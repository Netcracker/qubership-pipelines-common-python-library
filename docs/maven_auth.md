## Authorizing with maven-client (MavenArtifactSearcher)

All existing maven repositories support basic authorization, the only difference is how you go about issuing their tokens.

Authorization is required when accessing private repositories, and the same username/token pair could be used in Maven or Gradle


### JFrog Artifactory

JFrog Artifactory supports basic password authentication, so you can just use your technical user's login/password pair

```python
params_jfrog = {
    "username": "x_technical_user",
    "password": os.getenv('JFROG_TECH_USER_PASSWORD'),
    "registry_url": "http://192.168.225.129:8081/artifactory/test-mvn-repo",
}
maven_searcher = MavenArtifactSearcher(params_jfrog.get("registry_url")).with_artifactory(params_jfrog.get("username"), params_jfrog.get("password"))
```


### GitHub Packages

To access Maven artifacts stored in GitHub Packages, you need to authenticate with your personal access token.

Official documentation on this process is [here](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-apache-maven-registry)

But to recap, you need to go to your (or your technical user's) account settings:

`Settings -> Developer Settings -> Personal access tokens -> Tokens (classic)`

And `Generate new token (classic)` (token looks like `ghp_.....`)

GitHub doesn't have a single maven registry, but rather a registry per User/Organization.
So for registry URL you need to use either "https://maven.pkg.github.com/Netcracker/*" (to navigate all repositories under specified user) or "https://maven.pkg.github.com/Netcracker/certain_repo_name"

```python
registry_connection_params_github = {
    "username": "gh_tech_user_login",
    "password": os.getenv('GH_ACCESS_TOKEN'),
    "registry_url": "https://maven.pkg.github.com/Netcracker/*",
}
```


### Google Cloud GAR (Google Artifact Registry)

Official documentation on this process is [here](https://cloud.google.com/artifact-registry/docs/java/authentication?hl=en)

You need to use service account key as a credential.

So the process is:
- Create new `Service Account` with minimum required roles/permissions to access your Artifact Registry (e.g. "Artifact Registry Reader" role)
- Create new `Service Account Key` - and download it (it's a `.json` file)
- base64 encode this file to get your authentication token (e.g. `base64 -w 0 your_key.json > encoded_key.txt`)
- `username` should be `_json_key_base64`

```python
params_gcp = {
    "username": "_json_key_base64",
    "password": os.getenv('GAR_ACCESS_TOKEN'),
    "registry_url": "https://LOCATION-maven.pkg.dev/PROJECT/REPOSITORY",
}
maven_searcher = MavenArtifactSearcher(params_gcp.get("registry_url")).with_gcp_artifact_registry({"service_account_key": params_gcp.get("password")}, PROJECT, REGION, REPOSITORY)

```


### AWS Code Artifact

Official AWS documentation is [here](https://docs.aws.amazon.com/codeartifact/latest/ug/get-set-up-for-codeartifact.html)

You access `Code Artifact` repositories using special temporary token, but it's only valid for up to 12 hours.

To use persistent credentials, this library provides utility helper `AWSCodeArtifactHelper` that can generate token for you using Access + Secret keys and your domain + region.

You need to create an `IAM User` with required policies/permissions ([instructions here](https://docs.aws.amazon.com/codeartifact/latest/ug/get-set-up-provision-user.html))

Get `Access Key` and `Secret Key` to this user, you'll need them to generate your temporary authorization token to Code Artifact

```python
params_aws = {
    "username": "aws",
    "password": AWSCodeArtifactHelper.get_authorization_token(
        os.getenv('AWS_ACCESS_KEY'),
        os.getenv('AWS_SECRET_KEY'),
        "test-maven-domain",
        "us-east-1"
    ),
    "registry_url": "https://test-maven-domain-123.d.codeartifact.us-east-1.amazonaws.com/maven/test-maven-repo/",
}
maven_searcher = MavenArtifactSearcher(params_aws.get("registry_url")).with_aws_code_artifact(os.getenv('AWS_ACCESS_KEY'), os.getenv('AWS_SECRET_KEY'), DOMAIN, REGION, REPOSITORY)
```
