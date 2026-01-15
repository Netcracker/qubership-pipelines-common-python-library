from enum import StrEnum


class AuthType(StrEnum):
    BASIC = 'basic'
    OAUTH = 'oauth'
    BEARER = 'bearer'
