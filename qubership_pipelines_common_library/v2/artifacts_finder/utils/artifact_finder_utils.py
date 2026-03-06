from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommand
from qubership_pipelines_common_library.v1.utils.utils_dictionary import UtilsDictionary


class ArtifactProviderFactory:
    @staticmethod
    def create_artifactory_provider(provider_params: dict, common_params: dict):
        from qubership_pipelines_common_library.v2.artifacts_finder.providers.artifactory import ArtifactoryProvider
        provider = ArtifactoryProvider(
            registry_url=provider_params.get("registry_url"),
            username=provider_params.get("username"),
            password=provider_params.get("password"),
            params=common_params,
        )
        return provider

    @staticmethod
    def create_nexus_provider(provider_params: dict, common_params: dict):
        from qubership_pipelines_common_library.v2.artifacts_finder.providers.nexus import NexusProvider
        provider = NexusProvider(
            registry_url=provider_params.get("registry_url"),
            username=provider_params.get("username"),
            password=provider_params.get("password"),
            params=common_params,
        )
        return provider

    @staticmethod
    def create_aws_provider(provider_params: dict, common_params: dict):
        from qubership_pipelines_common_library.v2.artifacts_finder.auth.aws_credentials import AwsCredentialsProvider
        from qubership_pipelines_common_library.v2.artifacts_finder.providers.aws_code_artifact import AwsCodeArtifactProvider

        kwargs = {
            'access_key': provider_params.get("access_key"),
            'secret_key': provider_params.get("secret_key"),
            'region_name': provider_params.get("region_name"),
        }
        auth_type = provider_params.get("auth_type").upper()
        if auth_type == "DIRECT":
            credentials = AwsCredentialsProvider().with_direct_credentials(**kwargs).get_credentials()
        elif auth_type == "ASSUME_ROLE":
            ArtifactProviderFactory._validate_required_fields(
                provider_params, required_fields=["role_arn"],
                provider_name="AWS", auth_type=auth_type
            )
            kwargs["role_arn"] = provider_params.get("role_arn")
            credentials = AwsCredentialsProvider().with_assume_role(**kwargs).get_credentials()
        else:
            raise Exception(f"Unsupported auth type for AWS: {auth_type}")

        provider = AwsCodeArtifactProvider(
            credentials=credentials,
            domain=provider_params.get("domain"),
            repository=provider_params.get("repository"),
            package_format=provider_params.get("package_format", "generic"),
            params=common_params,
        )
        return provider

    @staticmethod
    def create_gcp_provider(provider_params: dict, common_params: dict):
        from qubership_pipelines_common_library.v2.artifacts_finder.auth.gcp_credentials import GcpCredentialsProvider
        from qubership_pipelines_common_library.v2.artifacts_finder.providers.gcp_artifact_registry import GcpArtifactRegistryProvider

        auth_type = provider_params.get("auth_type").upper()
        if auth_type == "SA_KEY":
            if "service_account_key_path" in provider_params:
                credentials = GcpCredentialsProvider().with_service_account_key(
                    service_account_key_path=provider_params.get("service_account_key_path")
                ).get_credentials()
            elif "service_account_key_content" in provider_params:
                credentials = GcpCredentialsProvider().with_service_account_key(
                    service_account_key_content=provider_params.get("service_account_key_content")
                ).get_credentials()
            else:
                ArtifactProviderFactory._validate_required_fields(
                    provider_params, required_fields=["service_account_key_content", "service_account_key_path"],
                    provider_name="GCP", auth_type=auth_type
                )
        elif auth_type == "OIDC_CREDS":
            ArtifactProviderFactory._validate_required_fields(
                provider_params, required_fields=["oidc_credential_source", "audience"],
                provider_name="GCP", auth_type=auth_type
            )
            credentials = GcpCredentialsProvider().with_oidc_creds(
                oidc_credential_source=provider_params.get("oidc_credential_source"),
                audience=provider_params.get("audience"),
            ).get_credentials()
        else:
            raise Exception(f"Unsupported auth type for GCP: {auth_type}")

        provider = GcpArtifactRegistryProvider(
            credentials=credentials,
            project=provider_params.get("project"),
            region_name=provider_params.get("region_name"),
            repository=provider_params.get("repository"),
            params=common_params,
        )
        return provider

    @staticmethod
    def create_azure_provider(provider_params: dict, common_params: dict):
        from qubership_pipelines_common_library.v2.artifacts_finder.auth.azure_credentials import AzureCredentialsProvider
        from qubership_pipelines_common_library.v2.artifacts_finder.providers.azure_artifacts import AzureArtifactsProvider

        auth_type = provider_params.get("auth_type").upper()
        if auth_type == "OAUTH2":
            if custom_auth_data := provider_params.get("custom_auth_data"):
                credentials = AzureCredentialsProvider().with_oauth2_custom_data(
                    tenant_id=provider_params.get("tenant_id"),
                    custom_auth_data=custom_auth_data,
                ).get_credentials()
            else:
                ArtifactProviderFactory._validate_required_fields(
                    provider_params, required_fields=["client_id", "client_secret", "target_resource"],
                    provider_name="Azure", auth_type=auth_type
                )
                credentials = AzureCredentialsProvider().with_oauth2(
                    tenant_id=provider_params.get("tenant_id"),
                    client_id=provider_params.get("client_id"),
                    client_secret=provider_params.get("client_secret"),
                    target_resource=provider_params.get("target_resource"),
                ).get_credentials()
        else:
            raise Exception(f"Unsupported auth type for Azure: {auth_type}")

        provider = AzureArtifactsProvider(
            credentials=credentials,
            organization=provider_params.get("organization"),
            project=provider_params.get("project"),
            feed=provider_params.get("feed"),
            params=common_params,
        )
        return provider

    @staticmethod
    def _validate_required_fields(provider_params: dict, required_fields: list[str], provider_name: str, auth_type: str):
        if missing := UtilsDictionary.check_required_fields(provider_params, required_fields):
            raise Exception(f"Missing fields: {missing} for {provider_name} {auth_type} auth scenario!")


