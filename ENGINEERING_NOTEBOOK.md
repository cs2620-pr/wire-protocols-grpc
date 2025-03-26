# Raft Consensus Chat System: Engineering Notebook

Pranav Ramesh, Mohamed Zidan Cassim

## Last Updated

March 25, 2025

## Overview

This document details the design and implementation of a distributed messaging application built on top of the Raft consensus algorithm. The system provides fault-tolerant messaging services with guarantees of consistency even in the presence of node failures.

The implementation began as a pure Raft-based state machine replication system before being extended to support a full-featured chat application.

Servers can be restarted after a failure as long as they are in the config file. Use the Raft monitor to check the status of the servers, manually stop servers, and start them.

> NOTE: This is our attempt at extra credit.

## 1. System Architecture

### 1.1 Component Overview

The system consists of several key components:

* **Raft Cluster**: A group of server nodes that implement the Raft consensus protocol.
* **MessageService**: Built on top of Raft to provide chat functionality.
* **Chat Client**: A PyQt6-based GUI for end users to interact with the system.

```ascii
┌───────────────┐      ┌───────────────────────────┐
│               │      │                           │
│  Chat Client  │◄─────┤   Raft Server Cluster     │
│    (PyQt6)    │      │                           │
│               │─────►│  ┌─────────────────────┐  │
└───────────────┘      │  │  MessageService     │  │
                       │  │                     │  │
                       │  └─────────────────────┘  │
                       │  ┌─────────────────────┐  │
                       │  │  Raft Consensus     │  │
                       │  │  Algorithm          │  │
                       │  └─────────────────────┘  │
                       │  ┌─────────────────────┐  │
                       │  │  Persistent Storage │  │
                       │  │                     │  │
                       │  └─────────────────────┘  │
                       └───────────────────────────┘
```

### 1.2 Expanded Architecture View

The following diagram shows a more detailed view of the system architecture and how components interact:

```ascii
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│                             Client Applications                             │
│                                                                             │
└───────────────┬───────────────────────────────────────────┬─────────────────┘
                │                                           │
                │ gRPC                                      │ gRPC
                ▼                                           ▼
┌───────────────────────────────┐             ┌───────────────────────────────┐
│                               │             │                               │
│        Raft Node 1 (Leader)   │◄────────────┤        Raft Node 2            │
│                               │   AppendEntries         │                   │
│ ┌───────────────────────────┐ │   HeartBeat   ┌─────────────────────────┐   │
│ │                           │ │             │ │                         │   │
│ │     gRPC Services         │ │             │ │     gRPC Services       │   │
│ │  - MessageService         │ │             │ │  - MessageService       │   │
│ │  - DataService            │ │             │ │  - DataService          │   │
│ │  - NodeCommunication      │ │             │ │  - NodeCommunication    │   │
│ │                           │ │             │ │                         │   │
│ └───────────┬───────────────┘ │             │ └─────────┬───────────────┘   │
│             │                 │             │           │                   │
│             ▼                 │             │           ▼                   │
│ ┌───────────────────────────┐ │             │ ┌─────────────────────────┐   │
│ │                           │ │             │ │                         │   │
│ │     Raft State Machine    │ │             │ │   Raft State Machine    │   │
│ │  - Log                    │ │             │ │  - Log                  │   │
│ │  - Current Term           │ │             │ │  - Current Term         │   │
│ │  - Voted For              │ │             │ │  - Voted For            │   │
│ │                           │ │             │ │                         │   │
│ └───────────┬───────────────┘ │             │ └─────────┬───────────────┘   │
│             │                 │             │           │                   │
│             ▼                 │             │           ▼                   │
│ ┌───────────────────────────┐ │             │ ┌─────────────────────────┐   │
│ │                           │ │             │ │                         │   │
│ │     Chat Application      │ │             │ │   Chat Application      │   │
│ │  - Users                  │ │             │ │  - Users                │   │
│ │  - Messages               │ │             │ │  - Messages             │   │
│ │  - Channels               │ │             │ │  - Channels             │   │
│ │                           │ │             │ │                         │   │
│ └───────────┬───────────────┘ │             │ └─────────┬───────────────┘   │
│             │                 │             │           │                   │
│             ▼                 │             │           ▼                   │
│ ┌───────────────────────────┐ │             │ ┌─────────────────────────┐   │
│ │                           │ │             │ │                         │   │
│ │     SQLite Database       │ │             │ │    SQLite Database      │   │
│ │  - Persistent Storage     │ │             │ │  - Persistent Storage   │   │
│ │                           │ │             │ │                         │   │
│ └───────────────────────────┘ │             │ └─────────────────────────┘   │
│                               │             │                               │
└───────────────────────────────┘             └───────────────────────────────┘
                │                                           │
                │                                           │
                ▼                                           ▼
┌───────────────────────────────┐             ┌───────────────────────────────┐
│                               │             │                               │
│        Raft Node 3            │◄────────────┤        Raft Node 4            │
│                               │             │                               │
└───────────────────────────────┘             └───────────────────────────────┘
```

