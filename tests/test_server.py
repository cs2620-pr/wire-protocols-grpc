import pytest  # type: ignore
import grpc  # type: ignore
from unittest.mock import MagicMock, patch
from typing import Generator, Tuple
import time
import logging
import os

from server.server import ChatServicer
from server.chat.chat_pb2 import (
    CreateAccountRequest,
    LoginRequest,
    ListAccountsRequest,
    DeleteAccountRequest,
    SendMessageRequest,
    GetMessagesRequest,
    DeleteMessagesRequest,
    AccountInfo,
)
from server.constants import ErrorMessage, SuccessMessage

# Create logs directory if it doesn't exist
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Configure test logging to use the same files as regular execution
logging.basicConfig(
    level=logging.DEBUG,  # Use DEBUG level for tests
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(log_dir, "server.log")
        ),  # Same file as regular execution
        logging.StreamHandler(),  # Also print logs to the console for test output
    ],
)

# Set up protocol metrics logger to use the same file
protocol_logger = logging.getLogger("protocol_metrics")
protocol_logger.setLevel(logging.DEBUG)

# Remove any existing handlers to avoid duplicates
for handler in protocol_logger.handlers[:]:
    protocol_logger.removeHandler(handler)

protocol_handler = logging.FileHandler(
    os.path.join(log_dir, "protocol_metrics_server.log")
)
protocol_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
protocol_logger.addHandler(protocol_handler)

# Get a logger for test output
logger = logging.getLogger("tests.server")

# Tests will now use the fixtures from conftest.py to enable logging


@pytest.fixture
def mock_database() -> Generator[MagicMock, None, None]:
    """Create a mock database for testing."""
    with patch("server.server.ChatDatabase") as mock_db_cls:
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        yield mock_db


@pytest.fixture
def servicer(mock_database: MagicMock) -> ChatServicer:
    """Create a ChatServicer instance with a mock database."""
    return ChatServicer()


@pytest.fixture
def context() -> grpc.ServicerContext:
    """Create a mock gRPC servicer context."""
    return MagicMock(spec=grpc.ServicerContext)


@pytest.fixture
def valid_session() -> str:
    """Return a valid session token."""
    return "valid_session_token"


@pytest.fixture
def expired_session() -> str:
    """Return an expired session token."""
    return "expired_session_token"


def create_message(
    message_id: str,
    sender: str,
    content: str,
    timestamp: int,
    delivered: bool = False,
    recipient: str = "testuser",
    unread: bool = True,
    deleted: bool = False,
) -> dict:
    """Helper function to create a message dictionary."""
    return {
        "message_id": message_id,
        "sender": sender,
        "recipient": recipient,
        "content": content,
        "timestamp": timestamp,
        "delivered": delivered,
        "unread": unread,
        "deleted": deleted,
    }


def test_create_account(
    servicer: ChatServicer,
    context: grpc.ServicerContext,
    mock_database: MagicMock,
) -> None:
    """Test account creation."""
    # Arrange
    logger.info("Testing account creation functionality")
    mock_database.create_user.return_value = (True, "")
    request = CreateAccountRequest(username="testuser", password="testpass")

    # Log the request manually to ensure it appears in protocol logs
    servicer.log_message("TEST Request", "CreateAccount", request, "Test user creation")

    # Act
    logger.debug("Sending CreateAccount request")
    response = servicer.CreateAccount(request, context)
    logger.debug(f"Received CreateAccount response: success={response.success}")

    # Log the response manually
    servicer.log_message(
        "TEST Response", "CreateAccount", response, f"Success: {response.success}"
    )

    # Assert
    assert response.success is True
    assert response.error_message == ""
    mock_database.create_user.assert_called_once_with("testuser", "testpass")
    logger.info("Account creation test completed successfully")


def test_create_account_failure(
    servicer: ChatServicer,
    context: grpc.ServicerContext,
    mock_database: MagicMock,
) -> None:
    """Test account creation failure."""
    # Arrange
    logger.info("Testing account creation failure functionality")
    mock_database.create_user.return_value = (False, ErrorMessage.USERNAME_EXISTS.value)
    request = CreateAccountRequest(username="testuser", password="testpass")

    # Log the request manually
    servicer.log_message(
        "TEST Request", "CreateAccount", request, "Test user creation failure"
    )

    # Act
    logger.debug("Sending CreateAccount request (expected to fail)")
    response = servicer.CreateAccount(request, context)
    logger.debug(
        f"Received CreateAccount response: success={response.success}, error={response.error_message}"
    )

    # Log the response manually
    servicer.log_message(
        "TEST Response",
        "CreateAccount",
        response,
        f"Failed as expected: {response.error_message}",
    )

    # Assert
    assert response.success is False
    assert response.error_message == ErrorMessage.USERNAME_EXISTS.value
    mock_database.create_user.assert_called_once_with("testuser", "testpass")
    logger.info("Account creation failure test completed successfully")


