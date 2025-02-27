import pytest  # type: ignore
import os
import time
import threading
import logging
from typing import Generator, List, Dict, Any, Callable
from server.database import ChatDatabase

# Create logs directory if it doesn't exist
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Configure database test logging to use the same file as regular execution
database_logger = logging.getLogger("database")
database_logger.setLevel(logging.DEBUG)

# Remove any existing handlers to avoid duplicates
for handler in database_logger.handlers[:]:
    database_logger.removeHandler(handler)

database_handler = logging.FileHandler(os.path.join(log_dir, "database.log"))
database_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)
database_logger.addHandler(database_handler)

# Get a logger for test output
logger = logging.getLogger("tests.database")
# Add a console handler for test output
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)
logger.setLevel(logging.DEBUG)


@pytest.fixture
def db() -> Generator[ChatDatabase, None, None]:
    """Create a new test database before each test."""
    test_db_path = "test_chat.db"
    logger.info(f"Creating test database at {test_db_path}")
    database = ChatDatabase(test_db_path)
    yield database
    # Cleanup after test
    if os.path.exists(test_db_path):
        logger.info(f"Cleaning up test database {test_db_path}")
        os.remove(test_db_path)


@pytest.fixture
def users(db: ChatDatabase) -> List[str]:
    """Create test users."""
    test_users = ["alice", "bob", "charlie", "david"]
    logger.info(f"Creating {len(test_users)} test users: {', '.join(test_users)}")
    for user in test_users:
        db.create_user(user, "password123")
    return test_users


def test_create_user(db: ChatDatabase) -> None:
    """Test user creation and duplicate prevention."""
    logger.info("Testing user creation and duplicate prevention")

    # Test successful user creation
    logger.debug("Attempting to create a new user 'testuser'")
    success, msg = db.create_user("testuser", "password123")
    logger.debug(f"Result: success={success}, message='{msg}'")

    assert success
    assert msg == "User created successfully"

    # Test duplicate username
    logger.debug("Attempting to create a duplicate user 'testuser'")
    success, msg = db.create_user("testuser", "different_password")
    logger.debug(f"Result: success={success}, message='{msg}'")

    assert not success
    assert msg == "Username already exists"

    logger.info("User creation test completed successfully")


def test_verify_user(db: ChatDatabase) -> None:
    """Test user verification with correct and incorrect credentials."""
    logger.info("Testing user verification with correct and incorrect credentials")

    # Create a test user
    logger.debug("Creating test user 'testuser'")
    db.create_user("testuser", "password123")

    # Test correct password
    logger.debug("Testing login with correct password")
    success, msg = db.verify_user("testuser", "password123")
    logger.debug(f"Result: success={success}, message='{msg}'")

    assert success
    assert msg == "Login successful"

    # Test incorrect password
    logger.debug("Testing login with incorrect password")
    success, msg = db.verify_user("testuser", "wrong_password")
    logger.debug(f"Result: success={success}, message='{msg}'")

    assert not success
    assert msg == "Invalid password"

    # Test non-existent user
    logger.debug("Testing login with non-existent user")
    success, msg = db.verify_user("nonexistent", "password123")
    logger.debug(f"Result: success={success}, message='{msg}'")

    assert not success
    assert msg == "User not found"

    logger.info("User verification test completed successfully")


def test_list_accounts(db: ChatDatabase, users: List[str]) -> None:
    """Test account listing with and without pattern matching."""
    logger.info("Testing account listing functionality")

    # Test listing all accounts
    logger.debug("Testing listing all accounts")
    accounts = db.list_accounts(pattern=None)  # Explicitly pass None as pattern
    logger.debug(f"Found {len(accounts)} accounts")

    assert len(accounts) == len(users)
    usernames = [account["username"] for account in accounts]
    for user in users:
        assert user in usernames

    # Test pattern matching
    logger.debug("Testing pattern matching with 'li'")
    accounts = db.list_accounts(pattern="li")  # Should match "alice" and "charlie"
    logger.debug(f"Found {len(accounts)} accounts matching 'li'")

    assert len(accounts) == 2
    usernames = [account["username"] for account in accounts]
    assert "alice" in usernames
    assert "charlie" in usernames

    logger.info("Account listing test completed successfully")


def test_delete_account(db: ChatDatabase) -> None:
    """Test account deletion and its effects on messages."""
    # Create users
    db.create_user("sender", "password123")
    db.create_user("recipient", "password123")

    # Send a test message
    db.send_message("sender", "recipient", "Test message", "msg1")

    # Delete sender's account
    success, msg = db.delete_account("sender")
    assert success
    assert msg == "Account deleted successfully"

    # Verify sender account no longer exists
    success, _ = db.verify_user("sender", "password123")
    assert not success

    # Verify message is no longer accessible
    messages = db.get_messages("recipient")
    assert len(messages) == 0