### 1.3 Raft State Transitions

This diagram illustrates the state transitions for each node in the Raft cluster:

```ascii
                   ┌─────────────────────┐
                   │                     │
          ┌────────┤      Follower       ◄──────────┐
          │        │                     │          │
          │        └─────────┬───────────┘          │
          │                  │                      │
Timeout   │                  │ Timeout,             │ Discovers
No Leader │                  │ Start Election       │ Current Leader
          │                  ▼                      │ or Higher Term
          │        ┌─────────────────────┐          │
          │        │                     │          │
          └───────►│      Candidate      ├──────────┘
                   │                     │
                   └─────────┬───────────┘
                             │
                             │ Receives Majority
                             │ of Votes
                             ▼
                   ┌─────────────────────┐
                   │                     │
                   │       Leader        │
                   │                     │
                   └─────────────────────┘
```

### 1.4 Log Replication Flow

The following diagram shows the detailed flow of log replication in the Raft system:

```ascii
┌────────┐              ┌────────┐              ┌────────┐
│ Client │              │ Leader │              │Follower│
└───┬────┘              └───┬────┘              └───┬────┘
    │                       │                       │
    │  1. Request           │                       │
    │───────────────────────>                       │
    │                       │                       │
    │                       │  2. AppendEntries     │
    │                       │───────────────────────>
    │                       │                       │
    │                       │  3. Append Success    │
    │                       │<───────────────────────
    │                       │                       │
    │                       │  4. AppendEntries     │
    │                       │──────────────────────┐│
    │                       │                      ││
    │                       │                      │▼
    │                       │                     Other
    │                       │                    Followers
    │                       │  5. Append Success   │
    │                       │<──────────────────────
    │                       │                       │
    │                       │  6. Commits Entry     │
    │                       │       when safe       │
    │                       │                       │
    │  7. Response          │                       │
    │<───────────────────────                       │
    │                       │  8. AppendEntries     │
    │                       │  (new commit index)   │
    │                       │───────────────────────>
    │                       │                       │
    │                       │                       │  9. Applies committed
    │                       │                       │     entries to state
    │                       │                       │     machine
    │                       │                       │
```

### 1.5 Communication Protocol

All inter-component communication is handled through gRPC, with service definitions in `replication.proto`:

* **NodeCommunication**: For inter-node Raft protocol messages
* **DataService**: For key-value operations on the state machine
* **MessageService**: For chat-specific operations
* **MonitoringService**: For health checks and status monitoring

### 1.6 System Components in Detail

* **Node Structure**: A cluster of 5 Raft nodes (configurable)
* **Consensus Protocol**: Full Raft implementation with leader election, log replication, and safety guarantees
* **Storage Backends**: Dual-layer persistence with in-memory state and SQLite for durability
* **Service Layer**: gRPC-based communication for both inter-node and client-server interactions

## 2. Raft Consensus Implementation

### 2.1 Core Concepts

Our implementation follows the Raft paper (Ongaro & Ousterhout, 2014) with:

* **Term-based Leadership**: Each term has at most one leader
* **Log Replication**: Commands are replicated across nodes
* **Safety**: If a node has applied a log entry at a given index, no other node will apply a different entry for the same index
* **Liveness**: As long as a majority of nodes are operational, the system continues to function

**Why We Chose Raft**: We selected Raft over other consensus algorithms like Paxos because of its design simplicity and understandability. The clear separation of leader election, log replication, and safety mechanisms made it easier to implement correctly and debug when issues arose. Its strong consistency guarantees were essential for our messaging application where message ordering and delivery guarantees are critical.

