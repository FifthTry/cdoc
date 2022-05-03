from enum import Enum


class OKind(Enum):
    USER = "USER"
    PULL_REQUEST = "PULL_REQUEST"
    REPOSITORY = "REPOSITORY"
    ORGANIZATION = "ORGANIZATION"
    INSTALLATION = "INSTALLATION"
    VISIT = "VISIT"
    # Any object
    # USER, PR, REPO, ORGANIZATION, INSTALLATION, ...


class EKind(Enum):
    GET = "GET"
    CREATE = "CREATE"
    APPROVE = "APPROVE"
    UPDATE = "UPDATE"
    LOGIN = "LOGIN"
    GITHUB_HANDOVER = "GITHUB_HANDOVER"
    CONNECT = "CONNECT"
    DISCONNECT = "DISCONNECT"
