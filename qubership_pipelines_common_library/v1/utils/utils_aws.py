class AWSCodeArtifactHelper:
    @staticmethod
    def get_authorization_token(access_key: str, secret_key: str, domain: str, region_name: str):
        """
        Fetches 12-hour temporary authorization token (using long-term credentials).
        This token is necessary for accessing CodeArtifact using standard maven interface
        """
        import boto3
        from botocore.config import Config
        client = boto3.client(service_name='codeartifact',
                              config=Config(region_name=region_name),
                              aws_access_key_id=access_key,
                              aws_secret_access_key=secret_key,
                              )
        response = client.get_authorization_token(domain=domain)
        return response.get('authorizationToken')
