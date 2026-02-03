"""
Gripper Server - A modular gripper control framework.

This package provides a server/client architecture for controlling
various grippers in a lab environment through a unified interface.

Architecture:
    Your Control Code <--ZMQ--> GripperServer <--Serial/USB--> Gripper Hardware

Example:
    # Server side (run on machine connected to gripper)
    python -m gripper_server.server --gripper robotiq
    
    # Client side (can run anywhere)
    from gripper_server import GripperClient
    
    client = GripperClient(server_ip="localhost")
    client.connect()
    client.activate()
    client.open()
    client.close()
"""

__version__ = "0.1.0"
__author__ = "Lab Robotics Team"

# Client (always available)
from gripper_server.client import GripperClient

# Protocol
from gripper_server.protocol import (
    GripperStateMsg,
    GripperType,
    ActivateCmd,
    ResetCmd,
    MoveCmd,
    OpenCmd,
    CloseCmd,
    StopCmd,
    CalibrateCmd,
    Response,
    DEFAULT_CMD_PORT,
    DEFAULT_STATE_PORT,
)

# Server and grippers (may require additional dependencies)
try:
    from gripper_server.server import GripperServer
    from gripper_server.grippers import (
        BaseGripper,
        GripperState,
        RobotiqGripper,
        get_gripper,
        GRIPPER_REGISTRY,
    )
    _server_available = True
except ImportError:
    _server_available = False


__all__ = [
    # Client
    "GripperClient",
    # Protocol
    "GripperStateMsg",
    "GripperType",
    "ActivateCmd",
    "ResetCmd",
    "MoveCmd",
    "OpenCmd",
    "CloseCmd",
    "StopCmd",
    "CalibrateCmd",
    "Response",
    "DEFAULT_CMD_PORT",
    "DEFAULT_STATE_PORT",
]

if _server_available:
    __all__.extend([
        # Server
        "GripperServer",
        # Grippers
        "BaseGripper",
        "GripperState",
        "RobotiqGripper",
        "get_gripper",
        "GRIPPER_REGISTRY",
    ])
