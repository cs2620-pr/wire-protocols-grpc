import os
import logging
import sys
from server.server import ChatServicer
from server.chat.chat_pb2 import SendMessageRequest

# Print Python version for debugging
print(f"Python version: {sys.version}")

# Create logs directory if it doesn't exist
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)
print(f"Logs directory: {os.path.abspath(log_dir)}")

# Clear the existing log files
with open(os.path.join(log_dir, "server.log"), "w") as f:
    f.write("")
with open(os.path.join(log_dir, "protocol_metrics_server.log"), "w") as f:
    f.write("")

# Debug info about logging
print("\nLogging config before basicConfig:")
print(f"Root logger level: {logging.getLogger().level}")
print(f"Root logger handlers: {logging.getLogger().handlers}")

# Configure basic logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(log_dir, "server.log")),
        logging.StreamHandler(),
    ],
    force=True,  # Force reconfiguration
)

# Debug info about logging
print("\nLogging config after basicConfig:")
print(f"Root logger level: {logging.getLogger().level}")
print(f"Root logger handlers: {logging.getLogger().handlers}")

# Get a logger
logger = logging.getLogger("server")
print(f"Server logger level: {logger.level}")
print(f"Server logger propagate: {logger.propagate}")
print(f"Server logger handlers: {logger.handlers}")

# Log directly to root logger
logging.info("Direct root logger message")

# Log to server logger
logger.info("Starting test script")
print(
    f"After logging: Server log exists: {os.path.exists(os.path.join(log_dir, 'server.log'))}"
)
print(
    f"After logging: Server log size: {os.path.getsize(os.path.join(log_dir, 'server.log'))}"
)

# Create a servicer with logging enabled
servicer = ChatServicer(enable_logging=True)
logger.info("Created servicer with logging enabled")

# Log some messages
servicer.protocol_logger.info("Direct protocol logger test message")
logger.info("Server logger test message")

# Create a request and log it using the servicer's log_message method
request = SendMessageRequest(
    session_token="test_token", recipient="recipient", content="Test message content"
)
servicer.log_message("TEST", "TestMethod", request, "Test message details")

# Print log file paths
print(f"\nLog files should be written to:")
print(f"  Server log: {os.path.join(os.getcwd(), log_dir, 'server.log')}")
print(
    f"  Protocol metrics log: {os.path.join(os.getcwd(), log_dir, 'protocol_metrics_server.log')}"
)


# Check if the logs exist and have content
def check_log_file(file_path: str) -> None:
    if os.path.exists(file_path):
        size = os.path.getsize(file_path)
        if size > 0:
            print(f"  ✅ {file_path} exists and has {size} bytes")
            with open(file_path, "r") as f:
                lines = f.readlines()
                print(
                    f"  Last log entry: {lines[-1].strip() if lines else 'No entries'}"
                )
        else:
            print(f"  ❌ {file_path} exists but is empty")
    else:
        print(f"  ❌ {file_path} does not exist")


print("\nChecking log files:")
check_log_file(os.path.join(log_dir, "server.log"))
check_log_file(os.path.join(log_dir, "protocol_metrics_server.log"))

# Try direct file writing to rule out permission issues
try:
    test_file_path = os.path.join(log_dir, "test_write.log")
    with open(test_file_path, "w") as f:
        f.write("Test write access\n")
    print(f"\nDirect file write test: ✅ Wrote to {test_file_path}")
    os.remove(test_file_path)
except Exception as e:
    print(f"\nDirect file write test: ❌ Failed with error: {str(e)}")
