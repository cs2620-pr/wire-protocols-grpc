import os
import logging
import pytest
from server.server import ChatServicer
from server.chat.chat_pb2 import SendMessageRequest

# Set up logging for this test module
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)


# Clear existing log files before the test
def setup_module(module):
    # Clear log files at the start of the test module
    with open(os.path.join(log_dir, "server.log"), "w") as f:
        f.write("Starting test_logging_pytest.py tests\n")
    with open(os.path.join(log_dir, "protocol_metrics_server.log"), "w") as f:
        f.write("Starting test_logging_pytest.py tests\n")

    print(f"Log files cleared and initialized")

    # Configure logging directly
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        handlers=[
            logging.FileHandler(os.path.join(log_dir, "server.log"), mode="a"),
            logging.StreamHandler(),
        ],
        force=True,
    )

    # Get a logger and log something
    logger = logging.getLogger("server")
    logger.info("Setup module running - this should go to server.log")

    # Debug info
    print(f"Root logger level: {logging.getLogger().level}")
    print(f"Root logger handlers: {logging.getLogger().handlers}")
    print(f"Server logger level: {logger.level}")
    print(f"Server logger handlers: {logger.handlers}")


@pytest.fixture
def servicer():
    """Create a ChatServicer instance with logging enabled."""
    return ChatServicer(enable_logging=True)


def test_logging_with_pytest(servicer):
    """Test that logging works correctly in pytest."""
    # Get a logger
    logger = logging.getLogger("server")
    logger.info("Test logging_with_pytest running - this should go to server.log")

    # Log a protocol message
    servicer.protocol_logger.info("Protocol logger test message from pytest")

    # Create and log a request
    request = SendMessageRequest(
        session_token="test_token",
        recipient="recipient",
        content="Test message from pytest",
    )
    servicer.log_message("TEST", "TestMethod", request, "Test details from pytest")

    # Check log files
    assert os.path.exists(
        os.path.join(log_dir, "server.log")
    ), "Server log file should exist"
    assert os.path.exists(
        os.path.join(log_dir, "protocol_metrics_server.log")
    ), "Protocol log file should exist"

    # Print file sizes for debugging
    server_log_size = os.path.getsize(os.path.join(log_dir, "server.log"))
    protocol_log_size = os.path.getsize(
        os.path.join(log_dir, "protocol_metrics_server.log")
    )
    print(f"Server log size: {server_log_size} bytes")
    print(f"Protocol log size: {protocol_log_size} bytes")

    # Assert that logs have content
    assert server_log_size > 0, "Server log should have content"
    assert protocol_log_size > 0, "Protocol log should have content"

    # Verify by reading the last line of each log
    with open(os.path.join(log_dir, "server.log"), "r") as f:
        lines = f.readlines()
        last_line = lines[-1].strip() if lines else "No entries"
        print(f"Last server log entry: {last_line}")

    with open(os.path.join(log_dir, "protocol_metrics_server.log"), "r") as f:
        lines = f.readlines()
        last_line = lines[-1].strip() if lines else "No entries"
        print(f"Last protocol log entry: {last_line}")


def test_direct_file_access():
    """Test that we can write to the log directory directly."""
    test_file_path = os.path.join(log_dir, "pytest_test_write.log")
    with open(test_file_path, "w") as f:
        f.write("Test write access from pytest\n")

    assert os.path.exists(test_file_path), "Test file should exist"
    assert os.path.getsize(test_file_path) > 0, "Test file should have content"

    # Clean up
    os.remove(test_file_path)
