**Engineering Notebook Entry: Re-Implementing our Chat Application with gRPC**

*by Pranav Ramesh and Mohamed Zidan Cassim*

---

### Objective
The goal of this exercise is to re-implement our previously designed chat application, by replacing the use of sockets and our custom wire protocol/JSON with a gRPC implementation. This document examines the impact of this transition on application complexity, data size, client and server architecture, and testing.

---

### Implementation Approach

#### 1. Migration from Sockets to gRPC
- Our original implementation used broadcasting, and we quickly realized that gRPC is primarily used for polling. However, we had also implemented polling in a previous iteration before deciding that broadcasting was a better design choice, and were able to refer back to and utilize some aspects of this implementation.
- The original implementation utilized raw sockets and JSON for message serialization.
- gRPC replaces this with Remote Procedure Calls (RPC) over HTTP/2, leveraging Protocol Buffers (protobuf) for data serialization.
- Instead of handling low-level socket programming, the application now defines service contracts via Protobuf and auto-generates client and server stubs.

#### 2. Changes to Client and Server Structure
**Client:**
- Instead of directly managing socket connections, the client now calls remote procedures defined in the `.proto` file.
- Message passing follows a structured RPC request/response model.
- Streaming messages can be used for real-time interactions (e.g., bidirectional streaming for chat messages).

**Server:**
- No longer needs to handle raw socket connections or custom JSON parsing.
- Implements gRPC service methods as defined in the `.proto` file.
- Can support multiple clients via gRPC’s built-in concurrency management.

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
Replacing raw sockets and JSON with gRPC significantly improves the development experience, reduces message size, and provides a well-structured API. However, debugging can be slightly more challenging due to Protobuf’s binary nature. Testing is simplified through built-in request validation, structured API contracts, and gRPC’s support for bidirectional streaming and multiplexing.

Overall, the migration to gRPC makes the chat application more maintainable and scalable, while also improving performance and security.

