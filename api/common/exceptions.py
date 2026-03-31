class EchoWhaleError(Exception):
    """Base application error."""


class NotFoundError(EchoWhaleError):
    """Raised when an entity does not exist."""
