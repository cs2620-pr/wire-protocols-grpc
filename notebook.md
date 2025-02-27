# Engineering Notebook Entry: Re-Implementing our Chat Application with gRPC

*by Pranav Ramesh and Mohamed Zidan Cassim*

---

### Objective
For this exercise, we decided to re-implement our previous chat application, replacing our custom wire protocol/JSON approach with gRPC. We wanted to see how this would affect application complexity, data size, architecture, and testing. This notebook documents our findings and the challenges we faced along the way.

---

### Implementation Approach

#### 1. Migration from Sockets to gRPC
- Our original socket implementation used broadcasting, which worked great. When we started migrating to gRPC, we quickly hit our first roadblock: gRPC is primarily designed for polling, not broadcasting! Fortunately, we had implemented polling in a previous iteration before deciding on broadcasting, so we had some code to fall back on.
- Our original implementation was pretty bare-bones: raw sockets and JSON for message serialization.
- With gRPC, we now had Remote Procedure Calls over HTTP/2 with Protocol Buffers (protobuf) handling serialization.
- The biggest difference was that we no longer had to deal with the headache of low-level socket programming. Instead, we defined service contracts in Protobuf and let the system generate client and server stubs for us.

##### 1.1 Broadcasting in the Original Implementation

In our original socket-based implementation, we used a broadcasting approach where the server would actively push messages to clients. This worked really well for a chat application, where you want messages to appear instantly. Here's how we did it with the `send_to_recipients` method:

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

This approach had some nice advantages:
- Messages appeared instantly for online users (no lag!)
- Efficient for active chats since we only sent each message once per recipient
- Conceptually straightforward: server tells clients when something happens

We kept track of everything with these simple dictionaries:

```python
self.clients: Dict[socket.socket, str] = {}  # socket -> username
self.usernames: Dict[str, socket.socket] = {}  # username -> socket
```

##### 1.2 Transition to Polling with gRPC

With gRPC, we hit a wall trying to implement the same broadcasting pattern. While gRPC does support server streaming, we found the polling approach was simpler given our timeframe. So we switched to a model where clients periodically ask "got anything new for me?"

We implemented client-side polling with this method:

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

This gets called every few seconds to:
1. Check who's online
2. See if there are new messages in the current conversation

On the server side, we implemented a `GetMessages` endpoint that returns all relevant messages:

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

The client then filters these to show only what's relevant:

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

##### 1.3 The Trade-offs We Found

**Broadcasting (Our Original Approach)**: 

Pros:
- Messages appeared instantly - much better user experience
- Less network traffic when conversations are active
- Felt more "chat-like" with immediate message delivery

Cons:
- We spent way too much time debugging socket connection issues
- Had to write our own protocol from scratch
- Would be a nightmare to scale beyond a classroom demo

**Polling (Our gRPC Approach)**:

Pros:
- So much simpler to implement! Less hair-pulling debugging sessions
- Better scaling potential with standard HTTP/2 infrastructure
- Handles reconnections automatically (huge win!)
- More robust when networks get flaky

Cons:
- Messages have a slight delay (up to our polling interval)
- More network traffic since we're checking for updates constantly
- Wastes bandwidth for inactive users who are still polling

We did try to be smart about polling by only updating the UI when something changed:

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
- Instead of wrestling with socket connections, our client now makes simple RPC calls defined in our `.proto` file.
- Message passing follows a nice, structured request/response pattern.
- We could have used streaming for real-time interactions, but didn't get to implement that in our timeframe.

**Server:**
- No more dealing with socket management or custom JSON parsing headaches.
- Just implements the service methods we defined in the `.proto` file.
- Multiple clients are handled automatically by gRPC's concurrency management.

#### 3. Session Management Differences

In our socket implementation, sessions were tied directly to socket connections, which was fragile:

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

With gRPC, we switched to session tokens independent of connections, which was much more robust:

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

This was a huge improvement - users could disconnect and reconnect without losing their session. Much better for real-world usage where connections drop all the time.

---

### Comparative Analysis

#### 1. Ease of Development
- **Way Easier:** Using gRPC saved us so much time that would have gone into socket management and protocol design.
- **Auto-Generated Code FTW:** Defining our `.proto` file and letting it generate client and server stubs was magical compared to writing all that code by hand.
- **Clear Contracts:** The `.proto` file served as documentation, contract, and code generation all in one - super helpful when we were splitting work.

#### 2. Data Size and Efficiency
- **Surprising Results:** We were shocked when we measured the actual network traffic between our different implementations.
- **Theory vs. Reality:** While Protobuf is supposed to be more efficient than JSON, our particular implementation showed some unexpected results.

##### 2.1 Protocol Efficiency Analysis

We measured all three protocols we tried throughout this project:

| Protocol | Total Messages | Total Bytes | Avg Size (bytes) |
|-------------|--------------|------------|----------------|
| gRPC | 3,023 | 1,615,231 | 534.53 |
| JSONProtocol | 7,288 | 1,734,544 | 238.00 |
| CustomWireProtocol | 9,202 | 495,293 | 53.82 |

###### Operation-Specific Statistics

| Operation | gRPC Count | gRPC Avg Size (bytes) | JSON Avg Size (bytes) | CustomWire Avg Size (bytes) |
|--------------------------|-----------|-------------------|-------------------|---------------------|
| GetMessages | 1,771 | 880.71 | 231.48 | 49.02 |
| ListAccounts | 984 | 51.14 | - | - |
| MarkConversationAsRead | 152 | 23.59 | 237.58 | 50.10 |
| SendMessage | 75 | 48.96 | 242.11 | 63.40 |
| Login | 25 | 23.48 | 244.19 | 67.88 |
| Logout | 16 | 20.00 | 233.28 | 49.24 |

