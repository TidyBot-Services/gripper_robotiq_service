#!/bin/bash
# Setup script for Gripper Client
# Run this on machines that need to control the gripper remotely
#
# Prerequisites: Activate your virtual environment first!

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Gripper Client Setup ==="
echo ""

# Check if we're in a virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
    echo "WARNING: No virtual environment detected!"
    echo ""
    echo "It is recommended to use a virtual environment:"
    echo "  python3 -m venv venv"
    echo "  source venv/bin/activate"
    echo ""
fi

# Install minimal dependencies for client
echo "Installing client dependencies..."
pip install pyzmq msgpack

# Optionally install the full package
read -p "Install full gripper_server package? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    pip install -e "$SCRIPT_DIR"
    echo "Full package installed."
else
    echo "Minimal client dependencies installed."
    echo ""
    echo "To use the client, copy gripper_server/client.py and gripper_server/protocol.py"
    echo "to your project, or install the full package later with:"
    echo "  pip install -e $SCRIPT_DIR"
fi

echo ""
echo "=== Setup Complete ==="
