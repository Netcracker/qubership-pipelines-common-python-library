# Authorizing with SecretManager

The SecretManager supports two modes of authorization:

1. **Direct** — instantiate a concrete provider with explicit arguments.
2. **Environment-variable-based** — via `MultiStoreProvider`, which resolves both the provider and its credentials from env vars.

---

## Direct Provider Initialization

Each provider accepts a `Credentials` object obtained from the corresponding credentials provider.

| Provider                    | Constructor                     | Credential provider                 |
|-----------------------------|---------------------------------|-------------------------------------|
| `HashicorpVaultProvider`    | `(url, credentials, namespace)` | `HashicorpVaultCredentialsProvider` |
| `OpenBaoProvider`           | `(url, credentials, namespace)` | `OpenBaoCredentialsProvider`        |
| `AwsSecretsManagerProvider` | `(credentials)`                 | `AwsCredentialsProvider`            |
| `AzureKeyVaultProvider`     | `(credentials)`                 | `AzureCredentialsProvider`          |
| `GcpSecretManagerProvider`  | `(credentials)`                 | `GcpCredentialsProvider`            |

```python
from qubership_pipelines_common_library.v2.secret_manager.secret_manager import SecretManager
from qubership_pipelines_common_library.v2.secret_manager.providers.hashicorp_vault import HashicorpVaultProvider
from qubership_pipelines_common_library.v2.artifacts_finder.auth.hashicorp_vault_credentials import HashicorpVaultCredentialsProvider

secret_manager = SecretManager(
    secret_provider=HashicorpVaultProvider(
        url="https://vault.example.com",
        credentials=HashicorpVaultCredentialsProvider().with_token("s.token").get_credentials(),
    )
)
```

---

## MultiStoreProvider — Environment-Variable Flow

`MultiStoreProvider` discovers the target provider from the **VALS URI scheme** embedded in each secret path:

```text
ref+awssecrets://demo/my-secret#/nested/key1
       ^-- provider type
```

The provider type is the part after `+` in the URI scheme. Supported values:

| URI scheme                | Backend             |
|---------------------------|---------------------|
| `ref+vault://...`         | HashiCorp Vault     |
| `ref+openbao://...`       | OpenBao             |
| `ref+awssecrets://...`    | AWS Secrets Manager |
| `ref+azurekeyvault://...` | Azure Key Vault     |
| `ref+gcpsecrets://...`    | GCP Secret Manager  |

**Important:** The `secret_store_id` query parameter (e.g. `?secret_store_id=prod`) prefixes every env var with `${store_id}_`. If omitted, env vars are read without a prefix.

```python
from qubership_pipelines_common_library.v2.secret_manager.secret_manager import SecretManager
from qubership_pipelines_common_library.v2.secret_manager.providers.multi_store_provider import MultiStoreProvider

sm = SecretManager(secret_provider=MultiStoreProvider())

# Reads VAULT_ADDR, VAULT_TOKEN / VAULT_USERNAME + VAULT_PASSWORD from env
sm.read_secret("vals://vault+myapp/config#/db/host")

# Reads SECOND_STORE_VAULT_ADDR, SECOND_STORE_VAULT_TOKEN, etc.
sm.read_secret("vals://vault+myapp/config?secret_store_id=SECOND_STORE#/db/host")
```

---

## Mandatory Environment Variables per Provider

### HashiCorp Vault

| Variable                            | Required | Description                                  |
|-------------------------------------|----------|----------------------------------------------|
| `VAULT_ADDR`                        | **Yes**  | Vault server URL                             |
| `VAULT_NAMESPACE`                   | No       | Vault namespace (for HCP / Enterprise)       |
| `VAULT_TOKEN`                       | One of   | Vault token (takes precedence over userpass) |
| `VAULT_USERNAME` + `VAULT_PASSWORD` | One of   | Userpass auth pair                           |

`VAULT_PASSWORD` supports file-based resolution: set `VAULT_PASSWORD_FILE=/path` to read the password from a file, or `VAULT_PASSWORD_ENV=OTHER_VAR` to proxy through another env var.

### OpenBao

| Variable                        | Required | Description                                    |
|---------------------------------|----------|------------------------------------------------|
| `BAO_ADDR`                      | **Yes**  | OpenBao server URL                             |
| `BAO_NAMESPACE`                 | No       | OpenBao namespace                              |
| `BAO_TOKEN`                     | One of   | OpenBao token (takes precedence over userpass) |
| `BAO_USERNAME` + `BAO_PASSWORD` | One of   | Userpass auth pair                             |

`BAO_PASSWORD` supports the same file/env-indirection resolution as `VAULT_PASSWORD`.

### AWS Secrets Manager

| Variable                | Required | Description                   |
|-------------------------|----------|-------------------------------|
| `AWS_ACCESS_KEY_ID`     | **Yes**  | IAM access key ID             |
| `AWS_SECRET_ACCESS_KEY` | **Yes**  | IAM secret access key         |
| `AWS_DEFAULT_REGION`    | **Yes**  | AWS region (e.g. `us-east-1`) |

Authentication type: always **DIRECT** (static keys). For `ASSUME_ROLE`, use `AwsCredentialsProvider` directly with `.with_assume_role()`.

### Azure Key Vault

| Variable                | Required | Description                                         |
|-------------------------|----------|-----------------------------------------------------|
| `AZURE_TENANT_ID`       | **Yes**  | Azure AD tenant ID                                  |
| `AZURE_CLIENT_ID`       | **Yes**  | Service principal client ID                         |
| `AZURE_CLIENT_SECRET`   | **Yes**  | Service principal client secret                     |
| `AZURE_TARGET_RESOURCE` | No       | Azure resource (default: `https://vault.azure.net`) |

Authentication: OAuth2 client credentials grant against `https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token`.

### GCP Secret Manager

| Variable                                 | Required | Description                               |
|------------------------------------------|----------|-------------------------------------------|
| `GOOGLE_APPLICATION_CREDENTIALS_CONTENT` | One of   | Inline service account JSON key           |
| `GOOGLE_APPLICATION_CREDENTIALS`         | One of   | **File path** to service account JSON key |

For workload identity federation (`OIDC_CREDS`), use `GcpCredentialsProvider` directly with `.with_oidc_creds()`.

The `GCP_PROJECT` env var is used to infer the GCP project when the secret path does not contain one (e.g. `ref+gcpsecrets://my-secret` instead of `ref+gcpsecrets://my-project/my-secret`).

---

## Prefix Behavior with `secret_store_id`

When a VALS URI includes `?secret_store_id=ALT_STORE`, all environment variables for that provider are prefixed with `ALT_STORE_`.
This allows configuring multiple stores of one type on one environment. For example:

```text
ref+vault://path/to/secret?secret_store_id=ALT_STORE#/nested_key
```

Expects these env vars:

```text
ALT_STORE_VAULT_ADDR=https://vault-prod.example.com
ALT_STORE_VAULT_TOKEN=s.prod-token
```

And version without `secret_store_id` (also known as `default` store):

```text
ref+vault://path/to/secret#/nested_key
```

Expects:

```text
VAULT_ADDR=https://vault.example.com
VAULT_TOKEN=s.token
```
