#!/bin/bash
# Setup script for Gripper Server
# Run this on the machine connected to the gripper hardware
#
# Prerequisites: Activate your virtual environment first!

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Gripper Server Setup ==="
echo ""



# Install the package
echo "Installing gripper_server package..."
pip install -e "$SCRIPT_DIR"

# Verify installation
echo ""
echo "Verifying installation..."
python -c "from gripper_server import GripperClient; print('Installation successful!')"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To start the server:"
echo "  python -m gripper_server.server --gripper robotiq"
echo ""
echo "For Robotiq grippers, you may need to set serial port permissions:"
echo "  sudo chmod 666 /dev/ttyUSB0"
echo ""
