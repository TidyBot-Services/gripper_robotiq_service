#!/bin/bash
# Start the gripper server
# Usage: ./start_server.sh [options]
#
# Prerequisites: Activate your virtual environment first!
#
# Options:
#   --gripper TYPE    Gripper type (default: robotiq)
#   --port PORT       Serial port (default: auto)
#   --cmd-port PORT   Command port (default: 5570)
#   --state-port PORT State port (default: 5571)


# Start the server with all arguments passed through
echo "Starting Gripper Server..."
python -m gripper_server.server "$@"