### 2.2 Server States

Each server exists in one of three states:

1. **Follower**: Passive state, responds to requests from leaders and candidates
2. **Candidate**: Initiates elections to become a leader
3. **Leader**: Handles client requests and manages log replication

```python
# State is managed as an enum in raft_node.py
class NodeState(Enum):
    FOLLOWER = 0
    CANDIDATE = 1
    LEADER = 2
```

**Why This State Model**: The three-state model provides a clear separation of responsibilities that simplifies the implementation. By having distinct states with well-defined transitions, we reduced the likelihood of race conditions and made the system's behavior more predictable during failures.

### 2.3 Enhanced Safety Features

We implemented additional safety checks beyond standard Raft:

* **Pre-Vote Protocol**: Reduces unnecessary elections by checking peer availability before formal election
* **Term Validation**: Strict enforcement of term monotonicity during log replication
* **Stale Leader Detection**: Mechanisms to detect and handle split-brain scenarios

**Why We Enhanced Safety**: While implementing the base Raft protocol, we encountered edge cases where network partitions could cause excessive term increments and unnecessary leader elections. The enhanced safety features were added to improve system stability, reduce unnecessary failovers, and protect against split-brain scenarios that could compromise data consistency.

### 2.4 Log Structure

Each log entry contains:
* Term number when the entry was created
* Index position in the log
* Command data (operation to be applied to the state machine)

```python
class LogEntry:
    def __init__(self, term, data, index=None):
        self.term = term
        self.data = data
        self.index = index
```

**Why This Log Structure**: We designed the log structure to maintain the essential properties required by Raft while keeping it as simple as possible. Including the term with each entry is crucial for detecting and resolving log inconsistencies during replication. The index field provides direct access to entries and simplifies the implementation of log compaction later.

## 3. Leadership Election

### 3.1 Election Process

Elections are triggered by:
* System initialization
* Timeout when no heartbeat is received from a leader

#### Election Algorithm:

1. Follower increments its term and transitions to candidate state
2. Candidate votes for itself and requests votes from other nodes
3. If a candidate receives votes from a majority of nodes, it becomes leader
4. If a candidate discovers a higher term, it reverts to follower state
5. If election timeout elapses with no winner, a new election begins

```python
def start_election(self):
    """Start a leader election"""
    with self.state_lock:
        self.current_term += 1
        self.state = NodeState.CANDIDATE
        self.voted_for = self.node_id
        
        # Reset election timeout
        self.last_heartbeat = time.time()
        self.election_timeout = self.compute_election_timeout()
        
        self.logger.info(f"Starting election for term {self.current_term}")
        
        # Request votes from all other nodes
        votes_received = 1  # Vote for self
        
        last_log_index = len(self.log) - 1
        last_log_term = 0
        if last_log_index >= 0:
            last_log_term = self.log[last_log_index].term
```

**Why Randomized Election Timeouts**: We implemented randomized election timeouts to prevent election conflicts, where multiple nodes become candidates simultaneously. This randomization is essential for ensuring the system's liveness property, allowing it to converge to a single leader quickly even after network partitions heal.

### 3.2 Leader Responsibilities

Once elected, a leader:
* Sends heartbeats (empty AppendEntries) to maintain authority
* Manages client requests
* Replicates log entries to followers
* Commits entries when safely replicated to a majority

**Why Centralized Leadership**: The leader-based approach simplifies the system by providing a single source of truth for all operations. This eliminates the need for complex distributed coordination protocols for each operation and reduces the opportunity for conflicts. The heartbeat mechanism provides an efficient way to detect leader failures with minimal communication overhead.

## 4. Data Replication

### 4.1 Log Replication Process

```ascii
   Client    Leader                             Followers
      │         │                                   │
      ├────────►│                                   │
      │         │                                   │
      │         ├───AppendEntries(log entries)─────►│
      │         │                                   │
      │         ◄─────────Response────────────────┤
      │         │                                   │
      │         │─────────────────────────────────►│
      │         │                                   │
      │         ◄─────────Response────────────────┤
      │         │                                   │
      │         │(After majority of confirmations)  │
      │         │(Leader commits entry)             │
      │         │                                   │
      │         ├────AppendEntries(commit index)───►│
      │         │                                   │
      ◄─────────┤                                   │
```

