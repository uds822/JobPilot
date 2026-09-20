class AppException(Exception):
    """Base exception for application errors."""

    def __init__(self, message: str = "An error occurred."):
        super().__init__(message)
        self.message = message

    def __str__(self):
        return self.message


class NotFoundError(AppException):
    """Requested resource does not exist."""


class ConflictError(AppException):
    """Request conflicts with existing data."""


class BadRequestError(AppException):
    """Request contains invalid business data."""


class UnauthorizedError(AppException):
    """Authentication or authorization failed."""