def test_login_success(
    servicer: ChatServicer, context: grpc.ServicerContext, mock_database: MagicMock
) -> None:
    """Test successful login."""
    # Arrange
    mock_database.verify_user.return_value = (
        True,
        SuccessMessage.LOGIN_SUCCESSFUL.value,
    )
    mock_database.get_unread_message_count.return_value = 5
    request = LoginRequest(username="testuser", password="testpass")

    # Act
    response = servicer.Login(request, context)

    # Assert
    assert response.success is True
    assert response.error_message == ""
    assert response.unread_message_count == 5
    assert response.session_token != ""
    mock_database.verify_user.assert_called_once_with("testuser", "testpass")
    mock_database.create_session.assert_called_once()


def test_login_failure(
    servicer: ChatServicer, context: grpc.ServicerContext, mock_database: MagicMock
) -> None:
    """Test login failure."""
    # Arrange
    mock_database.verify_user.return_value = (
        False,
        ErrorMessage.INVALID_PASSWORD.value,
    )
    request = LoginRequest(username="testuser", password="wrongpass")

    # Act
    response = servicer.Login(request, context)

    # Assert
    assert response.success is False
    assert response.error_message == ErrorMessage.INVALID_PASSWORD.value
    mock_database.create_session.assert_not_called()


def test_list_accounts(
    servicer: ChatServicer, context: grpc.ServicerContext, mock_database: MagicMock
) -> None:
    """Test listing accounts."""
    # Arrange
    mock_database.verify_session.return_value = "testuser"
    mock_database.list_accounts.return_value = [
        {"username": "user1"},
        {"username": "user2"},
    ]
    request = ListAccountsRequest(
        session_token="test_token", pattern="user*", page_size=10, page_number=0
    )

    # Act
    response = servicer.ListAccounts(request, context)

    # Assert
    assert len(response.accounts) == 2
    assert response.accounts[0].username == "user1"
    assert response.accounts[1].username == "user2"
    assert response.error_message == ""
    mock_database.list_accounts.assert_called_once_with(
        pattern="user*", limit=10, offset=0
    )


def test_list_accounts_invalid_session(
    servicer: ChatServicer,
    context: grpc.ServicerContext,
    mock_database: MagicMock,
    expired_session: str,
) -> None:
    """Test listing accounts with invalid session."""
    # Arrange
    mock_database.verify_session.return_value = None
    request = ListAccountsRequest(session_token=expired_session)

    # Act
    response = servicer.ListAccounts(request, context)

    # Assert
    assert response.error_message == ErrorMessage.INVALID_SESSION.value
    assert len(response.accounts) == 0
    mock_database.list_accounts.assert_not_called()


def test_list_accounts_pagination(
    servicer: ChatServicer,
    context: grpc.ServicerContext,
    mock_database: MagicMock,
    valid_session: str,
) -> None:
    """Test account listing pagination."""
    # Arrange
    mock_database.verify_session.return_value = "testuser"
    # Return exactly page_size items to indicate there might be more
    mock_database.list_accounts.return_value = [
        {"username": f"user{i}"} for i in range(5)
    ]
    request = ListAccountsRequest(
        session_token=valid_session, page_size=5, page_number=1  # Second page
    )

    # Act
    response = servicer.ListAccounts(request, context)

    # Assert
    assert len(response.accounts) == 5
    assert response.has_more  # Should be True when we get exactly page_size items
    mock_database.list_accounts.assert_called_once_with(pattern=None, limit=5, offset=5)