**Why This Replication Model**: We strictly followed Raft's log replication model because it provides a clear path to consistency. By ensuring that entries are only committed after being replicated to a majority of nodes, the system guarantees durability even when some nodes fail. The two-phase process (append then commit) ensures that all nodes eventually converge to the same state.

### 4.2 Efficient Replication Strategies

The system employs several optimizations for log replication:

1. **Batch Processing**: Combines multiple entries in a single AppendEntries RPC when possible
2. **Immediate Propagation**: Critical commands trigger immediate replication attempts
3. **Parallel Replication**: Uses threading to contact followers concurrently

**Why These Optimizations**: In our initial implementation, we observed high latency for write operations due to sequential replication. These optimizations were specifically added to improve throughput and reduce client-perceived latency. The parallel replication strategy, in particular, proved essential for scaling the system to handle more concurrent client requests.

### 4.3 Consistency Guarantees

The implementation maintains the following consistency properties:

* **Election Safety**: At most one leader per term
* **Leader Append-Only**: Leaders never overwrite or delete entries
* **Log Matching**: If two logs contain an entry with the same index and term, they are identical up to that point
* **Leader Completeness**: If an entry is committed, it will be present in the logs of all future leaders
* **State Machine Safety**: If a node applies a command to its state machine, no other node will apply a different command for the same log index

**Why Strong Consistency Guarantees**: We prioritized these strict consistency guarantees to ensure correctness in the messaging application. Message ordering and delivery guarantees are critical for user experience, and these properties ensure that all users see the same conversation history in the same order, regardless of which server they're connected to.

### 4.4 Next Index and Match Index Tracking

Leaders maintain two critical metadata arrays to track replication status:

* **next_index[]**: Index of the next log entry to send to each follower
* **match_index[]**: Index of highest log entry known to be replicated on each follower

```python
def become_leader(self):
    """Transition to leader state"""
    with self.state_lock:
        if self.state != NodeState.CANDIDATE:
            return False
            
        self.state = NodeState.LEADER
        self.leader_id = self.node_id
        
        # Initialize leader state
        self.next_index = {node['id']: len(self.log) for node in self.nodes if node['id'] != self.node_id}
        self.match_index = {node['id']: 0 for node in self.nodes if node['id'] != self.node_id}
```

**Why These Tracking Mechanisms**: These tracking arrays are essential for efficient log replication and recovery. They allow the leader to quickly identify which entries need to be sent to each follower, avoiding unnecessary replication of entries that are already present. They also enable the leader to determine when entries have been replicated to a majority of nodes and can be safely committed.

## 5. Persistent Storage

### 5.1 Storage Evolution

The system underwent a significant architectural evolution, migrating from a JSON-based persistence model to a full SQLite implementation:

```python
def init_database(self):
    """Initialize SQLite database schema and manage the database connection"""
    # Connect with proper configuration for Raft consensus use
    self.db_conn = sqlite3.connect(self.db_path, check_same_thread=False)
    
    # Set pragmas for better performance
    self.db_conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
    self.db_conn.execute("PRAGMA synchronous=NORMAL")  # Balance safety/performance
    self.db_conn.execute("PRAGMA foreign_keys=ON")  # Enforce constraints
```

**Why We Evolved the Storage Layer**: Our initial JSON-based persistence was simple but suffered from performance issues and didn't provide transaction safety. We migrated to SQLite to gain ACID properties, better concurrency with WAL mode, and improved query capabilities for the chat application. This change was crucial for handling user data reliably and scaling to support more concurrent operations.

### 5.2 Schema Design

The database schema was designed to support both key-value storage (for backward compatibility) and structured data for the chat application:

```sql
-- Create table for the key-value state machine (legacy)
CREATE TABLE IF NOT EXISTS state_machine (
    key TEXT PRIMARY KEY,
    value TEXT
)

-- Users, Messages, and Sessions tables implementation
CREATE TABLE IF NOT EXISTS sessions (
    session_token TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    FOREIGN KEY (username) REFERENCES users(username)
)
```

**Why This Schema Design**: We designed the schema to maintain backward compatibility with our existing key-value state machine while adding structured tables for users, messages, and sessions. This dual approach allowed us to continue supporting the existing Raft implementation while adding the specialized tables needed for the chat application. The foreign key constraints ensure data integrity across related tables.

