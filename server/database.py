import sqlite3
import time
import bcrypt  # type: ignore
from typing import List, Optional, Tuple, Dict, Any, Generator, Iterator, cast
from threading import Lock, local
from contextlib import contextmanager
import logging
from .constants import ErrorMessage, SuccessMessage
from typing import Optional

# Configure logging
logging.basicConfig(
    filename="database.log",  # Store logs in a file
    level=logging.INFO,  # Set log level to INFO
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("database")

class ChatDatabase:
    def __init__(self, db_path: str = "chat.db") -> None:
        self.db_path = db_path
        self._thread_local = local()
        self.lock = Lock()
        self.initialize_database()
        # Enable proper boolean handling
        sqlite3.register_adapter(bool, int)
        sqlite3.register_converter("BOOLEAN", lambda v: bool(int(v)))

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Thread-safe database connection context manager."""
        with self.lock:
            # Each thread gets its own connection
            if not hasattr(self._thread_local, "connection"):
                self._thread_local.connection = sqlite3.connect(
                    self.db_path, detect_types=sqlite3.PARSE_DECLTYPES
                )
                self._thread_local.connection.row_factory = sqlite3.Row
            try:
                yield self._thread_local.connection
            finally:
                pass  # Keep connection open for reuse

    def initialize_database(self) -> None:
        """Create database tables if they don't exist."""
        # Create a temporary connection just for initialization
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor: sqlite3.Cursor = conn.cursor()
            # Users table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    last_login INTEGER
                )
            """
            )

            # Messages table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    sender TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp BIGINT NOT NULL,
                    delivered BOOLEAN NOT NULL DEFAULT FALSE,
                    unread BOOLEAN NOT NULL DEFAULT TRUE,
                    deleted BOOLEAN NOT NULL DEFAULT FALSE,
                    FOREIGN KEY (sender) REFERENCES users(username),
                    FOREIGN KEY (recipient) REFERENCES users(username)
                )
            """
            )

            # Sessions table for managing active user sessions
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_token TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    FOREIGN KEY (username) REFERENCES users(username)
                )
            """
            )

            conn.commit()

            # Check if we need to add the unread column to an existing database
            cursor.execute("PRAGMA table_info(messages)")
            columns = [column[1] for column in cursor.fetchall()]
            if "unread" not in columns:
                cursor.execute(
                    "ALTER TABLE messages ADD COLUMN unread BOOLEAN NOT NULL DEFAULT TRUE"
                )
                conn.commit()

    # User Management Methods
    def create_user(self, username: str, password: str) -> Tuple[bool, str]:
        """Create a new user account."""
        try:
            with self.get_connection() as conn:
                cursor: sqlite3.Cursor = conn.cursor()
                # Check if username exists
                cursor.execute("SELECT 1 FROM users WHERE username = ?", (username,))
                if cursor.fetchone():
                    return False, ErrorMessage.USERNAME_EXISTS.value

                # Hash password
                password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

                # Create user
                cursor.execute(
                    """
                    INSERT INTO users (username, password_hash, created_at)
                    VALUES (?, ?, ?)
                """,
                    (username, password_hash.decode(), int(time.time())),
                )
                conn.commit()
                return True, SuccessMessage.USER_CREATED.value
        except Exception as e:
            return False, str(e)

    def verify_user(self, username: str, password: str) -> Tuple[bool, str]:
        """Verify user credentials."""
        try:
            with self.get_connection() as conn:
                cursor: sqlite3.Cursor = conn.cursor()
                cursor.execute(
                    "SELECT password_hash FROM users WHERE username = ?", (username,)
                )
                result = cursor.fetchone()

                if not result:
                    return False, ErrorMessage.USER_NOT_FOUND.value

                stored_hash = result["password_hash"].encode()
                if bcrypt.checkpw(password.encode(), stored_hash):
                    # Update last login
                    cursor.execute(
                        """
                        UPDATE users SET last_login = ? WHERE username = ?
                    """,
                        (int(time.time()), username),
                    )
                    conn.commit()
                    return True, SuccessMessage.LOGIN_SUCCESSFUL.value
                return False, ErrorMessage.INVALID_PASSWORD.value
        except Exception as e:
            return False, str(e)

    def list_accounts(
        self, pattern: Optional[str], limit: int = 50, offset: int = 0
    ) -> List[dict]:
        """List user accounts, optionally filtered by pattern."""
        try:
            with self.get_connection() as conn:
                cursor: sqlite3.Cursor = conn.cursor()
                if pattern:
                    query = """
                        SELECT username, last_login 
                        FROM users 
                        WHERE username LIKE ? 
                        ORDER BY username
                        LIMIT ? OFFSET ?
                    """
                    cursor.execute(query, (f"%{pattern}%", limit, offset))
                else:
                    query = """
                        SELECT username, last_login 
                        FROM users 
                        ORDER BY username
                        LIMIT ? OFFSET ?
                    """
                    cursor.execute(query, (limit, offset))

                return [dict(row) for row in cursor.fetchall()]
        except Exception:
            return []

    def delete_account(self, username: str) -> Tuple[bool, str]:
        """Delete a user account and all associated data."""
        try:
            with self.get_connection() as conn:
                cursor: sqlite3.Cursor = conn.cursor()
                # Delete user's sessions
                cursor.execute("DELETE FROM sessions WHERE username = ?", (username,))
                # Delete user's messages
                cursor.execute(
                    "DELETE FROM messages WHERE sender = ? OR recipient = ?",
                    (username, username),
                )
                # Delete user
                cursor.execute("DELETE FROM users WHERE username = ?", (username,))
                conn.commit()
                return True, SuccessMessage.ACCOUNT_DELETED.value
        except Exception as e:
            return False, str(e)

    # Message Management Methods
    def send_message(
        self, sender: str, recipient: str, content: str, message_id: str
    ) -> Tuple[bool, str]:
        """Store a new message with logging of message size and status."""
        try:
            with self.get_connection() as conn:
                cursor: sqlite3.Cursor = conn.cursor()

                # Verify recipient exists
                cursor.execute("SELECT 1 FROM users WHERE username = ?", (recipient,))
                if not cursor.fetchone():
                    logger.warning(f"Message failed: Recipient {recipient} does not exist.")
                    return False, ErrorMessage.RECIPIENT_DELETED.value

                # Calculate message size
                message_size = len(content.encode("utf-8"))

                # Log message details before insertion
                logger.info(
                    f"Storing message | Sender: {sender} -> Recipient: {recipient} | Message Size: {message_size} bytes | Message ID: {message_id}"
                )

                current_time = int(time.time() * 1000)  # Use milliseconds for better precision
                cursor.execute(
                    """
                    INSERT INTO messages (message_id, sender, recipient, content, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (message_id, sender, recipient, content, current_time),
                )
                conn.commit()

                logger.info(f"Message stored successfully | Message ID: {message_id}")

                return True, SuccessMessage.MESSAGE_SENT.value
        except Exception as e:
            logger.error(f"Database error while storing message from {sender} to {recipient}: {str(e)}")
            return False, str(e)


    def get_messages(self, username: str, limit: int = 50) -> List[dict]:
        """Get messages for a user."""
        try:
            with self.get_connection() as conn:
                cursor: sqlite3.Cursor = conn.cursor()
                # First, mark messages as delivered
                cursor.execute(
                    """
                    UPDATE messages 
                    SET delivered = TRUE 
                    WHERE recipient = ? AND deleted = FALSE
                """,
                    (username,),
                )
                conn.commit()

                # Then fetch both sent and received messages
                cursor.execute(
                    """
                    SELECT 
                        message_id,
                        sender,
                        recipient,
                        content,
                        timestamp,
                        delivered,
                        unread,
                        deleted
                    FROM messages
                    WHERE (recipient = ? OR sender = ?)
                    ORDER BY timestamp DESC
                    LIMIT ?
                """,
                    (username, username, limit),
                )
                messages = [dict(row) for row in cursor.fetchall()]
                return messages
        except Exception:
            return []

    def delete_messages(
        self, message_ids: List[str], username: str
    ) -> Tuple[bool, List[str]]:
        """Delete specified messages for a user."""
        failed_ids = []
        try:
            with self.get_connection() as conn:
                cursor: sqlite3.Cursor = conn.cursor()
                for msg_id in message_ids:
                    # Only allow deletion if the user is the sender
                    cursor.execute(
                        """
                        UPDATE messages 
                        SET deleted = 1
                        WHERE message_id = ? AND sender = ?
                    """,
                        (msg_id, username),
                    )
                    if cursor.rowcount == 0:
                        failed_ids.append(msg_id)
                conn.commit()
                return True, failed_ids
        except Exception as e:
            return False, message_ids

    def mark_conversation_as_read(self, username: str, other_user: str) -> bool:
        """Mark all messages in a conversation as read."""
        try:
            with self.get_connection() as conn:
                cursor: sqlite3.Cursor = conn.cursor()
                # Mark messages from the other user to this user as read
                cursor.execute(
                    """
                    UPDATE messages 
                    SET unread = FALSE 
                    WHERE sender = ? AND recipient = ? AND deleted = FALSE
                """,
                    (other_user, username),
                )
                conn.commit()
                return True
        except Exception as e:
            print(f"Error marking conversation as read: {e}")
            return False

    def get_unread_message_count_by_sender(self, username: str) -> Dict[str, int]:
        """Get count of unread messages for a user, grouped by sender."""
        try:
            with self.get_connection() as conn:
                cursor: sqlite3.Cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT sender, COUNT(*) as count 
                    FROM messages 
                    WHERE recipient = ? AND unread = TRUE AND deleted = FALSE
                    GROUP BY sender
                """,
                    (username,),
                )
                results = cursor.fetchall()
                return {row["sender"]: row["count"] for row in results}
        except sqlite3.Error as e:
            print(f"Error getting unread message count by sender: {e}")
            return {}

    # Session Management Methods
    def create_session(
        self, username: str, session_token: str, expiry_hours: int = 24
    ) -> bool:
        """Create a new session for a user."""
        try:
            with self.get_connection() as conn:
                current_time = int(time.time())
                cursor: sqlite3.Cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO sessions (session_token, username, created_at, expires_at)
                    VALUES (?, ?, ?, ?)
                """,
                    (
                        session_token,
                        username,
                        current_time,
                        current_time + (expiry_hours * 3600),
                    ),
                )
                conn.commit()
                return True
        except Exception:
            return False

    def verify_session(self, session_token: str) -> Optional[str]:
        """Verify a session token and return the associated username if valid."""
        try:
            with self.get_connection() as conn:
                cursor: sqlite3.Cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT username FROM sessions 
                    WHERE session_token = ? AND expires_at > ?
                """,
                    (session_token, int(time.time())),
                )
                result = cursor.fetchone()
                return result["username"] if result else None
        except Exception:
            return None

    def delete_session(self, session_token: str) -> bool:
        """Delete a session."""
        try:
            with self.get_connection() as conn:
                cursor: sqlite3.Cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM sessions WHERE session_token = ?", (session_token,)
                )
                conn.commit()
                return True
        except Exception:
            return False

    def get_unread_message_count(self, username: str) -> int:
        """Get count of unread messages for a user."""
        try:
            with self.get_connection() as conn:
                cursor: sqlite3.Cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT COUNT(*) as count 
                    FROM messages 
                    WHERE recipient = ? AND delivered = 0 AND deleted = 0
                """,
                    (username,),
                )
                result = cursor.fetchone()
                return cast(int, result["count"]) if result else 0
        except sqlite3.Error as e:
            print(f"Error getting unread message count: {e}")
            return 0
