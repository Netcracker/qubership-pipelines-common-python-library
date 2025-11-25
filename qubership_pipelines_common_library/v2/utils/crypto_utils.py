class CryptoUtils:
    EXCLUDE_KEYS = {"kind", "apiVersion"}

    @staticmethod
    def is_base64(s) -> bool:
        try:
            if isinstance(s, str):
                s_bytes = s.encode('utf-8')
            else:
                s_bytes = s
            import base64
            return base64.b64encode(base64.b64decode(s_bytes)) == s_bytes
        except Exception:
            return False

    @staticmethod
    def get_base64_encrypted_str(s) -> str:
        if isinstance(s, str):
            s_bytes = s.encode('utf-8')
        else:
            s_bytes = s
        import base64
        return base64.b64encode(s_bytes).decode('utf-8')

    @staticmethod
    def mask_values(data, path=None):
        if path is None:
            path = []

        if isinstance(data, dict):
            return {
                key: (CryptoUtils.mask_values(value, path + [key])
                      if not (len(path) == 0 and key in CryptoUtils.EXCLUDE_KEYS)
                      else value)
                for key, value in data.items()
            }
        elif isinstance(data, list):
            return [CryptoUtils.mask_values(item, path) for item in data]
        else:
            return "[MASKED]"

    @staticmethod
    def get_parameters_for_print(content: dict, need_mask: bool):
        import yaml
        if need_mask:
            return yaml.dump(CryptoUtils.mask_values(content), default_flow_style=False)
        else:
            return yaml.dump(content, default_flow_style=False)
