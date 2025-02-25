#!/bin/bash

# Exit on any error
set -e

# Create the output directory if it doesn't exist
mkdir -p server/chat

# Compile the proto file with mypy support
python -m grpc_tools.protoc \
    -I./protos \
    --python_out=./server/chat \
    --grpc_python_out=./server/chat \
    --mypy_out=./server/chat \
    ./protos/chat.proto

# Create __init__.py files if they don't exist
touch server/__init__.py
touch server/chat/__init__.py

# Create py.typed file to mark the package as typed
touch server/chat/py.typed

# Fix imports in generated files
sed -i '' 's/import chat_pb2/from . import chat_pb2/' server/chat/chat_pb2_grpc.py

echo "Proto compilation completed successfully!"