###### Message Size Analysis

- **Wait, What?** To our surprise, gRPC messages averaged 534.53 bytes, way bigger than our CustomWireProtocol (53.82 bytes) and even JSONProtocol (238.00 bytes).
- **The GetMessages Problem:** Looking deeper, we found that GetMessages in gRPC was a bandwidth hog at 880.71 bytes per request. This was because our implementation grabbed all messages for a user at once instead of just new ones.

###### Efficiency Analysis

- **Bandwidth Comparison:**
  - JSON messages were 3.4× larger than our custom protocol
  - gRPC messages were 2.2× larger than JSON and a whopping 9.9× larger than our custom protocol
  - If we scaled to 1 million messages:
    - CustomWireProtocol: 51.3 MB
    - JSONProtocol: 227.0 MB
    - gRPC: 534.5 MB

This was a real eye-opener for us. gRPC is supposed to be efficient, but our implementation ended up being the most bandwidth-hungry of all three approaches!

- **Operation-by-Operation:**
  - GetMessages was our biggest bandwidth consumer in gRPC
  - SendMessage in gRPC (48.96 bytes) was actually much smaller than JSON (242.11 bytes)
  - Login, Logout, and MarkConversationAsRead in gRPC were all smaller than JSON too

###### What This Means for Scaling

Given how much larger our gRPC messages were, we'd have higher network costs in a real deployment. But gRPC's HTTP/2 foundation would probably still give us better performance where raw throughput matters more than bandwidth usage.

#### 3. Client and Server Changes
| Aspect            | Custom Sockets & JSON | gRPC |
|------------------|---------------------|------|
| Message Handling | Tons of manual work | Handled automatically |
| Networking       | Socket nightmares | Works like magic |
| Data Format      | JSON (readable but big) | Protobuf (compact but binary) |
| API Contracts    | Hope and pray | Clearly defined in `.proto` |
| Error Handling   | DIY | Built-in status codes |
| Message Delivery | Broadcasting (push) | Polling (pull) |
| Connection Management | Reconnect? Good luck! | Mostly automatic |

#### 4. Testing Considerations
- **Much Easier Unit Testing:**
  - The structured API made it simple to test individual components
  - We could mock requests and verify responses without complex setup
- **Integration Testing:**
  - gRPC tools made monitoring API calls much easier
  - HTTP/2 support simplified load testing
- **Debugging Reality Check:**
  - Binary protocols are harder to debug by eye
  - We had to use tools like `grpcurl` to see what was happening

---

### Conclusion
Switching to gRPC was definitely a win for developer productivity. We spent way less time wrestling with networking code and more time on actual application features. 

The biggest surprise was our message size measurements. While we expected gRPC to be more efficient, our implementation actually used more bandwidth than both JSON and our custom protocol. This was mostly due to how we designed our GetMessages operation - a good reminder that architectural decisions can override theoretical protocol efficiencies.

The shift from broadcasting to polling changed the feel of our application. Messages now have a slight delay before appearing, but the system is more robust against connection issues, which is probably worth the trade-off in a real-world app.

Overall, we'd definitely use gRPC again for similar projects. The development speed gains were substantial, and with some tweaking of our message retrieval approach, we could probably address the bandwidth concerns.

---

### Direct Answers to Design Exercise Questions

#### Does the use of gRPC make the application easier or more difficult?

**Mostly easier:**
- Development time was cut drastically with auto-generated code
- The `.proto` file was like having instant documentation
- Connection management headaches disappeared
- Session handling became much more robust

**A few things were harder:**
- Debugging binary messages was a pain compared to JSON
- We had to learn Protobuf syntax and gRPC concepts
- Understanding the different streaming options took some time

#### What does gRPC do to the size of the data passed?

We were pretty surprised by what we found:
- We expected gRPC/Protobuf to be smaller than JSON but larger than our custom protocol
- In reality, our gRPC implementation averaged 534.53 bytes per message, compared to 238.00 bytes for JSON and 53.82 bytes for our custom protocol

The main reasons for this:
1. Our GetMessages implementation was inefficient, grabbing all messages at once
2. HTTP/2 headers and gRPC metadata added overhead
3. Our polling approach meant frequent large responses

For smaller operations like Login and SendMessage, gRPC was more efficient than JSON, which matched our expectations.

#### How does it change the structure of the client and server?

**Client-side:**
- No more socket management code - big win!
- Error handling became more structured with proper status codes
- We switched from receiving pushed updates to asking for updates
- Session handling became more robust, allowing for reconnections

**Server-side:**
- Gone were the days of manually parsing JSON
- We just implemented interfaces defined in our `.proto` file
- Session management became separate from connection state
- Thread management was handled automatically by gRPC

#### How does this change the testing of the application?

**Testing got easier:**
- We could write unit tests with mock services
- The generated stubs made testing server logic straightforward
- Request/response formats were validated automatically
- Components were more isolated, making targeted testing easier

**Some new challenges:**
- We needed special tools for manual testing
- Binary formats made visual inspection harder
- Network simulation became more complex with HTTP/2

### Our Take on gRPC

After this project, here's what we think:

- **Implementation:** So much easier than socket programming!
- **Debugging:** Definitely harder with binary messages
- **Efficiency:** Could be efficient, but our implementation choices led to larger messages
- **Testing:** Definitely easier and more structured

The biggest lesson? Protocol choice matters, but implementation details matter more. Just switching to gRPC didn't automatically make our app more efficient - we would need to rethink our approach to message retrieval to really get the benefits.