class ArtifactFinderUtils:

    PROVIDERS_CONFIG = {
        "artifactory": {
            "required_fields": ["registry_url"],
            "init_method": ArtifactProviderFactory.create_artifactory_provider
        },
        "nexus": {
            "required_fields": ["registry_url"],
            "init_method": ArtifactProviderFactory.create_nexus_provider
        },
        "aws": {
            "required_fields": ["auth_type", "domain", "repository", "access_key", "secret_key", "region_name"],
            "init_method": ArtifactProviderFactory.create_aws_provider
        },
        "gcp": {
            "required_fields": ["auth_type", "project", "region_name", "repository"],
            "init_method": ArtifactProviderFactory.create_gcp_provider
        },
        "azure": {
            "required_fields": ["auth_type", "organization", "project", "feed", "tenant_id"],
            "init_method": ArtifactProviderFactory.create_azure_provider
        },
    }

    @staticmethod
    def create_artifact_finder_for_command(cmd: ExecutionCommand):
        params = cmd.context.input_param_get("systems.artifact_finder")
        provider = None
        if params:
            configured_providers = [name for name in ArtifactFinderUtils.PROVIDERS_CONFIG if name in params]
            if not configured_providers:
                raise Exception("Missing specific provider configuration in 'systems.artifact_finder' section")
            if len(configured_providers) > 1:
                raise Exception(f"Multiple Artifact providers configured: {configured_providers}. Only one is expected.")

            provider_name = configured_providers[0]
            provider_config = ArtifactFinderUtils.PROVIDERS_CONFIG.get(provider_name)
            provider_params = params.get(provider_name)
            common_params = {"timeout": cmd.timeout_seconds, "verify": cmd.verify}
            if missing := UtilsDictionary.check_required_fields(provider_params, provider_config.get("required_fields", [])):
                raise Exception(f"Missing required fields for {provider_name}: {missing}")

            provider = provider_config.get("init_method")(provider_params, common_params)

        from qubership_pipelines_common_library.v2.artifacts_finder.artifact_finder import ArtifactFinder
        return ArtifactFinder(artifact_provider=provider)
