import grpc  # type: ignore
from concurrent import futures
import time
import uuid
import logging
import argparse
from typing import Dict, List, Tuple, Optional, cast
import sys

from .chat.chat_pb2 import (
    CreateAccountRequest,
    CreateAccountResponse,
    LoginRequest,
    LoginResponse,
    ListAccountsRequest,
    ListAccountsResponse,
    AccountInfo,
    DeleteAccountRequest,
    DeleteAccountResponse,
    SendMessageRequest,
    SendMessageResponse,
    GetMessagesRequest,
    GetMessagesResponse,
    DeleteMessagesRequest,
    DeleteMessagesResponse,
    Message,
    LogoutRequest,
    LogoutResponse,
    MarkConversationAsReadRequest,
    MarkConversationAsReadResponse,
)
from .chat.chat_pb2_grpc import ChatServiceServicer, add_ChatServiceServicer_to_server
from .database import ChatDatabase  # type: ignore
from .constants import ErrorMessage, SuccessMessage

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Change to DEBUG if you need more details
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.FileHandler("server.log"),  # Save logs to a file
        logging.StreamHandler()  # Also print logs to the console
    ],
)

logger = logging.getLogger("server")  # Use a specific logger for clarity

# Capture logs from database.py as well
logging.getLogger("database").setLevel(logging.INFO)



