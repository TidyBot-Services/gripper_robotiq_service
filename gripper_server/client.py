"""
Gripper Client - Connect to GripperServer from your control code.

This client provides a simple interface for controlling grippers
through the GripperServer via ZMQ.

Example:
    from gripper_server import GripperClient
    
    # Connect to server
    client = GripperClient(server_ip="localhost")
    client.connect()
    
    # Activate and control
    client.activate()
    client.open()
    client.close(force=200)
    
    # Get state
    state = client.get_state()
    print(f"Position: {state.position}")
    
    client.disconnect()
"""

import logging
import time
from typing import Optional, Tuple, Dict, Any

try:
    import zmq
except ImportError:
    raise ImportError("ZMQ not installed. Run: pip install pyzmq")

try:
    import msgpack
except ImportError:
    raise ImportError("msgpack not installed. Run: pip install msgpack")

from gripper_server.protocol import (
    GripperStateMsg,
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


logger = logging.getLogger(__name__)


class GripperClient:
    """Client for connecting to GripperServer.
    
    Provides both synchronous commands and state subscription.
    
    Attributes:
        latest_state: Most recent GripperStateMsg from server
        position: Current gripper position (0-255)
        position_mm: Current position in mm (if calibrated)
        is_activated: Whether gripper is activated
        object_detected: Whether an object is grasped
    """
    
    def __init__(
        self,
        server_ip: str = "localhost",
        cmd_port: int = DEFAULT_CMD_PORT,
        state_port: int = DEFAULT_STATE_PORT,
        timeout: float = 30.0,
    ):
        """Initialize the gripper client.
        
        Args:
            server_ip: IP address of the gripper server
            cmd_port: Port for commands
            state_port: Port for state subscription
            timeout: Timeout for commands in seconds
        """
        self.server_ip = server_ip
        self.cmd_port = cmd_port
        self.state_port = state_port
        self.timeout = timeout
        
        self._zmq_context = None
        self._cmd_socket = None
        self._state_socket = None
        self._connected = False
        
        # Cached state
        self.latest_state: Optional[GripperStateMsg] = None
    
    @property
    def connected(self) -> bool:
        """Check if connected to server."""
        return self._connected
    
    @property
    def position(self) -> int:
        """Get current position (0-255)."""
        if self.latest_state:
            return self.latest_state.position
        return 0
    
    @property
    def position_mm(self) -> float:
        """Get current position in mm."""
        if self.latest_state:
            return self.latest_state.position_mm
        return 0.0
    
    @property
    def is_activated(self) -> bool:
        """Check if gripper is activated."""
        if self.latest_state:
            return self.latest_state.is_activated
        return False
    
    @property
    def is_moving(self) -> bool:
        """Check if gripper is moving."""
        if self.latest_state:
            return self.latest_state.is_moving
        return False
    
    @property
    def object_detected(self) -> bool:
        """Check if object is detected/grasped."""
        if self.latest_state:
            return self.latest_state.object_detected
        return False
    
    @property
    def is_calibrated(self) -> bool:
        """Check if gripper is calibrated for mm positioning."""
        if self.latest_state:
            return self.latest_state.is_calibrated
        return False
    
    @property
    def current(self) -> int:
        """Get motor current (0-255)."""
        if self.latest_state:
            return self.latest_state.current
        return 0
    
    @property
    def current_ma(self) -> float:
        """Get motor current in mA."""
        if self.latest_state:
            return self.latest_state.current_ma
        return 0.0
    
    @property
    def fault_code(self) -> int:
        """Get fault code (0 = no fault)."""
        if self.latest_state:
            return self.latest_state.fault_code
        return 0
    
    @property
    def fault_message(self) -> str:
        """Get fault message."""
        if self.latest_state:
            return self.latest_state.fault_message
        return ""
    
    def connect(self) -> None:
        """Connect to the gripper server."""
        self._zmq_context = zmq.Context()
        
        # Command socket (REQ)
        self._cmd_socket = self._zmq_context.socket(zmq.REQ)
        self._cmd_socket.setsockopt(zmq.RCVTIMEO, int(self.timeout * 1000))
        self._cmd_socket.setsockopt(zmq.SNDTIMEO, int(self.timeout * 1000))
        self._cmd_socket.connect(f"tcp://{self.server_ip}:{self.cmd_port}")
        
        # State socket (SUB)
        self._state_socket = self._zmq_context.socket(zmq.SUB)
        self._state_socket.setsockopt(zmq.CONFLATE, 1)  # Keep only latest
        self._state_socket.setsockopt_string(zmq.SUBSCRIBE, "")
        self._state_socket.setsockopt(zmq.RCVTIMEO, 100)
        self._state_socket.connect(f"tcp://{self.server_ip}:{self.state_port}")
        
        self._connected = True
        logger.info("Connected to %s", self.server_ip)
        
        # Get initial state
        self.update_state()
    
    def disconnect(self) -> None:
        """Disconnect from the server."""
        if self._cmd_socket:
            self._cmd_socket.close()
        if self._state_socket:
            self._state_socket.close()
        if self._zmq_context:
            self._zmq_context.term()
        
        self._cmd_socket = None
        self._state_socket = None
        self._zmq_context = None
        self._connected = False
        
        logger.info("Disconnected")
    
    def update_state(self) -> bool:
        """Update cached state from server.
        
        Returns:
            bool: True if state was updated
        """
        try:
            data = self._state_socket.recv(zmq.NOBLOCK)
            self.latest_state = GripperStateMsg.unpack(data)
            return True
        except zmq.Again:
            return False
    
    def get_state(self) -> Optional[GripperStateMsg]:
        """Get current gripper state.
        
        Returns:
            GripperStateMsg or None: Current state
        """
        self.update_state()
        return self.latest_state
    
    def _send_command(self, cmd) -> Response:
        """Send command and wait for response.
        
        Args:
            cmd: Command object with pack() method
            
        Returns:
            Response: Server response
        """
        if not self._connected:
            raise RuntimeError("Not connected to server")
        
        self._cmd_socket.send(cmd.pack())
        response = Response.unpack(self._cmd_socket.recv())
        return response
    
    def activate(self, reset_first: bool = True) -> bool:
        """Activate/initialize the gripper.
        
        Warning: The gripper will perform a full open/close cycle.
        
        Args:
            reset_first: Whether to reset before activation
            
        Returns:
            bool: True if activation successful
        """
        logger.info("Activating...")
        response = self._send_command(ActivateCmd(reset_first=reset_first))
        
        if response.success:
            logger.info("Activation complete")
        else:
            logger.error("Activation failed: %s", response.message)
        
        self.update_state()
        return response.success
    
    def reset(self) -> bool:
        """Reset the gripper.
        
        Returns:
            bool: True if reset successful
        """
        logger.info("Resetting...")
        response = self._send_command(ResetCmd())
        self.update_state()
        return response.success
    
    def move(
        self,
        position: int,
        speed: int = 255,
        force: int = 255
    ) -> Tuple[int, bool]:
        """Move gripper to specified position.
        
        Args:
            position: Target position (0-255, 0=open, 255=closed)
            speed: Movement speed (0-255)
            force: Grip force (0-255)
            
        Returns:
            Tuple[int, bool]: (final_position, object_detected)
        """
        response = self._send_command(MoveCmd(
            position=position,
            speed=speed,
            force=force
        ))
        
        self.update_state()
        
        if response.data:
            return response.data.get("position", 0), response.data.get("object_detected", False)
        return self.position, False
    
    def open(self, speed: int = 255, force: int = 255) -> Tuple[int, bool]:
        """Open the gripper fully.
        
        Args:
            speed: Movement speed (0-255)
            force: Grip force (0-255)
            
        Returns:
            Tuple[int, bool]: (final_position, object_detected)
        """
        logger.info("Opening...")
        response = self._send_command(OpenCmd(speed=speed, force=force))
        self.update_state()
        
        if response.data:
            return response.data.get("position", 0), response.data.get("object_detected", False)
        return self.position, False
    
    def close(self, speed: int = 255, force: int = 255) -> Tuple[int, bool]:
        """Close the gripper fully.
        
        Args:
            speed: Movement speed (0-255)
            force: Grip force (0-255)
            
        Returns:
            Tuple[int, bool]: (final_position, object_detected)
        """
        logger.info("Closing...")
        response = self._send_command(CloseCmd(speed=speed, force=force))
        self.update_state()
        
        if response.data:
            return response.data.get("position", 0), response.data.get("object_detected", False)
        return self.position, False
    
    def stop(self) -> bool:
        """Stop gripper motion.
        
        Returns:
            bool: True if stop successful
        """
        logger.info("Stopping...")
        response = self._send_command(StopCmd())
        return response.success
    
    def calibrate(self, open_mm: float = 85.0, close_mm: float = 0.0) -> bool:
        """Calibrate the gripper for mm positioning.
        
        This performs a full open/close cycle.
        
        Args:
            open_mm: Distance when fully open (mm)
            close_mm: Distance when fully closed (mm)
            
        Returns:
            bool: True if calibration successful
        """
        logger.info("Calibrating (open=%smm, close=%smm)...", open_mm, close_mm)
        response = self._send_command(CalibrateCmd(
            open_mm=open_mm,
            close_mm=close_mm
        ))
        
        if response.success:
            logger.info("Calibration complete")
        else:
            logger.error("Calibration failed: %s", response.message)
        
        self.update_state()
        return response.success
    
    def move_mm(
        self,
        position_mm: float,
        speed: int = 255,
        force: int = 255
    ) -> Tuple[float, bool]:
        """Move gripper to position in mm.
        
        Requires calibration first.
        
        Args:
            position_mm: Target position in mm
            speed: Movement speed (0-255)
            force: Grip force (0-255)
            
        Returns:
            Tuple[float, bool]: (final_position_mm, object_detected)
        """
        if not self.is_calibrated:
            raise RuntimeError("Gripper must be calibrated for mm positioning")
        
        # Convert mm to bit position
        if self.latest_state:
            open_mm = self.latest_state.open_mm
            close_mm = self.latest_state.close_mm
            
            if abs(open_mm - close_mm) < 0.001:
                raise RuntimeError("Invalid calibration data")
            
            ratio = (position_mm - open_mm) / (close_mm - open_mm)
            position = int(ratio * 255)
            position = max(0, min(255, position))
        else:
            raise RuntimeError("No state available")
        
        final_pos, obj_detected = self.move(position, speed, force)
        
        # Convert back to mm
        final_mm = open_mm + (final_pos / 255.0) * (close_mm - open_mm)
        return final_mm, obj_detected
    
    def grasp(
        self,
        speed: int = 255,
        force: int = 255,
        detect_object: bool = True
    ) -> bool:
        """Close gripper to grasp an object.
        
        Args:
            speed: Movement speed (0-255)
            force: Grip force (0-255)
            detect_object: If True, return whether object was detected
            
        Returns:
            bool: True if object was grasped (or close completed if detect_object=False)
        """
        _, obj_detected = self.close(speed, force)
        
        if detect_object:
            return obj_detected
        return True
    
    def release(self, speed: int = 255) -> bool:
        """Open gripper to release an object.
        
        Args:
            speed: Movement speed (0-255)
            
        Returns:
            bool: True if release completed
        """
        self.open(speed)
        return True
    
    def print_status(self) -> None:
        """Print current gripper status."""
        self.update_state()
        
        if not self.latest_state:
            logger.info("No state available")
            return

        state = self.latest_state
        info_lines = [
            "=== Gripper Status ===",
            "Connected: %s" % self._connected,
            "Activated: %s" % state.is_activated,
            "Position: %s/255" % state.position,
        ]
        if state.is_calibrated:
            info_lines.append("Position (mm): %.2f" % state.position_mm)
        info_lines.extend([
            "Current: %.0f mA" % state.current_ma,
            "Object detected: %s" % state.object_detected,
            "Moving: %s" % state.is_moving,
            "Calibrated: %s" % state.is_calibrated,
            "Fault: %s" % state.fault_message,
            "=====================",
        ])
        logger.info("\n".join(info_lines))
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, *args):
        """Context manager exit."""
        self.disconnect()
