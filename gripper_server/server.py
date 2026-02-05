"""
Gripper Server - Handles gripper commands via ZMQ.

This server runs in a virtual environment with access to the gripper hardware
and exposes a ZMQ interface for remote control.
"""

import argparse
import os
import signal
import subprocess
import sys
import time
import threading
from typing import Optional

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

# Force unbuffered print output for immediate log visibility
import functools
print = functools.partial(print, flush=True)


def kill_port_users(port: int) -> None:
    """Kill any process using the specified port."""
    try:
        result = subprocess.run(
            ["fuser", "-k", f"{port}/tcp"],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            print(f"[GripperServer] Killed process using port {port}")
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
                        print(f"[GripperServer] Killed PID {pid} using port {port}")
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
            print(f"[GripperServer] Initializing {self.gripper_type} gripper...")
            self.gripper = get_gripper(self.gripper_type, **self.gripper_kwargs)
            
            if not self.gripper.connect():
                print("[GripperServer] Failed to connect to gripper")
                return False
            
            print("[GripperServer] Gripper connected successfully")
            return True
            
        except Exception as e:
            print(f"[GripperServer] Gripper initialization failed: {e}")
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
        self._cmd_socket.bind(f"tcp://*:{self.cmd_port}")
        
        # State socket (PUB)
        self._state_socket = self._zmq_context.socket(zmq.PUB)
        self._state_socket.setsockopt(zmq.LINGER, 0)
        self._state_socket.bind(f"tcp://*:{self.state_port}")
        
        print(f"[GripperServer] ZMQ sockets initialized:")
        print(f"  - Command: tcp://*:{self.cmd_port}")
        print(f"  - State: tcp://*:{self.state_port}")
    
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
                print(f"[GripperServer] Activating (reset_first={cmd.reset_first})")
                success = self.gripper.activate(reset_first=cmd.reset_first)
                return Response(
                    success=success,
                    message="Activation complete" if success else "Activation failed"
                ).pack()
            
            elif isinstance(cmd, ResetCmd):
                print("[GripperServer] Resetting")
                success = self.gripper.reset()
                return Response(
                    success=success,
                    message="Reset complete" if success else "Reset failed"
                ).pack()
            
            elif isinstance(cmd, MoveCmd):
                print(f"[GripperServer] Moving to position={cmd.position}, speed={cmd.speed}, force={cmd.force}")
                final_pos, obj_detected = self.gripper.move(cmd.position, cmd.speed, cmd.force)
                return Response(
                    success=True,
                    message="Object detected" if obj_detected else "Position reached",
                    data={"position": final_pos, "object_detected": obj_detected}
                ).pack()
            
            elif isinstance(cmd, OpenCmd):
                print(f"[GripperServer] Opening (speed={cmd.speed}, force={cmd.force})")
                final_pos, obj_detected = self.gripper.open(cmd.speed, cmd.force)
                return Response(
                    success=True,
                    message="Open complete",
                    data={"position": final_pos, "object_detected": obj_detected}
                ).pack()
            
            elif isinstance(cmd, CloseCmd):
                print(f"[GripperServer] Closing (speed={cmd.speed}, force={cmd.force})")
                final_pos, obj_detected = self.gripper.close(cmd.speed, cmd.force)
                return Response(
                    success=True,
                    message="Object detected" if obj_detected else "Close complete",
                    data={"position": final_pos, "object_detected": obj_detected}
                ).pack()
            
            elif isinstance(cmd, StopCmd):
                print("[GripperServer] Stopping")
                success = self.gripper.stop()
                return Response(
                    success=success,
                    message="Stopped" if success else "Stop failed"
                ).pack()
            
            elif isinstance(cmd, CalibrateCmd):
                print(f"[GripperServer] Calibrating (open={cmd.open_mm}mm, close={cmd.close_mm}mm)")
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
            print(f"[GripperServer] Error handling command: {e}")
            return Response(success=False, message=str(e)).pack()
    
    def _command_loop(self) -> None:
        """Main command processing loop."""
        print("[GripperServer] Command loop started")
        
        while self._running:
            try:
                # Poll for commands with timeout
                if self._cmd_socket.poll(timeout=100):
                    data = self._cmd_socket.recv()
                    response = self._handle_command(data)
                    self._cmd_socket.send(response)
            except zmq.ZMQError as e:
                if self._running:
                    print(f"[GripperServer] ZMQ error: {e}")
            except Exception as e:
                if self._running:
                    print(f"[GripperServer] Command error: {e}")
        
        print("[GripperServer] Command loop stopped")
    
    def _state_publish_loop(self) -> None:
        """State publishing loop."""
        print(f"[GripperServer] State publishing at {self.state_publish_rate} Hz")
        
        interval = 1.0 / self.state_publish_rate
        
        while self._running:
            try:
                state_msg = self._build_state_msg()
                self._state_socket.send(state_msg.pack())
                time.sleep(interval)
            except Exception as e:
                if self._running:
                    print(f"[GripperServer] State publish error: {e}")
                time.sleep(0.1)
        
        print("[GripperServer] State publishing stopped")
    
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
        
        print("[GripperServer] Server started")
        return True
    
    def stop(self) -> None:
        """Stop the gripper server."""
        print("[GripperServer] Stopping...")
        
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
        
        print("[GripperServer] Server stopped")
    
    def run(self) -> None:
        """Run the server (blocking)."""
        if not self.start():
            print("[GripperServer] Failed to start server")
            return
        
        print("\n[GripperServer] Press Ctrl+C to stop\n")
        
        try:
            while self._running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n[GripperServer] Interrupted")
        
        self.stop()


def main():
    """Main entry point for gripper server."""
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
        print("\n[GripperServer] Signal received, stopping...")
        server.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    server.run()


if __name__ == "__main__":
    main()