class ChatServicer(ChatServiceServicer):
    def __init__(self, db_path: str = "chat.db") -> None:
        self.db = ChatDatabase(db_path)
        # In-memory cache of online users and their session tokens
        self.online_users: Dict[str, str] = {}  # username -> session_token

    def CreateAccount(
        self,
        request: CreateAccountRequest,
        context: grpc.ServicerContext,
    ) -> CreateAccountResponse:
        """Handle account creation request."""
        logger.info(f"Creating account for user: {request.username}")
        success, message = self.db.create_user(request.username, request.password)

        return CreateAccountResponse(
            success=success, error_message=message if not success else ""
        )

    def Login(
        self,
        request: LoginRequest,
        context: grpc.ServicerContext,
    ) -> LoginResponse:
        """Handle login request."""
        logger.info(f"Login attempt for user: {request.username}")
        success, message = self.db.verify_user(request.username, request.password)

        if not success:
            return LoginResponse(success=False, error_message=message)

        # Generate session token
        session_token = str(uuid.uuid4())
        self.db.create_session(request.username, session_token)
        self.online_users[request.username] = session_token

        # Get unread message count
        unread_count = self.db.get_unread_message_count(request.username)

        return LoginResponse(
            success=True,
            error_message="",
            unread_message_count=unread_count,
            session_token=session_token,
        )

    def ListAccounts(
        self,
        request: ListAccountsRequest,
        context: grpc.ServicerContext,
    ) -> ListAccountsResponse:
        """Handle account listing request."""
        # Verify session
        username = self.db.verify_session(request.session_token)
        if not username:
            return ListAccountsResponse(
                error_message=ErrorMessage.INVALID_SESSION.value
            )

        # Get accounts
        accounts = self.db.list_accounts(
            pattern=request.pattern if request.pattern else None,
            limit=request.page_size,
            offset=request.page_size * request.page_number,
        )

        # Convert to proto format
        account_infos = []
        for account in accounts:
            is_online = account["username"] in self.online_users
            account_infos.append(
                AccountInfo(username=account["username"], is_online=is_online)
            )

        return ListAccountsResponse(
            accounts=account_infos,
            has_more=len(accounts) == request.page_size,
            total_count=len(accounts),
            error_message="",
        )

    def DeleteAccount(
        self,
        request: DeleteAccountRequest,
        context: grpc.ServicerContext,
    ) -> DeleteAccountResponse:
        """Handle account deletion request."""
        # Verify session
        username = self.db.verify_session(request.session_token)
        if not username:
            return DeleteAccountResponse(
                success=False, error_message=ErrorMessage.INVALID_SESSION.value
            )

        # Log the account deletion attempt
        print(
            f"ACCOUNT DELETION: User '{username}' is attempting to delete their account"
        )

        # Delete account
        success, message = self.db.delete_account(username)
        if success:
            # Log successful deletion
            print(
                f"ACCOUNT DELETION SUCCESSFUL: User '{username}' has deleted their account"
            )

            # Remove from online users if present
            self.online_users.pop(username, None)
            # Delete session
            self.db.delete_session(request.session_token)
        else:
            # Log failed deletion
            print(
                f"ACCOUNT DELETION FAILED: User '{username}' failed to delete their account. Reason: {message}"
            )

        return DeleteAccountResponse(
            success=success, error_message=message if not success else ""
        )

    def SendMessage(
        self,
        request: SendMessageRequest,
        context: grpc.ServicerContext,
    ) -> SendMessageResponse:
        """Handle message sending request with logging."""
        
        request_size = len(request.SerializeToString())  # Log request size
        logger.info(f"GRPC Incoming - SendMessage - Size: {request_size} bytes | Sender: {request.session_token} -> Recipient: {request.recipient}")

        # Verify session
        username = self.db.verify_session(request.session_token)
        if not username:
            response = SendMessageResponse(
                success=False, error_message=ErrorMessage.INVALID_SESSION.value
            )
            response_size = len(response.SerializeToString())  # Log response size
            logger.info(f"GRPC Outgoing - SendMessage (Error) - Size: {response_size} bytes | Invalid session")
            return response

        # Generate message ID
        message_id = str(uuid.uuid4())

        # Send message
        success, message = self.db.send_message(
            sender=username,
            recipient=request.recipient,
            content=request.content,
            message_id=message_id,
        )

        response = SendMessageResponse(
            success=success,
            error_message=message if not success else "",
            message_id=message_id if success else "",
        )

        response_size = len(response.SerializeToString())  # Log response size
        logger.info(f"GRPC Outgoing - SendMessage - Size: {response_size} bytes | Success: {success}")

        return response

    def GetMessages(
        self,
        request: GetMessagesRequest,
        context: grpc.ServicerContext,
    ) -> GetMessagesResponse:
        """Handle message retrieval request with logging."""
        
        request_size = len(request.SerializeToString())  # Log request size
        logger.info(f"GRPC Incoming - GetMessages - Size: {request_size} bytes | Session Token: {request.session_token}")

        # Verify session
        username = self.db.verify_session(request.session_token)
        if not username:
            response = GetMessagesResponse(error_message=ErrorMessage.INVALID_SESSION.value)
            response_size = len(response.SerializeToString())  # Log response size
            logger.info(f"GRPC Outgoing - GetMessages (Error) - Size: {response_size} bytes | Invalid session")
            return response

        # Get messages
        messages = self.db.get_messages(username=username, limit=request.max_messages)

        # Convert to proto format
        message_protos = []

        # Track unique conversation partners to mark messages as read
        conversation_partners = set()

        for msg in messages:
            message_protos.append(
                Message(
                    message_id=msg["message_id"],
                    sender=msg["sender"],
                    recipient=msg["recipient"],
                    content=msg["content"],
                    timestamp=msg["timestamp"],
                    delivered=msg["delivered"],
                    unread=msg["unread"],
                    deleted=msg["deleted"],
                )
            )

            # Track conversation partners
            if msg["sender"] != username:
                conversation_partners.add(msg["sender"])
            if msg["recipient"] != username:
                conversation_partners.add(msg["recipient"])

        response = GetMessagesResponse(
            messages=message_protos,
            has_more=len(messages) == request.max_messages,
            error_message="",
        )

        response_size = len(response.SerializeToString())  # Log response size
        logger.info(f"GRPC Outgoing - GetMessages - Size: {response_size} bytes | Retrieved {len(messages)} messages")

        return response

    def DeleteMessages(
        self,
        request: DeleteMessagesRequest,
        context: grpc.ServicerContext,
    ) -> DeleteMessagesResponse:
        """Handle message deletion request."""
        # Verify session
        username = self.db.verify_session(request.session_token)
        if not username:
            return DeleteMessagesResponse(
                success=False, error_message=ErrorMessage.INVALID_SESSION.value
            )

        # Delete messages
        success, failed_ids = self.db.delete_messages(
            message_ids=request.message_ids, username=username
        )

        # Provide a specific error message if deletion failed
        error_message = ""
        if not success:
            error_message = ErrorMessage.FAILED_DELETE_MESSAGES.value
        elif failed_ids:
            error_message = "You can only delete messages that you sent."

        return DeleteMessagesResponse(
            success=success and not failed_ids,
            error_message=error_message,
            failed_message_ids=failed_ids,
        )

    def Logout(
        self,
        request: LogoutRequest,
        context: grpc.ServicerContext,
    ) -> LogoutResponse:
        """Handle logout request."""
        # Verify session
        username = self.db.verify_session(request.session_token)
        if not username:
            return LogoutResponse(
                success=False, error_message=ErrorMessage.INVALID_SESSION.value
            )

        # Log the logout attempt
        logger.info(f"Logout attempt for user: {username}")

        # Delete session from database
        success = self.db.delete_session(request.session_token)

        # Remove from online users cache
        if username in self.online_users:
            del self.online_users[username]

        return LogoutResponse(
            success=success, error_message="" if success else "Failed to logout"
        )

    def MarkConversationAsRead(
        self,
        request: MarkConversationAsReadRequest,
        context: grpc.ServicerContext,
    ) -> MarkConversationAsReadResponse:
        """Handle marking a conversation as read."""
        # Verify session
        username = self.db.verify_session(request.session_token)
        if not username:
            return MarkConversationAsReadResponse(
                success=False, error_message=ErrorMessage.INVALID_SESSION.value
            )

        # Mark conversation as read
        success = self.db.mark_conversation_as_read(username, request.other_user)

        return MarkConversationAsReadResponse(
            success=success,
            error_message="" if success else "Failed to mark conversation as read",
        )


