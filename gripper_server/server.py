"""
Gripper Server - Handles gripper commands via ZMQ.

This server runs in a virtual environment with access to the gripper hardware
and exposes a ZMQ interface for remote control.
"""

import argparse
import logging
import os
import signal
import subprocess
import sys
import time
import threading
from typing import Optional

# Project-level logging setup
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from logging_config import setup_logging

try:
    import zmq
except ImportError:
    raise ImportError("ZMQ not installed. Run: pip install pyzmq")

try:
    import msgpack
except ImportError:
    raise ImportError("msgpack not installed. Run: pip install msgpack")

from gripper_server.protocol import (
    MessageType,
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
    unpack_command,
    DEFAULT_CMD_PORT,
    DEFAULT_STATE_PORT,
)
from gripper_server.grippers import get_gripper, BaseGripper

logger = logging.getLogger(__name__)


def kill_port_users(port: int) -> None:
    """Kill any process using the specified port."""
    try:
        result = subprocess.run(
            ["fuser", "-k", f"{port}/tcp"],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            logger.info("Killed process using port %s", port)
            time.sleep(0.5)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        try:
            result = subprocess.run(
                ["lsof", "-t", f"-i:{port}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    try:
                        os.kill(int(pid), signal.SIGKILL)
                        logger.info("Killed PID %s using port %s", pid, port)
                    except (ProcessLookupError, ValueError):
                        pass
                time.sleep(0.5)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass


class GripperServer:
    """Gripper control server using ZMQ for communication.
    
    Supports multiple gripper types through a common interface.
    
    Example:
        server = GripperServer(gripper_type="robotiq", port="/dev/ttyUSB0")
        server.start()
    """
    
    def __init__(
        self,
        gripper_type: str = "robotiq",
        cmd_port: int = DEFAULT_CMD_PORT,
        state_port: int = DEFAULT_STATE_PORT,
        state_publish_rate: float = 10.0,
        **gripper_kwargs
    ):
        """Initialize the gripper server.
        
        Args:
            gripper_type: Type of gripper (e.g., "robotiq")
            cmd_port: Port for command socket (REQ/REP)
            state_port: Port for state publishing (PUB/SUB)
            state_publish_rate: Rate at which to publish state (Hz)
            **gripper_kwargs: Additional arguments for gripper constructor
        """
        self.gripper_type = gripper_type
        self.cmd_port = cmd_port
        self.state_port = state_port
        self.state_publish_rate = state_publish_rate
        self.gripper_kwargs = gripper_kwargs
        
        self.gripper: Optional[BaseGripper] = None
        self._running = False
        
        # ZMQ
        self._zmq_context = None
        self._cmd_socket = None
        self._state_socket = None
        
        # Threads
        self._cmd_thread = None
        self._state_thread = None
    
    def _init_gripper(self) -> bool:
        """Initialize the gripper hardware."""
        try:
            logger.info("Initializing %s gripper...", self.gripper_type)
            self.gripper = get_gripper(self.gripper_type, **self.gripper_kwargs)
            
            if not self.gripper.connect():
                logger.error("Failed to connect to gripper")
                return False
            
            logger.info("Gripper connected successfully")
            return True
            
        except Exception as e:
            logger.error("Gripper initialization failed: %s", e)
            return False
    
    def _init_zmq(self) -> None:
        """Initialize ZMQ sockets."""
        # Kill any leftover processes
        kill_port_users(self.cmd_port)
        kill_port_users(self.state_port)
        
        self._zmq_context = zmq.Context()
        
        # Command socket (REQ/REP)
        self._cmd_socket = self._zmq_context.socket(zmq.REP)
        self._cmd_socket.setsockopt(zmq.LINGER, 0)
        self._cmd_socket.bind(f"tcp://127.0.0.1:{self.cmd_port}")
        
        # State socket (PUB)
        self._state_socket = self._zmq_context.socket(zmq.PUB)
        self._state_socket.setsockopt(zmq.LINGER, 0)
        self._state_socket.bind(f"tcp://127.0.0.1:{self.state_port}")
        
        logger.info("ZMQ sockets initialized: Command=tcp://127.0.0.1:%s, State=tcp://127.0.0.1:%s",
                    self.cmd_port, self.state_port)
    
    def _cleanup_zmq(self) -> None:
        """Cleanup ZMQ resources."""
        if self._cmd_socket:
            self._cmd_socket.close()
        if self._state_socket:
            self._state_socket.close()
        if self._zmq_context:
            self._zmq_context.term()
    
    def _get_gripper_type_enum(self) -> int:
        """Get GripperType enum value for current gripper."""
        type_map = {
            "robotiq": GripperType.ROBOTIQ_2F85,
            "robotiq_2f85": GripperType.ROBOTIQ_2F85,
            "robotiq_2f140": GripperType.ROBOTIQ_2F140,
            "robotiq_hande": GripperType.ROBOTIQ_HANDE,
        }
        return type_map.get(self.gripper_type.lower(), GripperType.UNKNOWN)
    
    def _build_state_msg(self) -> GripperStateMsg:
        """Build state message from current gripper state."""
        state = self.gripper.read_state()
        
        return GripperStateMsg(
            timestamp=time.time(),
            gripper_type=self._get_gripper_type_enum(),
            position=state.position,
            position_mm=state.position_mm,
            position_request=state.position_request,
            current=state.current,
            current_ma=state.current * 10.0,
            is_activated=state.is_activated,
            is_moving=state.is_moving,
            object_detected=state.object_detected,
            is_calibrated=state.is_calibrated,
            open_mm=state.open_mm,
            close_mm=state.close_mm,
            fault_code=state.fault_code,
            fault_message=state.fault_message,
        )
    
    def _handle_command(self, data: bytes) -> bytes:
        """Handle incoming command and return response."""
        try:
            cmd = unpack_command(data)
            
            if isinstance(cmd, ActivateCmd):
                logger.info("Activating (reset_first=%s)", cmd.reset_first)
                success = self.gripper.activate(reset_first=cmd.reset_first)
                return Response(
                    success=success,
                    message="Activation complete" if success else "Activation failed"
                ).pack()
            
            elif isinstance(cmd, ResetCmd):
                logger.info("Resetting")
                success = self.gripper.reset()
                return Response(
                    success=success,
                    message="Reset complete" if success else "Reset failed"
                ).pack()
            
            elif isinstance(cmd, MoveCmd):
                logger.info("Moving to position=%s, speed=%s, force=%s", cmd.position, cmd.speed, cmd.force)
                final_pos, obj_detected = self.gripper.move(cmd.position, cmd.speed, cmd.force)
                return Response(
                    success=True,
                    message="Object detected" if obj_detected else "Position reached",
                    data={"position": final_pos, "object_detected": obj_detected}
                ).pack()
            
            elif isinstance(cmd, OpenCmd):
                logger.info("Opening (speed=%s, force=%s)", cmd.speed, cmd.force)
                final_pos, obj_detected = self.gripper.open(cmd.speed, cmd.force)
                return Response(
                    success=True,
                    message="Open complete",
                    data={"position": final_pos, "object_detected": obj_detected}
                ).pack()
            
            elif isinstance(cmd, CloseCmd):
                logger.info("Closing (speed=%s, force=%s)", cmd.speed, cmd.force)
                final_pos, obj_detected = self.gripper.close(cmd.speed, cmd.force)
                return Response(
                    success=True,
                    message="Object detected" if obj_detected else "Close complete",
                    data={"position": final_pos, "object_detected": obj_detected}
                ).pack()
            
            elif isinstance(cmd, StopCmd):
                logger.info("Stopping")
                success = self.gripper.stop()
                return Response(
                    success=success,
                    message="Stopped" if success else "Stop failed"
                ).pack()
            
            elif isinstance(cmd, CalibrateCmd):
                logger.info("Calibrating (open=%smm, close=%smm)", cmd.open_mm, cmd.close_mm)
                success = self.gripper.calibrate(cmd.open_mm, cmd.close_mm)
                return Response(
                    success=success,
                    message="Calibration complete" if success else "Calibration failed"
                ).pack()
            
            else:
                return Response(
                    success=False,
                    message=f"Unknown command type"
                ).pack()
                
        except Exception as e:
            logger.error("Error handling command: %s", e)
            return Response(success=False, message=str(e)).pack()
    
    def _command_loop(self) -> None:
        """Main command processing loop."""
        logger.info("Command loop started")
        
        while self._running:
            try:
                # Poll for commands with timeout
                if self._cmd_socket.poll(timeout=100):
                    data = self._cmd_socket.recv()
                    response = self._handle_command(data)
                    self._cmd_socket.send(response)
            except zmq.ZMQError as e:
                if self._running:
                    logger.error("ZMQ error: %s", e)
            except Exception as e:
                if self._running:
                    logger.error("Command error: %s", e)
        
        logger.info("Command loop stopped")
    
    def _state_publish_loop(self) -> None:
        """State publishing loop."""
        logger.info("State publishing at %s Hz", self.state_publish_rate)
        
        interval = 1.0 / self.state_publish_rate
        
        while self._running:
            try:
                state_msg = self._build_state_msg()
                self._state_socket.send(state_msg.pack())
                time.sleep(interval)
            except Exception as e:
                if self._running:
                    logger.error("State publish error: %s", e)
                time.sleep(0.1)
        
        logger.info("State publishing stopped")
    
    def start(self) -> bool:
        """Start the gripper server.
        
        Returns:
            bool: True if server started successfully
        """
        # Initialize gripper
        if not self._init_gripper():
            return False
        
        # Initialize ZMQ
        self._init_zmq()
        
        self._running = True
        
        # Start command thread
        self._cmd_thread = threading.Thread(target=self._command_loop, daemon=True)
        self._cmd_thread.start()
        
        # Start state publishing thread
        self._state_thread = threading.Thread(target=self._state_publish_loop, daemon=True)
        self._state_thread.start()
        
        logger.info("Server started")
        return True
    
    def stop(self) -> None:
        """Stop the gripper server."""
        logger.info("Stopping...")
        
        self._running = False
        
        # Wait for threads
        if self._cmd_thread:
            self._cmd_thread.join(timeout=2.0)
        if self._state_thread:
            self._state_thread.join(timeout=2.0)
        
        # Cleanup ZMQ
        self._cleanup_zmq()
        
        # Disconnect gripper
        if self.gripper:
            self.gripper.disconnect()
        
        logger.info("Server stopped")
    
    def run(self) -> None:
        """Run the server (blocking)."""
        if not self.start():
            logger.error("Failed to start server")
            return
        
        logger.info("Press Ctrl+C to stop")
        
        try:
            while self._running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("Interrupted")
        
        self.stop()


def main():
    """Main entry point for gripper server."""
    setup_logging("gripper_server")

    parser = argparse.ArgumentParser(description="Gripper Server")
    
    parser.add_argument(
        "--gripper", "-g",
        type=str,
        default="robotiq",
        help="Gripper type (default: robotiq)"
    )
    parser.add_argument(
        "--port", "-p",
        type=str,
        default="auto",
        help="Serial port for gripper (default: auto)"
    )
    parser.add_argument(
        "--slave-address",
        type=int,
        default=9,
        help="Modbus slave address for Robotiq gripper (default: 9)"
    )
    parser.add_argument(
        "--cmd-port",
        type=int,
        default=DEFAULT_CMD_PORT,
        help=f"Command port (default: {DEFAULT_CMD_PORT})"
    )
    parser.add_argument(
        "--state-port",
        type=int,
        default=DEFAULT_STATE_PORT,
        help=f"State port (default: {DEFAULT_STATE_PORT})"
    )
    parser.add_argument(
        "--state-rate",
        type=float,
        default=10.0,
        help="State publish rate in Hz (default: 10.0)"
    )
    
    args = parser.parse_args()
    
    # Build gripper kwargs
    gripper_kwargs = {}
    if args.port != "auto":
        gripper_kwargs["port"] = args.port
    if args.slave_address != 9:
        gripper_kwargs["slave_address"] = args.slave_address
    
    # Create and run server
    server = GripperServer(
        gripper_type=args.gripper,
        cmd_port=args.cmd_port,
        state_port=args.state_port,
        state_publish_rate=args.state_rate,
        **gripper_kwargs
    )
    
    # Handle signals
    def signal_handler(sig, frame):
        logger.info("Signal received, stopping...")
        server.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    server.run()


if __name__ == "__main__":
    main()
