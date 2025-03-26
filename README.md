# Raft Chat - A Distributed Messaging App

**Pranav Ramesh, Mohamed Zidan Cassim**

This is a messaging chat application built on top of the Raft consensus algorithm implementation. It provides a fault-tolerant messaging system that resembles iMessage.

## Features

- **User Registration and Authentication**: Create accounts, login, and logout
- **Messaging**: Send and receive messages in real-time
- **Message Management**: Delete your sent messages
- **User Status**: See which users are online and offline
- **Unread Messages**: Track unread messages from other users
- **Account Management**: Delete your account if needed

## Architecture

The application is built using:
- **Raft Consensus**: For reliable distributed state management
- **gRPC**: For efficient client-server communication
- **PyQt6**: For the graphical user interface

## Prerequisites

- Python 3.6+
- PyQt6
- gRPC and gRPC tools

## Installation

1. Ensure you have the required dependencies:
```
pip install -r requirements.txt
```

2. Generate the gRPC code:
```
./generate_proto.sh
```

## Usage

### Starting the Server Cluster

First, start the Raft server cluster:

```
python run_cluster.py --config config.json --nodes all --no-auto-restart
```

The system is designed to tolerate multiple node failures. With the default 5-node configuration, it can continue operating with up to 2 nodes down.

### Starting the Raft Monitor

Start the Raft monitor to manage and view the status of the cluster:

```
python raft_monitor.py
```

You can see the cluster status and node health in the Raft monitor. This monitor also allows you to test crashing servers and restarting them. Use a Raft monitor on every unique device that is hosting a server and control the servers of an individual host specifically from that device's Raft monitor.

### Running the Chat Client

Launch the chat client:

```
python chat_launcher.py
```

### Using the Chat App

1. **Register a New Account**: Click "Register" on the login screen and fill in your details
2. **Login**: Enter your username and password
3. **Send Messages**: Select a user from the contact list and type your message
4. **Delete Messages**: Right-click on your sent messages to delete them
5. **Logout**: Click the "Logout" button when done
6. **Delete Account**: Click "Settings" > "Delete Account" if you wish to remove your account

## How It Works

The chat application leverages the Raft consensus algorithm to ensure:

1. **Consistency**: All servers have the same view of messages and user accounts
2. **Fault Tolerance**: The system continues working even if some servers fail
3. **Persistence**: Messages and account data are preserved even if all servers restart

The client communicates with the server cluster through gRPC services defined in the protocol buffer file. The servers use Raft to replicate all state changes, such as sending messages or creating accounts, ensuring that any changes made through one server are propagated to all others.

## Technical Details

- Messages are stored in the Raft state machine and replicated across all nodes
- User authentication is handled through session tokens
- The UI is built with PyQt6 to provide a modern and responsive interface
- The client automatically reconnects to alternative servers if the leader fails

## Troubleshooting

- **Connection Issues**: Ensure the server cluster is running
- **Login Problems**: Verify your username and password
- **Message Delivery Delays**: This can occur if the leader is changing (failover)

## Engineering Notebook

For detailed information about the system design and implementation, please refer to the [ENGINEERING_NOTEBOOK.md](ENGINEERING_NOTEBOOK.md) file.