def serve(
    host: str = "localhost",
    port: int = 50051,
    max_workers: int = 10,
    db_path: str = "chat.db",
) -> None:
    """Start the gRPC server."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    add_ChatServiceServicer_to_server(ChatServicer(db_path), server)
    server_address = f"{host}:{port}"

    try:
        # Try to bind to the specified port
        server.add_insecure_port(server_address)
        server.start()
        logger.info(f"Server started on {server_address}")

        try:
            server.wait_for_termination()
        except KeyboardInterrupt:
            logger.info("Shutting down server...")
            server.stop(0)
    except Exception as e:
        logger.error(f"Failed to start server on {server_address}: {str(e)}")
        print(f"ERROR: Failed to start server on {server_address}: {str(e)}")

        # Check for common errors and provide helpful messages
        if "address already in use" in str(e).lower():
            print(
                f"The port {port} is already in use. Try a different port with --port option."
            )
        elif "cannot assign requested address" in str(e).lower():
            print(f"Cannot bind to address {host}. Make sure the host is valid.")

        # Exit with error code
        sys.exit(1)


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Chat Server")
    parser.add_argument(
        "--host", default="localhost", help="Host address to bind the server to"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port number to listen on"
    )
    parser.add_argument(
        "--protocol",
        default="json",
        choices=["json", "custom"],
        help="Protocol type to use (choices: json, custom)",
    )
    parser.add_argument(
        "--db-path", default="chat.db", help="Path to the SQLite database file"
    )

    args = parser.parse_args()

    # Note: The protocol argument is included for compatibility but not used in gRPC implementation
    if args.protocol != "json":
        logger.warning(
            f"Protocol '{args.protocol}' specified, but this server uses gRPC"
        )

    # Validate port number
    if args.port < 1 or args.port > 65535:
        print(
            f"ERROR: Invalid port number {args.port}. Port must be between 1 and 65535."
        )
        sys.exit(1)

    # Print startup message
    print(f"Starting server on {args.host}:{args.port}...")
    print(f"Using database: {args.db_path}")
    print("Press Ctrl+C to stop the server")

    serve(host=args.host, port=args.port, db_path=args.db_path)
