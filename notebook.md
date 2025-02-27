**Engineering Notebook Entry: Re-Implementing our Chat Application with gRPC**

*by Pranav Ramesh and Mohamed Zidan Cassim*

---

### Objective
The goal of this exercise was to re-implement our previously designed chat application, by replacing the use of sockets and our custom wire protocol/JSON with a gRPC implementation. This document examines the impact of this transition on application complexity, data size, client and server architecture, and testing.

---

### Implementation Approach

#### 1. Migration from Sockets to gRPC
- Our original implementation used broadcasting, and whilst trying to migrate this code to gRPC, we quickly realized that gRPC is primarily used for polling. However, we had also implemented polling in a previous iteration before deciding that broadcasting was a better design choice, and were able to refer back to and utilize some aspects of this implementation.
- The original implementation utilized raw sockets and JSON for message serialization.
- gRPC replaces this with Remote Procedure Calls (RPC) over HTTP/2, leveraging Protocol Buffers (protobuf) for data serialization.
- Instead of handling low-level socket programming, the application now defines service contracts via Protobuf and auto-generates client and server stubs.

##### 1.1 Broadcasting in the Original Implementation

In our socket-based implementation, we used a broadcasting approach where the server would actively push messages to connected clients without them having to request updates. This was implemented through the `send_to_recipients` method in our original server:

```python
def send_to_recipients(self, message: ChatMessage, exclude_socket=None):
    """Send message to specific recipients or broadcast if no recipients specified"""
    if message.message_type == MessageType.DM:
        self.handle_dm(message, exclude_socket)
        return

    with self.lock:
        if message.recipients:
            # Send to specific recipients
            for recipient in message.recipients:
                if recipient in self.usernames:
                    recipient_socket = self.usernames[recipient]
                    if recipient_socket != exclude_socket:
                        if not self.send_to_client(recipient_socket, message):
                            threading.Thread(
                                target=self.remove_client,
                                args=(recipient_socket, True),
                                daemon=True,
                            ).start()
        else:
            # Broadcast to all if no recipients specified
            clients_copy = list(self.clients.items())

    if not message.recipients:
        # Broadcast outside the lock to prevent deadlock
        for client_socket, username in clients_copy:
            if client_socket == exclude_socket:
                continue

            if not self.send_to_client(client_socket, message):
                threading.Thread(
                    target=self.remove_client,
                    args=(client_socket, True),
                    daemon=True,
                ).start()
```

This approach had several advantages:
- **Real-time updates**: Messages were delivered instantly to online users
- **Efficient for active chats**: Only one message transmission was needed per recipient
- **Simple mental model**: The server actively notified clients of new events

The implementation maintained mappings between sockets and usernames to efficiently deliver messages:

```python
self.clients: Dict[socket.socket, str] = {}  # socket -> username
self.usernames: Dict[str, socket.socket] = {}  # username -> socket
```

##### 1.2 Transition to Polling with gRPC

With gRPC, we found that implementing a broadcasting pattern was more complex, as the framework is primarily designed around a request-response model. While gRPC does support server streaming, we opted for a simpler polling-based approach where clients periodically request updates from the server.

The client-side polling is implemented in the `poll_for_updates` method:

```python
def poll_for_updates(self) -> None:
    """Poll for updates from the server."""
    try:
        # Update users list
        self.update_users_list()

        # Update messages if a user is selected
        if self.selected_user:
            self.update_messages()

        self.last_poll_time = time.time()
    except grpc.RpcError as e:
        print(f"Error polling for updates: {e}")
```

This method is called periodically (every few seconds) to:
1. Update the list of online users
2. Check for new messages when a conversation is open

The server implements a `GetMessages` endpoint that returns all messages for the requesting user:

```python
def GetMessages(self, request: GetMessagesRequest, context: grpc.ServicerContext) -> GetMessagesResponse:
    """Handle message retrieval request with logging."""
    
    # Verify session
    username = self.db.verify_session(request.session_token)
    if not username:
        response = GetMessagesResponse(error_message=ErrorMessage.INVALID_SESSION.value)
        return response

    # Get messages
    messages = self.db.get_messages(username=username, limit=request.max_messages)
    
    # Create response with all messages
    return GetMessagesResponse(messages=messages)
```

The client then filters these messages to display only those relevant to the current conversation:

```python
# Filter messages for the selected user
filtered_messages = []
for msg in response.messages:
    # Include messages where:
    # 1. Current user is sender and selected user is recipient
    # 2. Selected user is sender and current user is recipient
    if (
        msg.sender == self.username and msg.recipient == self.selected_user
    ) or (
        msg.sender == self.selected_user and msg.recipient == self.username
    ):
        filtered_messages.append(msg)
```

##### 1.3 Advantages and Disadvantages of Both Approaches

**Broadcasting (Original Approach)**:
- ✅ Lower latency for message delivery
- ✅ Less network traffic when conversations are active
- ✅ More "chat-like" behavior where messages appear immediately
- ❌ More complex server-side code to manage connections
- ❌ Requires custom protocol implementation
- ❌ Difficult to scale with many concurrent users

