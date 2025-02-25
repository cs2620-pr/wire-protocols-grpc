from enum import Enum, auto


class ErrorMessage(Enum):
    """Error messages used throughout the application."""

    INVALID_SESSION = "Invalid or expired session"
    USERNAME_EXISTS = "Username already exists"
    USER_NOT_FOUND = "User not found"
    INVALID_PASSWORD = "Invalid password"
    RECIPIENT_NOT_FOUND = "Recipient not found"
    RECIPIENT_DELETED = "This user's account has been deleted"
    FAILED_DELETE_MESSAGES = "Failed to delete some messages"


class SuccessMessage(Enum):
    """Success messages used throughout the application."""

    USER_CREATED = "User created successfully"
    LOGIN_SUCCESSFUL = "Login successful"
    ACCOUNT_DELETED = "Account deleted successfully"
    MESSAGE_SENT = "Message sent successfully"


class DatabaseOperation(Enum):
    """Database operation types."""

    CREATE_USER = auto()
    VERIFY_USER = auto()
    DELETE_ACCOUNT = auto()
    SEND_MESSAGE = auto()
    GET_MESSAGES = auto()
    DELETE_MESSAGES = auto()
    CREATE_SESSION = auto()
    VERIFY_SESSION = auto()
    DELETE_SESSION = auto()


class SessionState(Enum):
    """Session states."""

    VALID = auto()
    INVALID = auto()
    EXPIRED = auto()


class MessageStatus(Enum):
    """Message status."""

    DELIVERED = "delivered"
    UNDELIVERED = "undelivered"
    DELETED = "deleted"
    ACTIVE = "active"