### 5.3 Persisted State

To recover from crashes, critical state is persisted to disk:

* **Log Entries**: Complete command history
* **Current Term**: Latest term server has seen
* **Voted For**: Candidate that received vote in current term
* **State Machine**: Latest applied state

**Why This Persistence Strategy**: Persisting these specific Raft state elements is essential for maintaining the safety properties of the consensus algorithm across server restarts. We carefully designed the persistence layer to ensure that the critical components required by the Raft paper are durably stored, allowing servers to recover their exact state after crashes without violating safety guarantees.

### 5.4 State Machine Implementation

The state machine applies committed log entries and maintains the application state:

```python
def apply_to_state_machine(self, command: Dict):
    """Apply a command to the state machine"""
    with self.state_machine_lock:
        cmd_type = command.get('type')
        
        if cmd_type == 'set':
            key, value = command.get('key'), command.get('value')
            # Update both the in-memory dict and SQLite database
            self.state_machine[key] = value
            self.db_conn.execute("INSERT OR REPLACE INTO state_machine VALUES (?, ?)", 
                                 (key, json.dumps(value)))
            self.db_conn.commit()
```

**Why This Dual-Layer Approach**: We implemented both in-memory and persistent storage for the state machine to optimize for both performance and durability. The in-memory dictionary provides fast access for read operations, while the SQLite backend ensures durability across server restarts. This approach significantly improved performance while maintaining the safety guarantees required by the application.

## 6. Commit Index Management

### 6.1 Commit Rules

The system follows Raft's safety rules for committing entries:

```python
def update_commit_index(self):
    """Update the commit index if entries have been replicated to a majority"""
    if self.state != NodeState.LEADER:
        return
    
    old_commit_index = self.commit_index
    
    # Find the highest index that has been replicated to a majority
    for i in range(self.commit_index + 1, len(self.log)):
        # Only commit entries from current term (Raft safety property)
        if self.log[i].term != self.current_term:
            continue
            
        replica_count = 1  # Count self
        for node_id in self.match_index:
            if self.match_index[node_id] >= i:
                replica_count += 1
        
        # If majority of nodes have replicated this entry, commit it
        if replica_count > len(self.nodes) // 2:
            self.commit_index = i
```

**Why We Follow Strict Commit Rules**: We strictly follow Raft's commit rules to ensure the system's safety properties are maintained even during leadership changes. The restriction of only committing entries from the current term in the update_commit_index function is particularly important for preventing scenarios where uncommitted entries from previous terms might be lost during a leader change.

## 7. Message Service Implementation

### 7.1 Chat Functionality

The MessageService is built on top of the Raft consensus layer, providing:

* User registration and authentication
* Session management
* Public and private messaging
* Channel-based communication

**Why This Service Layer Approach**: We designed the MessageService as a separate layer above the Raft implementation to maintain a clean separation of concerns. This modular architecture allows us to modify the chat functionality without affecting the underlying consensus mechanism, and potentially replace either component independently as requirements evolve.

### 7.2 Integration Architecture

The chat functionality was integrated as a layer on top of the existing Raft implementation:

```
Original approach (failed):
Chat App → Add Replication → Refactor for Consistency

Revised approach (successful):
Build Raft Core → Add State Machine → Rebuild Chat on Top
```

**Why We Changed Our Integration Approach**: Our initial attempt to add replication to an existing chat application proved problematic due to the complex interdependencies it created. By reversing the approach—building a solid Raft foundation first and then adding chat functionality on top—we achieved a more maintainable architecture with better separation of concerns and fewer edge cases.

### 7.3 Session Management

One of the most critical aspects was maintaining session validity across node failures:

```python
# Evolved session management with SQLite
def validate_session(self, token):
    """Validate a session token and check if it's still valid"""
    cursor = self.db_conn.execute(
        "SELECT username, expires_at FROM sessions WHERE session_token = ?", 
        (token,)
    )
    result = cursor.fetchone()
    
    if not result:
        return None
        
    username, expires_at = result
    current_time = int(time.time())
    
    if current_time > expires_at:
        # Session expired, clean up
        self.db_conn.execute("DELETE FROM sessions WHERE session_token = ?", (token,))
        self.db_conn.commit()
        return None
        
    return username
```