def test_send_and_get_messages(db: ChatDatabase) -> None:
    """Test sending and receiving messages."""
    # Create users
    db.create_user("sender", "password123")
    db.create_user("recipient", "password123")

    # Send messages with a small delay to ensure different timestamps
    db.send_message("sender", "recipient", "Message 1", "msg1")
    time.sleep(0.1)  # Add delay between messages
    db.send_message("sender", "recipient", "Message 2", "msg2")

    # Get messages
    messages = db.get_messages("recipient")
    assert len(messages) == 2
    assert messages[0]["content"] == "Message 2"  # Most recent first
    assert messages[1]["content"] == "Message 1"

    # Verify message attributes
    for message in messages:
        assert message["sender"] == "sender"
        assert message["recipient"] == "recipient"
        assert message["delivered"]


def test_delete_messages(db: ChatDatabase) -> None:
    """Test message deletion."""
    # Create users and messages
    db.create_user("sender", "password123")
    db.create_user("recipient", "password123")
    db.send_message("sender", "recipient", "Message 1", "msg1")
    db.send_message("sender", "recipient", "Message 2", "msg2")

    # Delete one message
    success, failed_ids = db.delete_messages(["msg1"], "recipient")
    assert success
    assert len(failed_ids) == 0

    # Verify only one message remains
    messages = db.get_messages("recipient")
    assert len(messages) == 1
    assert messages[0]["message_id"] == "msg2"


def test_session_management(db: ChatDatabase) -> None:
    """Test session creation, verification, and deletion."""
    # Create a test user
    db.create_user("testuser", "password123")

    # Create session
    session_token = "test_session_token"
    success = db.create_session("testuser", session_token)
    assert success

    # Verify valid session
    username = db.verify_session(session_token)
    assert username == "testuser"

    # Delete session
    success = db.delete_session(session_token)
    assert success

    # Verify session no longer valid
    username = db.verify_session(session_token)
    assert username is None


def test_unread_message_count(db: ChatDatabase) -> None:
    """Test unread message counting."""
    # Create users
    db.create_user("sender", "password123")
    db.create_user("recipient", "password123")

    # Send messages
    db.send_message("sender", "recipient", "Message 1", "msg1")
    db.send_message("sender", "recipient", "Message 2", "msg2")

    # Check unread count before reading
    count = db.get_unread_message_count("recipient")
    assert count == 2

    # Read messages
    db.get_messages("recipient")

    # Check unread count after reading
    count = db.get_unread_message_count("recipient")
    assert count == 0


def test_send_message_to_nonexistent_user(db: ChatDatabase) -> None:
    """Test sending message to non-existent user."""
    db.create_user("sender", "password123")
    success, msg = db.send_message("sender", "nonexistent", "Test message", "msg1")
    assert not success
    assert msg == "Recipient not found"


def test_concurrent_message_operations(db: ChatDatabase) -> None:
    """Test message operations with multiple users."""
    # Create users
    users = ["user1", "user2", "user3"]
    for user in users:
        db.create_user(user, "password123")

    # Send multiple messages between users
    message_ids = []
    for i in range(5):
        for sender in users:
            for recipient in users:
                if sender != recipient:
                    msg_id = f"msg_{sender}_{recipient}_{i}"
                    db.send_message(sender, recipient, f"Message {i}", msg_id)
                    message_ids.append(msg_id)

    # Verify message counts
    for user in users:
        messages = db.get_messages(user)
        expected_count = 20  # (2 other users * 5 messages each) * 2 directions
        assert len(messages) == expected_count


def test_session_expiry(db: ChatDatabase) -> None:
    """Test session expiration."""
    # Create user
    db.create_user("testuser", "pass123")

    # Create session with very short expiry
    session_token = "test_session_token"
    with db.get_connection() as conn:
        current_time = int(time.time())
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO sessions (session_token, username, created_at, expires_at)
            VALUES (?, ?, ?, ?)
        """,
            (
                session_token,
                "testuser",
                current_time,
                current_time - 3600,  # Expired 1 hour ago
            ),
        )
        conn.commit()

    # Verify session has expired
    assert db.verify_session(session_token) is None


def test_thread_local_connections(db: ChatDatabase) -> None:
    """Test that thread-local connections work correctly."""
    # Create a user in the main thread
    db.create_user("thread_test_user", "password123")

    # Function to run in a separate thread
    def thread_function(success_list: List[bool]) -> None:
        # Verify the user exists
        success, _ = db.verify_user("thread_test_user", "password123")
        success_list.append(success)

        # Create another user from this thread
        success, _ = db.create_user("thread_created_user", "password123")
        success_list.append(success)

    # Run the function in a separate thread
    success_results: List[bool] = []
    thread = threading.Thread(target=thread_function, args=(success_results,))
    thread.start()
    thread.join()

    # Verify results
    assert len(success_results) == 2
    assert all(success_results), "Thread operations should succeed"

    # Verify the user created in the thread is accessible from the main thread
    success, _ = db.verify_user("thread_created_user", "password123")
    assert success, "User created in thread should be accessible from main thread"
