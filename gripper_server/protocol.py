"""
Protocol definitions for Gripper Server communication.

Uses msgpack for fast, compact serialization over ZMQ.
All messages are defined as dataclasses for type safety.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional
from enum import IntEnum
import time

try:
    import msgpack
except ImportError:
    raise ImportError("msgpack not installed. Run: pip install msgpack")


# Default network ports
DEFAULT_CMD_PORT = 5570
DEFAULT_STATE_PORT = 5571


class MessageType(IntEnum):
    """Message type identifiers for protocol."""
    # State messages
    GRIPPER_STATE = 1
    
    # Command messages
    ACTIVATE = 10
    RESET = 11
    MOVE = 12
    OPEN = 13
    CLOSE = 14
    STOP = 15
    CALIBRATE = 16
    
    # Response messages
    RESPONSE = 100


class GripperType(IntEnum):
    """Supported gripper types."""
    UNKNOWN = 0
    ROBOTIQ_2F85 = 1
    ROBOTIQ_2F140 = 2
    ROBOTIQ_HANDE = 3
    # Add more gripper types here


@dataclass
class GripperStateMsg:
    """Gripper state message broadcast by the server.
    
    This is a unified state format for all gripper types.
    """
    # Timing
    timestamp: float = 0.0
    
    # Gripper identification
    gripper_type: int = GripperType.UNKNOWN
    
    # Position state
    position: int = 0           # Current position (0-255, 0=open, 255=closed)
    position_mm: float = 0.0    # Position in mm (if calibrated)
    
    # Request echo
    position_request: int = 0   # Echo of requested position
    
    # Motor state
    current: int = 0            # Motor current (0-255)
    current_ma: float = 0.0     # Current in mA (current * 10)
    
    # Status flags
    is_activated: bool = False
    is_moving: bool = False
    object_detected: bool = False
    is_calibrated: bool = False
    
    # Calibration data (if calibrated)
    open_mm: float = 0.0
    close_mm: float = 0.0
    
    # Fault information
    fault_code: int = 0
    fault_message: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GripperStateMsg":
        return cls(**data)
    
    def pack(self) -> bytes:
        """Pack state into binary format for transmission."""
        return msgpack.packb(self.to_dict(), use_bin_type=True)
    
    @classmethod
    def unpack(cls, data: bytes) -> "GripperStateMsg":
        """Unpack state from binary format."""
        return cls.from_dict(msgpack.unpackb(data, raw=False))


@dataclass
class ActivateCmd:
    """Activate/initialize the gripper."""
    msg_type: int = MessageType.ACTIVATE
    timestamp: float = field(default_factory=time.time)
    reset_first: bool = True  # Reset before activation
    
    def pack(self) -> bytes:
        return msgpack.packb(asdict(self), use_bin_type=True)
    
    @classmethod
    def unpack(cls, data: bytes) -> "ActivateCmd":
        d = msgpack.unpackb(data, raw=False)
        return cls(**d)


@dataclass
class ResetCmd:
    """Reset the gripper."""
    msg_type: int = MessageType.RESET
    timestamp: float = field(default_factory=time.time)
    
    def pack(self) -> bytes:
        return msgpack.packb(asdict(self), use_bin_type=True)
    
    @classmethod
    def unpack(cls, data: bytes) -> "ResetCmd":
        d = msgpack.unpackb(data, raw=False)
        return cls(**d)


@dataclass
class MoveCmd:
    """Move gripper to specified position."""
    msg_type: int = MessageType.MOVE
    timestamp: float = field(default_factory=time.time)
    position: int = 0      # Target position (0-255)
    speed: int = 255       # Movement speed (0-255)
    force: int = 255       # Grip force (0-255)
    
    def pack(self) -> bytes:
        return msgpack.packb(asdict(self), use_bin_type=True)
    
    @classmethod
    def unpack(cls, data: bytes) -> "MoveCmd":
        d = msgpack.unpackb(data, raw=False)
        return cls(**d)


@dataclass
class OpenCmd:
    """Open the gripper fully."""
    msg_type: int = MessageType.OPEN
    timestamp: float = field(default_factory=time.time)
    speed: int = 255
    force: int = 255
    
    def pack(self) -> bytes:
        return msgpack.packb(asdict(self), use_bin_type=True)
    
    @classmethod
    def unpack(cls, data: bytes) -> "OpenCmd":
        d = msgpack.unpackb(data, raw=False)
        return cls(**d)


@dataclass
class CloseCmd:
    """Close the gripper fully."""
    msg_type: int = MessageType.CLOSE
    timestamp: float = field(default_factory=time.time)
    speed: int = 255
    force: int = 255
    
    def pack(self) -> bytes:
        return msgpack.packb(asdict(self), use_bin_type=True)
    
    @classmethod
    def unpack(cls, data: bytes) -> "CloseCmd":
        d = msgpack.unpackb(data, raw=False)
        return cls(**d)


@dataclass
class StopCmd:
    """Stop gripper motion."""
    msg_type: int = MessageType.STOP
    timestamp: float = field(default_factory=time.time)
    
    def pack(self) -> bytes:
        return msgpack.packb(asdict(self), use_bin_type=True)
    
    @classmethod
    def unpack(cls, data: bytes) -> "StopCmd":
        d = msgpack.unpackb(data, raw=False)
        return cls(**d)


@dataclass
class CalibrateCmd:
    """Calibrate the gripper for mm positioning."""
    msg_type: int = MessageType.CALIBRATE
    timestamp: float = field(default_factory=time.time)
    open_mm: float = 85.0   # Distance when fully open (mm)
    close_mm: float = 0.0   # Distance when fully closed (mm)
    
    def pack(self) -> bytes:
        return msgpack.packb(asdict(self), use_bin_type=True)
    
    @classmethod
    def unpack(cls, data: bytes) -> "CalibrateCmd":
        d = msgpack.unpackb(data, raw=False)
        return cls(**d)


@dataclass
class Response:
    """Response message from server."""
    msg_type: int = MessageType.RESPONSE
    success: bool = False
    message: str = ""
    data: Optional[Dict[str, Any]] = None
    
    def pack(self) -> bytes:
        d = asdict(self)
        return msgpack.packb(d, use_bin_type=True)
    
    @classmethod
    def unpack(cls, data: bytes) -> "Response":
        d = msgpack.unpackb(data, raw=False)
        return cls(**d)


def unpack_command(data: bytes):
    """Unpack a command message and return the appropriate command object."""
    d = msgpack.unpackb(data, raw=False)
    msg_type = d.get("msg_type")
    
    if msg_type == MessageType.ACTIVATE:
        return ActivateCmd(**d)
    elif msg_type == MessageType.RESET:
        return ResetCmd(**d)
    elif msg_type == MessageType.MOVE:
        return MoveCmd(**d)
    elif msg_type == MessageType.OPEN:
        return OpenCmd(**d)
    elif msg_type == MessageType.CLOSE:
        return CloseCmd(**d)
    elif msg_type == MessageType.STOP:
        return StopCmd(**d)
    elif msg_type == MessageType.CALIBRATE:
        return CalibrateCmd(**d)
    else:
        raise ValueError(f"Unknown message type: {msg_type}")