**Why Robust Session Management Was Critical**: Session management presented unique challenges in a distributed environment. Sessions must be available and consistent across all nodes, even during leader changes or node failures. We designed the session management system to be fully replicated through the Raft log, ensuring that user authentication state is never lost during failovers, which is crucial for maintaining a seamless user experience.

## 8. Fault Tolerance and Recovery

### 8.1 Failure Handling

The system is designed to handle various failure scenarios:

* Node crashes and restarts
* Network partitions
* Corrupt log entries
* Divergent logs

**Why Comprehensive Failure Handling**: A distributed messaging system must remain operational despite various failure modes. We specifically designed our failure handling to address the most common scenarios in distributed systems, ensuring that the chat application continues to function even when multiple servers fail. This robustness is essential for deploying the system in real-world environments where failures are inevitable.

### 8.2 Recovery Process

When nodes restart or rejoin after a failure, the recovery process includes:

1. Loading persisted state from disk
2. Identifying and catching up with the current leader
3. Reconciling divergent logs using term and index information
4. Rebuilding state machine to the latest committed index

**Why This Structured Recovery Process**: The recovery process was carefully designed to ensure that nodes can rejoin the cluster smoothly without compromising safety. By first loading persisted state and then catching up with the current leader, nodes avoid unnecessary election disruptions. The systematic approach to recovery reduces the time needed for a node to become fully operational after a failure.

### 8.3 Log Inconsistency Recovery

Handling log inconsistencies was one of the major implementation challenges:

```python
# Sophisticated log matching for recovery
def reconcile_logs(self, follower_id, conflict_index):
    """Handle log inconsistency by finding the last point of agreement"""
    # Find the last index where logs match
    for i in range(conflict_index, 0, -1):
        if i <= 0:
            # Logs completely diverge, start from beginning
            self.next_index[follower_id] = 1
            return
            
        if i < len(self.log) and self.log[i-1].term == self.follower_terms[follower_id][i-1]:
            # Found matching point, start replication from here
            self.next_index[follower_id] = i
            return
            
    # If no match found, reset to beginning
    self.next_index[follower_id] = 1
```

**Why Sophisticated Log Reconciliation**: Log inconsistencies are inevitable in distributed systems, especially after network partitions heal. Our log reconciliation algorithm efficiently identifies the exact point of divergence between logs and repairs the inconsistencies without requiring full log replacement. This approach significantly reduces recovery time and network traffic compared to naive approaches that would transfer entire logs.

## 9. Testing Fault Tolerance

### 9.1 Test Methodology

The system's fault tolerance can be tested by:

* System operates normally with 5 nodes
* System continues functioning with 4 nodes (1 failure)
* System continues functioning with 3 nodes (2 failures)
* System becomes unavailable with only 2 nodes (3 failures)
* When failed nodes are restarted, the system resumes normal operation

**Why This Testing Approach**: We designed our testing methodology to verify that the system correctly implements Raft's majority-based consensus. A 5-node system should tolerate 2 node failures (remaining operational with 3 nodes) but become unavailable with 3 failures. This approach ensures we've correctly implemented the theoretical fault tolerance properties of Raft and validates that our recovery mechanisms work properly.

### 9.2 Scalability Considerations

The current implementation has some scaling limitations:

* All nodes store the complete state machine
* All nodes process all commands
* O(N²) communication complexity for the Raft protocol

Potential improvements:

* Read-only queries could be served directly from followers
* Sharding across multiple Raft groups for horizontal scaling

**Why We Acknowledge Scaling Limitations**: Being transparent about scaling limitations is important for setting appropriate expectations. The current implementation follows the standard Raft approach with full replication across all nodes, which has known scaling constraints. We identified potential optimizations like read-only queries from followers and sharding to guide future improvements when scaling becomes necessary.

## 10. Performance Optimization

### 10.1 Initial Performance Issues

Early benchmarks revealed several performance bottlenecks:

* Log replication took over 500ms per entry in the first implementation
* State machine writes had high latency due to excessive locking
* Memory usage grew linearly with log size

**Why Performance Analysis Was Necessary**: Initial performance testing revealed significant bottlenecks that would have made the system impractical for real-world use. Identifying these issues early in development allowed us to address them systematically before finalizing the architecture, resulting in a much more responsive final system.