**Polling (gRPC Approach)**:
- ✅ Simpler client and server implementations
- ✅ Better scalability with standardized HTTP/2 infrastructure
- ✅ Automatic reconnection handling
- ✅ More robust against network issues
- ❌ Higher latency for message delivery
- ❌ Potentially more network traffic due to periodic polling
- ❌ Less efficient for inactive users (polling when no new messages)

We mitigated some of the disadvantages of polling by implementing intelligent update detection:

```python
# Check if messages have changed before updating display
if self._messages_changed(filtered_messages):
    self.messages = filtered_messages
    self._display_messages()
else:
    logger.info("No changes in messages, skipping display update")
```

#### 2. Changes to Client and Server Structure
**Client:**
- Instead of directly managing socket connections, the client now calls remote procedures defined in the `.proto` file.
- Message passing follows a structured RPC request/response model.
- Streaming messages can be used for real-time interactions (e.g., bidirectional streaming for chat messages).

**Server:**
- No longer needs to handle raw socket connections or custom JSON parsing.
- Implements gRPC service methods as defined in the `.proto` file.
- Can support multiple clients via gRPC's built-in concurrency management.

#### 3. Session Management Differences

In our socket-based implementation, user sessions were tied directly to socket connections:

```python
def handle_client(self, client_socket: socket.socket):
    username = None
    db = self.db()
    try:
        while self.running:
            # Authentication handling
            if username is None:
                # First message should be login or register
                # ...
                username = message.username
                with self.lock:
                    self.clients[client_socket] = username
                    self.usernames[username] = client_socket
```

In contrast, the gRPC implementation uses session tokens that are independent of the connection:

```python
def Login(self, request: LoginRequest, context: grpc.ServicerContext) -> LoginResponse:
    # Verify credentials
    success, message = self.db.verify_user(request.username, request.password)
    if not success:
        return LoginResponse(success=False, error_message=message)
    
    # Generate a session token
    session_token = str(uuid.uuid4())
    
    # Store session
    self.db.create_session(request.username, session_token)
    
    # Mark user as online
    self.online_users[request.username] = session_token
    
    return LoginResponse(
        success=True,
        session_token=session_token,
        username=request.username
    )
```

This approach provides more flexibility and allows clients to disconnect and reconnect without losing their session, making the application more robust against network issues.

---

### Impact Analysis

#### 1. Ease of Development
- **Easier:** The use of gRPC abstracts much of the low-level networking code, reducing the complexity of managing sockets, message serialization, and protocol handling.
- **Automatic Code Generation:** Protobuf definitions auto-generate client and server stubs, eliminating boilerplate code.
- **Clear API Definition:** The `.proto` file acts as a self-documenting contract, making it easier to maintain and extend.

#### 2. Data Size and Efficiency
- **Smaller:** Protobuf is more efficient than JSON, reducing payload sizes.
- **Binary Serialization:** Unlike JSON, which is text-based, Protobuf encodes data in a compact binary format.
- **Better Performance:** gRPC runs over HTTP/2, enabling multiplexed streams and lower latency.

#### 3. Client and Server Changes
| Aspect            | Custom Sockets & JSON | gRPC |
|------------------|---------------------|------|
| Message Handling | Custom parsing & validation | Handled by Protobuf |
| Networking       | Manual socket management | Automatic via gRPC library |
| Data Format      | JSON (larger, human-readable) | Protobuf (smaller, binary) |
| API Contracts    | Implicit | Explicit via `.proto` |
| Error Handling   | Manual | Built-in with status codes |
| Message Delivery | Broadcasting (push) | Polling (pull) |
| Connection Management | Manual reconnection logic | Automatic with HTTP/2 |

#### 4. Testing Considerations
- **Easier Unit Testing:**
  - The structured API provided by gRPC simplifies mocking requests.
  - gRPC supports automatic validation of request/response formats.
- **Integration Testing:**
  - gRPC tooling includes reflection and interceptors for monitoring API calls.
  - Load testing can benefit from built-in HTTP/2 support.
- **Debugging:**
  - Harder to debug than JSON-based APIs due to binary encoding.
  - Requires tools like `grpcurl` or `grpcui` to inspect messages.

---

### Conclusion
Replacing raw sockets and JSON with gRPC significantly improves the development experience, reduces message size, and provides a well-structured API. However, debugging can be slightly more challenging due to Protobuf's binary nature. Testing is simplified through built-in request validation, structured API contracts, and gRPC's support for bidirectional streaming and multiplexing.

The shift from broadcasting to polling represents a fundamental change in how messages are delivered, with trade-offs in terms of latency and efficiency. While broadcasting provides more immediate delivery, polling with gRPC offers better reliability and scalability.

Overall, the migration to gRPC makes the chat application more maintainable and scalable, while also improving performance and security.