def test_list_accounts_online_status(
    servicer: ChatServicer,
    context: grpc.ServicerContext,
    mock_database: MagicMock,
    valid_session: str,
) -> None:
    """Test online status in account listing."""
    # Arrange
    mock_database.verify_session.return_value = "testuser"
    mock_database.list_accounts.return_value = [
        {"username": "online_user"},
        {"username": "offline_user"},
    ]
    # Add online_user to the servicer's online_users dict
    servicer.online_users["online_user"] = "some_session_token"
    request = ListAccountsRequest(session_token=valid_session)

    # Act
    response = servicer.ListAccounts(request, context)

    # Assert
    assert len(response.accounts) == 2
    online_user = next(a for a in response.accounts if a.username == "online_user")
    offline_user = next(a for a in response.accounts if a.username == "offline_user")
    assert online_user.is_online is True
    assert offline_user.is_online is False


def test_delete_account(
    servicer: ChatServicer, context: grpc.ServicerContext, mock_database: MagicMock
) -> None:
    """Test account deletion."""
    # Arrange
    mock_database.verify_session.return_value = "testuser"
    mock_database.delete_account.return_value = (True, "")
    request = DeleteAccountRequest(session_token="test_token")

    # Act
    response = servicer.DeleteAccount(request, context)

    # Assert
    assert response.success is True
    assert response.error_message == ""
    mock_database.delete_account.assert_called_once_with("testuser")
    mock_database.delete_session.assert_called_once_with("test_token")


def test_send_message(
    servicer: ChatServicer, context: grpc.ServicerContext, mock_database: MagicMock
) -> None:
    """Test sending a message."""
    # Arrange
    mock_database.verify_session.return_value = "sender"
    mock_database.send_message.return_value = (True, "")
    request = SendMessageRequest(
        session_token="test_token", recipient="recipient", content="Hello!"
    )

    # Act
    response = servicer.SendMessage(request, context)

    # Assert
    assert response.success is True
    assert response.error_message == ""
    assert response.message_id != ""
    mock_database.send_message.assert_called_once()
    call_args = mock_database.send_message.call_args[1]
    assert call_args["sender"] == "sender"
    assert call_args["recipient"] == "recipient"
    assert call_args["content"] == "Hello!"
    assert "message_id" in call_args


def test_send_message_invalid_session(
    servicer: ChatServicer,
    context: grpc.ServicerContext,
    mock_database: MagicMock,
    expired_session: str,
) -> None:
    """Test sending message with invalid session."""
    # Arrange
    mock_database.verify_session.return_value = None
    request = SendMessageRequest(
        session_token=expired_session, recipient="recipient", content="Hello!"
    )

    # Act
    response = servicer.SendMessage(request, context)

    # Assert
    assert response.success is False
    assert response.error_message == ErrorMessage.INVALID_SESSION.value
    assert response.message_id == ""
    mock_database.send_message.assert_not_called()


def test_get_messages(
    servicer: ChatServicer, context: grpc.ServicerContext, mock_database: MagicMock
) -> None:
    """Test retrieving messages."""
    # Arrange
    mock_database.verify_session.return_value = "testuser"
    mock_database.get_messages.return_value = [
        {
            "message_id": "msg1",
            "sender": "user1",
            "content": "Hello",
            "timestamp": 1234567890,
            "delivered": True,
        }
    ]
    request = GetMessagesRequest(session_token="test_token", max_messages=10)

    # Act
    response = servicer.GetMessages(request, context)

    # Assert
    assert len(response.messages) == 1
    assert response.messages[0].message_id == "msg1"
    assert response.messages[0].sender == "user1"
    assert response.messages[0].content == "Hello"
    assert response.messages[0].timestamp == 1234567890
    assert response.messages[0].delivered is True
    mock_database.get_messages.assert_called_once_with(username="testuser", limit=10)


def test_get_messages_ordering(
    servicer: ChatServicer,
    context: grpc.ServicerContext,
    mock_database: MagicMock,
    valid_session: str,
) -> None:
    """Test message ordering in get messages."""
    # Arrange
    mock_database.verify_session.return_value = "testuser"
    current_time = int(time.time())
    messages = [
        create_message("msg1", "user1", "First", current_time - 100),
        create_message("msg2", "user2", "Second", current_time - 50),
        create_message("msg3", "user3", "Third", current_time),
    ]
    mock_database.get_messages.return_value = messages
    request = GetMessagesRequest(session_token=valid_session, max_messages=10)

    # Act
    response = servicer.GetMessages(request, context)

    # Assert
    assert len(response.messages) == 3
    # Messages should maintain their order
    assert response.messages[0].message_id == "msg1"
    assert response.messages[1].message_id == "msg2"
    assert response.messages[2].message_id == "msg3"
    # Verify timestamps are preserved
    assert response.messages[0].timestamp == current_time - 100
    assert response.messages[1].timestamp == current_time - 50
    assert response.messages[2].timestamp == current_time


