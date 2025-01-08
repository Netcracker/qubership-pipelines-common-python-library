# Copyright 2024 NetCracker Technology Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from enum import StrEnum

from kubernetes import client, config
from kubernetes.client import Configuration, ApiException, V1Deployment


class ScaleMode(StrEnum):
    UP = 'Up'
    DOWN = 'Down'


class ResourceKind(StrEnum):
    DEPLOYMENT = 'Deployment'
    STATEFUL_SET = 'StatefulSet'


class KubeClient:
    REPLICAS_CONFIG_MAP_NAME = "replicas-config"
    DEPLOYMENTS_KEY = "deployments"
    STATEFUL_SETS_KEY = "statefulsets"

    def __init__(self, endpoint: str = None, token: str = None, kubeconfig_path: str = None):
        if kubeconfig_path:
            config.load_kube_config(config_file=kubeconfig_path)
        elif endpoint and token:
            config.load_kube_config_from_dict(self.__get_generic_admin_kubeconfig(endpoint, token))
        else:
            raise Exception("Neither kubeconfig file or endpoint/token combination were provided to configure KubeClient!")
        self.core_api = client.CoreV1Api()
        self.apps_api = client.AppsV1Api()
        logging.info("Kube Client configured for %s", Configuration.get_default_copy().host)

    def list_namespaces(self):
        ns_list = self.core_api.list_namespace(watch=False)
        return [i.metadata.name for i in ns_list.items]

    def namespace_exists(self, namespace: str):
        if not namespace:
            return False
        try:
            self.core_api.read_namespace_status(namespace)
            return True
        except ApiException as e:
            if e.status == 404:
                return False
            raise e

    def deployments_exist(self, namespace: str):
        deployments = self.apps_api.list_namespaced_deployment(namespace, limit=1)
        return len(deployments.items) > 0

    def is_namespace_scaled_to_zero(self, namespace: str):
        all_replicas = [i.spec.replicas for i in self.__get_deployments_and_stateful_sets(namespace)]
        logging.debug(f"StatefulSet and Deployment replica count for {namespace}: {all_replicas}")
        return len(all_replicas) == 0 or all(r == 0 for r in all_replicas)

    def list_not_ready_resources(self, namespace):
        deployment_unavailable_replicas = [
            ResourceReplicaCount(p.metadata.name,
                                 ResourceKind.DEPLOYMENT if isinstance(p, V1Deployment) else ResourceKind.STATEFUL_SET,
                                 p.status.available_replicas, p.status.replicas) for
            p in self.__get_deployments_and_stateful_sets(namespace) if
            p.status.available_replicas != p.status.replicas]
        return deployment_unavailable_replicas

    def create_namespace(self, namespace: str):
        body = client.V1Namespace(metadata=client.V1ObjectMeta(name=namespace))
        return self.core_api.create_namespace(body=body)

    def delete_namespaces(self, namespaces: list[str], ignore_not_found: bool = False):
        for namespace in namespaces:
            try:
                self.core_api.delete_namespace(namespace)
            except ApiException as e:
                if ignore_not_found and e.status == 404:
                    logging.info(f"Namespace {namespace} not found, can't delete...")
                else:
                    raise e

    def list_config_map_names(self, namespace: str):
        return [i.metadata.name for i in self.core_api.list_namespaced_config_map(namespace).items]

    def read_config_map(self, namespace: str, config_map_name: str):
        return self.core_api.read_namespaced_config_map(config_map_name, namespace)

    def create_config_map(self, namespace: str, config_map_name: str, config_map_data: dict):
        object_meta = client.V1ObjectMeta(name=config_map_name, namespace=namespace)
        body = client.V1ConfigMap(api_version="v1", kind="ConfigMap", metadata=object_meta, data=config_map_data)
        self.core_api.create_namespaced_config_map(namespace=namespace, body=body)

    def patch_config_map(self, namespace: str, config_map_name: str, config_map_data: dict):
        """ Patching allows adding/removing only specified keys in config map. Removes key-value pair when value is None """
        object_meta = client.V1ObjectMeta(name=config_map_name, namespace=namespace)
        body = client.V1ConfigMap(api_version="v1", kind="ConfigMap", metadata=object_meta, data=config_map_data)
        self.core_api.patch_namespaced_config_map(name=config_map_name, namespace=namespace, body=body)

    def replace_config_map(self, namespace: str, config_map_name: str, config_map_data: dict):
        """ Replaces all data inside existing config map with value of 'config_map_data' argument """
        object_meta = client.V1ObjectMeta(name=config_map_name, namespace=namespace)
        body = client.V1ConfigMap(api_version="v1", kind="ConfigMap", metadata=object_meta, data=config_map_data)
        self.core_api.replace_namespaced_config_map(name=config_map_name, namespace=namespace, body=body)

    def create_or_replace_config_map(self, namespace: str, config_map_name: str, config_map_data: dict):
        if config_map_name in self.list_config_map_names(namespace):
            self.replace_config_map(namespace, config_map_name, config_map_data)
        else:
            self.create_config_map(namespace, config_map_name, config_map_data)

    def delete_config_map(self, namespace: str, config_map_name: str):
        self.core_api.delete_namespaced_config_map(name=config_map_name, namespace=namespace)

    def scale_namespace(self, namespace: str, scale_mode: ScaleMode, use_config_map: bool = True, replicas: int = 0):
        logging.info(f"Scaling {namespace} '{scale_mode}', use_config_map: {use_config_map}, replicas: {replicas}")
        if scale_mode == ScaleMode.DOWN:
            self.scale_namespace_down(namespace)
        if scale_mode == ScaleMode.UP:
            self.scale_namespace_up(namespace, use_config_map, replicas)

    def scale_namespace_down(self, namespace: str):
        if self.is_namespace_scaled_to_zero(namespace):
            logging.info(f"Namespace {namespace} is already scaled to zero!")
            return

        deployments = self.apps_api.list_namespaced_deployment(namespace).items
        statefulsets = self.apps_api.list_namespaced_stateful_set(namespace).items
        data = {}
        if deployments:
            data[KubeClient.DEPLOYMENTS_KEY] = "\n".join([f"{d.metadata.name}={d.spec.replicas}" for d in deployments])
        if statefulsets:
            data[KubeClient.STATEFUL_SETS_KEY] = "\n".join([f"{d.metadata.name}={d.spec.replicas}" for d in statefulsets])
        self.create_or_replace_config_map(namespace, KubeClient.REPLICAS_CONFIG_MAP_NAME, data)

        for deployment in deployments:
            self.apps_api.patch_namespaced_deployment_scale(name=deployment.metadata.name, namespace=namespace,
                                                            body={'spec': {'replicas': 0}})
        for statefulset in statefulsets:
            self.apps_api.patch_namespaced_stateful_set_scale(name=statefulset.metadata.name, namespace=namespace,
                                                              body={'spec': {'replicas': 0}})

    def scale_namespace_up(self, namespace: str, use_config_map: bool, replicas: int = 0):
        if use_config_map:
            replicas_data = self.read_config_map(namespace, KubeClient.REPLICAS_CONFIG_MAP_NAME).data
            logging.info(f"Using following data for scaling up: {replicas_data}")
            if KubeClient.DEPLOYMENTS_KEY in replicas_data:
                for deployment in replicas_data[KubeClient.DEPLOYMENTS_KEY].splitlines():
                    dep_parts = deployment.split("=")
                    self.apps_api.patch_namespaced_deployment_scale(name=dep_parts[0], namespace=namespace,
                                                                    body={'spec': {'replicas': int(dep_parts[1])}})
            if KubeClient.STATEFUL_SETS_KEY in replicas_data:
                for statefulset in replicas_data[KubeClient.STATEFUL_SETS_KEY].splitlines():
                    ss_parts = statefulset.split("=")
                    self.apps_api.patch_namespaced_stateful_set_scale(name=ss_parts[0], namespace=namespace,
                                                                    body={'spec': {'replicas': int(ss_parts[1])}})
        else:
            if replicas <= 0:
                raise Exception(f"Scaling up to '{replicas}' is not supported, needs positive integer!")
            deployments = self.apps_api.list_namespaced_deployment(namespace).items
            for deployment in deployments:
                self.apps_api.patch_namespaced_deployment_scale(name=deployment.metadata.name, namespace=namespace,
                                                                body={'spec': {'replicas': replicas}})
            statefulsets = self.apps_api.list_namespaced_stateful_set(namespace).items
            for statefulset in statefulsets:
                self.apps_api.patch_namespaced_stateful_set_scale(name=statefulset.metadata.name, namespace=namespace,
                                                                  body={'spec': {'replicas': replicas}})

    def __get_deployments_and_stateful_sets(self, namespace: str):
        return self.apps_api.list_namespaced_deployment(namespace).items + self.apps_api.list_namespaced_stateful_set(namespace).items

    def __get_generic_admin_kubeconfig(self, endpoint: str, token: str):
        return {
            "current-context": "context-admin/cluster_name",
            "contexts": [
                {
                    "name": "context-admin/cluster_name",
                    "context": {
                        "cluster": "cluster_name",
                        "user": "admin/cluster_name",
                    }
                }
            ],
            "clusters": [
                {
                    "name": "cluster_name",
                    "cluster": {
                        "server": endpoint,
                        "insecure-skip-tls-verify": True,
                    }
                }
            ],
            "users": [
                {
                    "name": "admin/cluster_name",
                    "user": {
                        "token": token
                    }
                }
            ]
        }


class ResourceReplicaCount:
    def __init__(self, name: str, kind: ResourceKind, available_replicas: int, target_replicas: int):
        self._name = name
        self._kind = kind
        self._available_replicas = 0 if available_replicas is None else available_replicas
        self._target_replicas = target_replicas

    @property
    def name(self):
        return self._name

    @property
    def kind(self):
        return self._kind

    @property
    def available_replicas(self):
        return self._available_replicas

    @property
    def target_replicas(self):
        return self._target_replicas

    def __repr__(self) -> str:
        return f"[name: {self.name}, kind: {self.kind}, replicas: {self.available_replicas}/{self.target_replicas}]"

    def __str__(self) -> str:
        return f"[name: {self.name}, kind: {self.kind}, replicas: {self.available_replicas}/{self.target_replicas}]"

    def __eq__(self, other):
        if isinstance(other, ResourceReplicaCount):
            return self.name == other.name and self.kind == other.kind \
                and self.available_replicas == other.available_replicas \
                and self.target_replicas == other.target_replicas
        return False
