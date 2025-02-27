import re
import pandas as pd
from collections import defaultdict
from typing import DefaultDict, Dict

# Directory path for log files
log_directory = "logs/"
log_files = ["client.log", "database.log", "protocol_metrics_server.log"]

# Regex patterns for extracting relevant information
grpc_pattern = re.compile(r"GRPC (Incoming|Outgoing) - (\w+) - Size: (\d+) bytes")
storage_pattern = re.compile(
    r"Storing message \| Sender: .*? \| Recipient: .*? \| Message Size: (\d+) bytes"
)

# Data containers
operation_stats: DefaultDict[str, Dict[str, int]] = defaultdict(
    lambda: {"count": 0, "total_bytes": 0}
)


# Function to process log files
def process_log_file(file_path: str) -> None:
    with open(file_path, "r") as file:
        for line in file:
            grpc_match = grpc_pattern.search(line)
            storage_match = storage_pattern.search(line)

            if grpc_match:
                _, operation, size = grpc_match.groups()
                size = int(size)
                operation_stats[operation]["count"] += 1
                operation_stats[operation]["total_bytes"] += size

            if storage_match:
                size = int(storage_match.group(1))
                operation_stats["store_message"]["count"] += 1
                operation_stats["store_message"]["total_bytes"] += size


# Process each log file
for log_file in log_files:
    process_log_file(log_directory + log_file)

# Create DataFrame for results
analysis_df = pd.DataFrame(
    [
        {
            "Operation": op,
            "Count": stats["count"],
            "Total Bytes": stats["total_bytes"],
            "Avg Size (bytes)": (
                round(stats["total_bytes"] / stats["count"], 2)
                if stats["count"] > 0
                else 0
            ),
        }
        for op, stats in operation_stats.items()
    ]
)

# Save the results and display them


analysis_df.sort_values(by="Count", ascending=False, inplace=True)
print(analysis_df)  # Simple console output
analysis_df.to_csv("grpc_log_analysis.csv", index=False)  # Save as CSV