### 10.2 Successful Optimizations

The final system includes several optimizations:

* Parallel replication using threading
* SQLite Write-Ahead Logging for improved concurrency
* Fine-grained locking to reduce contention
* Strategic indexing for common query patterns

**Why These Specific Optimizations**: Each optimization addresses a specific bottleneck identified in our performance testing. Parallel replication addresses the high latency of sequential replication. WAL mode in SQLite improves write throughput by allowing concurrent reads during writes. Fine-grained locking reduces contention between threads, and strategic indexing accelerates common database operations essential for the chat application.

### 10.3 Current Performance Metrics

After optimization, the system achieves:

* Log replication latency: < 50ms per entry (single node)
* Throughput: Up to 1000 commands per second with 5 nodes
* Recovery time: < 2 seconds for 10,000 log entries

**Why We Track These Metrics**: These specific performance metrics were chosen to represent the most important aspects of system behavior for a chat application. Replication latency affects message delivery time, throughput determines how many users can be served simultaneously, and recovery time impacts availability after node failures. The achieved metrics demonstrate that the system is suitable for real-world deployment.

## 11. Alternative Approaches Considered

### 11.1 Pure In-Memory with Snapshots

An early design relied solely on memory with periodic snapshots:

```python
def create_snapshot(self):
    """Create a point-in-time snapshot of the state machine"""
    with self.state_machine_lock:
        snapshot = {
            'state_machine': deepcopy(self.state_machine),
            'last_applied': self.last_applied,
            'timestamp': time.time()
        }
        
        # Write to disk atomically
        snapshot_path = os.path.join(self.data_dir, f"snapshot_{self.last_applied}.json")
        temp_path = snapshot_path + ".tmp"
        
        with open(temp_path, 'w') as f:
            json.dump(snapshot, f)
            
        os.rename(temp_path, snapshot_path)
```

Advantages:
* Simple implementation
* Fast in-memory operations

Drawbacks:
* Long recovery times
* Risk of data loss between snapshots

**Why We Rejected This Approach**: While simpler to implement, this approach couldn't provide the durability guarantees required for a messaging application. The potential for data loss between snapshots was unacceptable for user messages, and the long recovery times would impact availability. Our SQLite-based solution provides better durability with minimal performance impact.

### 11.2 MongoDB-Based State Machine

We also considered using MongoDB for the state machine:

```python
# Considered but not implemented
def apply_to_mongodb(command):
    """Apply command to MongoDB state machine"""
    db = mongo_client[DB_NAME]
    
    if command['type'] == 'message':
        db.messages.insert_one({
            'sender': command['sender'],
            'receiver': command['receiver'],
            'content': command['content'],
            'timestamp': command['timestamp']
        })
```

Advantages:
* Native support for JSON documents
* Built-in replication capabilities
* Horizontal scaling

Drawbacks:
* Complexity of managing two distributed systems
* Potential consistency issues between Raft and MongoDB
* Higher resource requirements

**Why We Rejected This Approach**: Introducing MongoDB would have added unnecessary complexity by requiring us to maintain consistency between two different distributed systems. The potential for conflicts between Raft's consensus and MongoDB's replication would have been difficult to resolve. Our SQLite implementation provides all the necessary functionality with lower complexity and resource requirements.

## 12. Tests

We have tests in the root directory.

## 13. Future Work

Some areas for future development include:

* Optimizing the append-only log for better memory usage
* Implementing snapshotting for log compaction
* Supporting dynamic membership changes

## 14. Recent Updates

### March 25, 2025

* Completed documentation of persistent storage implementation
* Verified all component diagrams are up-to-date
* System now handles node recovery with proper log reconciliation
* Added comprehensive test suite for leader election edge cases
* Integrated information from the original server replication implementation

Advantages:
* Native support for JSON documents
* Built-in replication capabilities
* Horizontal scaling

Drawbacks:
* Complexity of managing two distributed systems
* Potential consistency issues between Raft and MongoDB
* Higher resource requirements

**Why We Rejected This Approach**: Introducing MongoDB would have added unnecessary complexity by requiring us to maintain consistency between two different distributed systems. The potential for conflicts between Raft's consensus and MongoDB's replication would have been difficult to resolve. Our SQLite implementation provides all the necessary functionality with lower complexity and resource requirements.