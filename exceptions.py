"""Custom exception classes for the auto_chat application."""


class AutoChatException(Exception):
    """Base exception for all auto_chat errors."""
    pass


class APIException(AutoChatException):
    """Base exception for API-related errors."""
    pass


class APIKeyMissingError(APIException):
    """Raised when an API key is required but not provided."""
    pass


class ModelNotSetError(APIException):
    """Raised when a model must be set but hasn't been."""
    pass


class APIRequestError(APIException):
    """Raised when an API request fails."""

    def __init__(self, message: str, status_code: int = None, response_text: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class PersonaException(AutoChatException):
    """Base exception for persona-related errors."""
    pass


class PersonaLoadError(PersonaException):
    """Raised when personas cannot be loaded."""
    pass


class PersonaSaveError(PersonaException):
    """Raised when personas cannot be saved."""
    pass


class PersonaValidationError(PersonaException):
    """Raised when persona data is invalid."""
    pass


class ConfigException(AutoChatException):
    """Base exception for configuration-related errors."""
    pass


class ConfigLoadError(ConfigException):
    """Raised when configuration cannot be loaded."""
    pass


class ConfigSaveError(ConfigException):
    """Raised when configuration cannot be saved."""
    pass