def test_get_messages_limit(
    servicer: ChatServicer,
    context: grpc.ServicerContext,
    mock_database: MagicMock,
    valid_session: str,
) -> None:
    """Test message limit in get messages."""
    # Arrange
    mock_database.verify_session.return_value = "testuser"
    current_time = int(time.time())
    messages = [
        create_message(f"msg{i}", f"user{i}", f"Message {i}", current_time - i)
        for i in range(5)
    ]
    mock_database.get_messages.return_value = messages
    request = GetMessagesRequest(session_token=valid_session, max_messages=3)

    # Act
    response = servicer.GetMessages(request, context)

    # Assert
    assert len(response.messages) == 5  # Should get all messages from mock
    mock_database.get_messages.assert_called_once_with(username="testuser", limit=3)


def test_delete_messages(
    servicer: ChatServicer, context: grpc.ServicerContext, mock_database: MagicMock
) -> None:
    """Test deleting messages."""
    # Arrange
    mock_database.verify_session.return_value = "testuser"
    mock_database.delete_messages.return_value = (True, [])
    request = DeleteMessagesRequest(
        session_token="test_token", message_ids=["msg1", "msg2"]
    )

    # Act
    response = servicer.DeleteMessages(request, context)

    # Assert
    assert response.success is True
    assert response.error_message == ""
    assert len(response.failed_message_ids) == 0
    mock_database.delete_messages.assert_called_once_with(
        message_ids=["msg1", "msg2"], username="testuser"
    )


def test_delete_messages_partial_failure(
    servicer: ChatServicer,
    context: grpc.ServicerContext,
    mock_database: MagicMock,
    valid_session: str,
) -> None:
    """Test partial failure in message deletion."""
    # Arrange
    mock_database.verify_session.return_value = "testuser"
    mock_database.delete_messages.return_value = (False, ["msg2", "msg3"])
    request = DeleteMessagesRequest(
        session_token=valid_session, message_ids=["msg1", "msg2", "msg3"]
    )

    # Act
    response = servicer.DeleteMessages(request, context)

    # Assert
    assert response.success is False
    assert response.error_message == ErrorMessage.FAILED_DELETE_MESSAGES.value
    assert response.failed_message_ids == ["msg2", "msg3"]
    mock_database.delete_messages.assert_called_once_with(
        message_ids=["msg1", "msg2", "msg3"], username="testuser"
    )


def test_delete_account_with_messages(
    servicer: ChatServicer,
    context: grpc.ServicerContext,
    mock_database: MagicMock,
    valid_session: str,
) -> None:
    """Test account deletion with existing messages."""
    # Arrange
    mock_database.verify_session.return_value = "testuser"
    mock_database.delete_account.return_value = (True, "")
    request = DeleteAccountRequest(session_token=valid_session)

    # Act
    response = servicer.DeleteAccount(request, context)

    # Assert
    assert response.success is True
    assert response.error_message == ""
    # Verify the session is deleted
    mock_database.delete_session.assert_called_once_with(valid_session)
    # Verify user is removed from online users
    assert "testuser" not in servicer.online_users


def test_login_with_unread_messages(
    servicer: ChatServicer,
    context: grpc.ServicerContext,
    mock_database: MagicMock,
) -> None:
    """Test login with unread messages."""
    # Arrange
    mock_database.verify_user.return_value = (True, "")
    mock_database.get_unread_message_count.return_value = 42
    request = LoginRequest(username="testuser", password="testpass")

    # Act
    response = servicer.Login(request, context)

    # Assert
    assert response.success is True
    assert response.unread_message_count == 42
    assert response.session_token != ""
    mock_database.verify_user.assert_called_once_with("testuser", "testpass")
    mock_database.create_session.assert_called_once()


