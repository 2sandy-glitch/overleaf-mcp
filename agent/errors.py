"""Every error the server raises on purpose. Each one reaches the client as a
plain-language tool error; anything else is a bug."""


class OverleafMCPError(Exception):
    pass


class ConfigError(OverleafMCPError):
    """projects.json / env is missing something or is malformed."""


class BackendError(OverleafMCPError):
    """Syncing with Overleaf (or another remote) failed."""


class AuthError(BackendError):
    """The Overleaf web session is missing, expired, or has no access to the project."""


class WorkspaceError(OverleafMCPError):
    """A file operation was refused: bad path, text not found, binary file..."""