def test_session_expiry(
    servicer: ChatServicer,
    context: grpc.ServicerContext,
    mock_database: MagicMock,
    expired_session: str,
) -> None:
    """Test handling of expired sessions."""
    # Arrange
    mock_database.verify_session.return_value = None  # Simulates expired session

    # Test with various endpoints that require authentication
    list_request = ListAccountsRequest(session_token=expired_session)
    send_request = SendMessageRequest(
        session_token=expired_session, recipient="someone", content="Hello"
    )
    get_request = GetMessagesRequest(session_token=expired_session)
    delete_request = DeleteMessagesRequest(
        session_token=expired_session, message_ids=["msg1"]
    )

    # Act & Assert
    list_response = servicer.ListAccounts(list_request, context)
    assert list_response.error_message == ErrorMessage.INVALID_SESSION.value

    send_response = servicer.SendMessage(send_request, context)
    assert send_response.error_message == ErrorMessage.INVALID_SESSION.value
    assert send_response.success is False

    get_response = servicer.GetMessages(get_request, context)
    assert get_response.error_message == ErrorMessage.INVALID_SESSION.value

    delete_response = servicer.DeleteMessages(delete_request, context)
    assert delete_response.error_message == ErrorMessage.INVALID_SESSION.value
    assert delete_response.success is False


def test_get_messages_marks_as_delivered(
    servicer: ChatServicer,
    context: grpc.ServicerContext,
    mock_database: MagicMock,
    valid_session: str,
) -> None:
    """Test that getting messages marks them as delivered."""
    # Arrange
    mock_database.verify_session.return_value = "testuser"
    current_time = int(time.time())
    messages = [
        create_message("msg1", "user1", "First", current_time, delivered=False),
        create_message("msg2", "user2", "Second", current_time, delivered=False),
    ]
    mock_database.get_messages.return_value = messages
    request = GetMessagesRequest(session_token=valid_session, max_messages=10)

    # Act
    response = servicer.GetMessages(request, context)

    # Assert
    assert len(response.messages) == 2
    # In the response, messages should be marked as delivered
    assert all(msg.delivered for msg in response.messages)
    mock_database.get_messages.assert_called_once_with(username="testuser", limit=10)


def test_send_message_to_nonexistent_user(
    servicer: ChatServicer,
    context: grpc.ServicerContext,
    mock_database: MagicMock,
    valid_session: str,
) -> None:
    """Test sending message to non-existent user."""
    # Arrange
    mock_database.verify_session.return_value = "sender"
    mock_database.send_message.return_value = (
        False,
        ErrorMessage.RECIPIENT_NOT_FOUND.value,
    )
    request = SendMessageRequest(
        session_token=valid_session, recipient="nonexistent", content="Hello!"
    )

    # Act
    response = servicer.SendMessage(request, context)

    # Assert
    assert response.success is False
    assert response.error_message == ErrorMessage.RECIPIENT_NOT_FOUND.value
    assert response.message_id == ""
    mock_database.send_message.assert_called_once()


def test_delete_account_removes_session(
    servicer: ChatServicer,
    context: grpc.ServicerContext,
    mock_database: MagicMock,
    valid_session: str,
) -> None:
    """Test that deleting account removes the session."""
    # Arrange
    username = "testuser"
    mock_database.verify_session.return_value = username
    mock_database.delete_account.return_value = (True, "")
    # Add user to online users
    servicer.online_users[username] = valid_session
    request = DeleteAccountRequest(session_token=valid_session)

    # Act
    response = servicer.DeleteAccount(request, context)

    # Assert
    assert response.success is True
    # Verify session is deleted
    mock_database.delete_session.assert_called_once_with(valid_session)
    # Verify user is removed from online users
    assert username not in servicer.online_users
    # Verify account is deleted
    mock_database.delete_account.assert_called_once_with(username)


def test_protocol_logging(
    servicer: ChatServicer, context: grpc.ServicerContext, mock_database: MagicMock
) -> None:
    """Test that protocol logging is working automatically."""
    # Arrange
    logger.info("Testing protocol logging functionality")
    mock_database.verify_session.return_value = "testuser"
    mock_database.send_message.return_value = (True, "")

    # Create a request that will generate sizeable log output
    content = "This is a test message that should be logged with protocol metrics. " * 5
    request = SendMessageRequest(
        session_token="test_token", recipient="recipient", content=content
    )

    # Log test start
    logger.debug("About to call SendMessage which should generate protocol logs")

    # Act - this should trigger automatic protocol logging
    response = servicer.SendMessage(request, context)

    # Assert basic response is correct
    assert response.success is True
    assert response.error_message == ""

    # Log test completion
    logger.info("Protocol logging test completed - check logs directory for output")

    # Verify the logs directory exists
    assert os.path.exists("logs"), "Logs directory should be created"

    # Additional log entry to make the logs go burr
    servicer.log_message(
        "TEST EXPLICIT",
        "ProtocolLoggingTest",
        request,
        "This is an explicit log entry to verify protocol logging",
    )
