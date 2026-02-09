"""
Robotiq Gripper Driver

Driver for Robotiq 2F-85, 2F-140, and Hand-E grippers via Modbus RTU
over USB/RS485 connection.

Based on the pyRobotiqGripper library by Benoit CASTETS.
"""

import logging
import time
from typing import Tuple, Optional

try:
    import minimalmodbus as mm
    import serial
    import serial.tools.list_ports
except ImportError:
    raise ImportError(
        "Serial communication libraries not installed. "
        "Run: pip install pyserial minimalmodbus"
    )

from gripper_server.grippers.base import BaseGripper, GripperState

logger = logging.getLogger(__name__)

# Serial communication constants
BAUDRATE = 115200
BYTESIZE = 8
PARITY = "N"
STOPBITS = 1
TIMEOUT = 0.2

# Default slave address for Robotiq grippers
DEFAULT_SLAVE_ADDRESS = 9


class RobotiqGripper(BaseGripper):
    """Driver for Robotiq grippers (2F-85, 2F-140, Hand-E).
    
    Communicates via Modbus RTU over USB/RS485 connection.
    
    Example:
        gripper = RobotiqGripper(port="/dev/ttyUSB0")
        gripper.connect()
        gripper.activate()
        gripper.open()
        gripper.close(force=200)
    """
    
    def __init__(
        self,
        port: str = "auto",
        slave_address: int = DEFAULT_SLAVE_ADDRESS,
        timeout: float = 10.0,
    ):
        """Initialize Robotiq gripper driver.
        
        Args:
            port: Serial port name (e.g., "/dev/ttyUSB0") or "auto" for auto-detection
            slave_address: Modbus slave address (usually 9)
            timeout: Timeout for gripper operations in seconds
        """
        super().__init__()
        
        self._port = port
        self._slave_address = slave_address
        self._timeout = timeout
        
        self._serial = None
        self._instrument = None
        
        # Calibration coefficients for mm conversion
        self._a_coef = None
        self._b_coef = None
        self._open_bit = None
        self._close_bit = None
    
    def connect(self) -> bool:
        """Connect to the gripper via serial port.
        
        Returns:
            bool: True if connection successful
        """
        try:
            # Auto-detect port if needed
            if self._port == "auto":
                self._port = self._auto_detect_port()
                if self._port is None:
                    logger.error("No gripper detected")
                    return False
            
            # Create serial connection
            self._serial = serial.Serial(
                self._port,
                BAUDRATE,
                BYTESIZE,
                PARITY,
                STOPBITS,
                TIMEOUT
            )
            
            # Create Modbus instrument
            self._instrument = mm.Instrument(
                self._serial,
                self._slave_address,
                mm.MODE_RTU,
                close_port_after_each_call=False,
                debug=False
            )
            
            self._connected = True
            logger.info("Connected on %s", self._port)
            
            # Read initial state
            self.read_state()
            
            return True
            
        except Exception as e:
            logger.error("Connection failed: %s", e)
            self._connected = False
            return False
    
    def disconnect(self) -> None:
        """Disconnect from the gripper."""
        if self._serial:
            try:
                self._serial.close()
            except:
                pass
        self._serial = None
        self._instrument = None
        self._connected = False
        logger.info("Disconnected")
    
    def _auto_detect_port(self, verbose: bool = True) -> Optional[str]:
        """Auto-detect the serial port with a connected Robotiq gripper.
        
        Args:
            verbose: Print debug information during detection
        
        Returns:
            str or None: Port name if found, None otherwise
        """
        ports = serial.tools.list_ports.comports()
        
        if verbose:
            logger.debug("Scanning %s serial ports...", len(ports))
            for p in ports:
                logger.debug("  - %s: %s", p.device, p.description)
        
        if not ports:
            if verbose:
                logger.warning("No serial ports found")
            return None
        
        for port in ports:
            if verbose:
                logger.debug("Trying %s...", port.device)
            
            ser = None
            try:
                ser = serial.Serial(
                    port.device,
                    BAUDRATE,
                    BYTESIZE,
                    PARITY,
                    STOPBITS,
                    TIMEOUT
                )
                
                device = mm.Instrument(
                    ser,
                    self._slave_address,
                    mm.MODE_RTU,
                    close_port_after_each_call=False,
                    debug=False
                )
                
                # Try to write a position and read it back
                device.write_registers(1000, [0, 100, 0])
                time.sleep(0.1)  # Give gripper time to respond
                registers = device.read_registers(2000, 3, 4)
                pos_echo = registers[1] & 0b11111111
                
                ser.close()
                
                if pos_echo == 100:
                    logger.info("Found gripper on %s", port.device)
                    return port.device
                else:
                    if verbose:
                        logger.debug("%s: Response mismatch (got %s, expected 100)", port.device, pos_echo)
                    
            except Exception as e:
                if verbose:
                    logger.debug("%s: %s", port.device, e)
                if ser:
                    try:
                        ser.close()
                    except:
                        pass
        
        return None
    
    def _write_registers(self, address: int, values: list) -> None:
        """Write to gripper registers."""
        if not self._connected:
            raise RuntimeError("Gripper not connected")
        self._instrument.write_registers(address, values)
    
    def _read_registers(self, address: int, count: int) -> list:
        """Read from gripper registers."""
        if not self._connected:
            raise RuntimeError("Gripper not connected")
        return self._instrument.read_registers(address, count, 4)
    
    def read_state(self) -> GripperState:
        """Read current state from gripper hardware.
        
        Returns:
            GripperState: Current gripper state
        """
        if not self._connected:
            return self._state
        
        try:
            # Read 3 16-bit registers starting from 2000
            registers = self._read_registers(2000, 3)
            
            # Register 2000 - Gripper Status
            gripper_status = (registers[0] >> 8) & 0xFF
            
            # Object detection (gOBJ)
            g_obj = (gripper_status >> 6) & 0b11
            # Gripper status (gSTA)
            g_sta = (gripper_status >> 4) & 0b11
            # Go-to status (gGTO)
            g_gto = (gripper_status >> 3) & 0b1
            # Activation status (gACT)
            g_act = gripper_status & 0b1
            
            # Register 2001 - Fault status and position request echo
            fault_status = (registers[1] >> 8) & 0xFF
            g_flt = fault_status & 0b1111
            pos_request = registers[1] & 0xFF
            
            # Register 2002 - Position and current
            position = (registers[2] >> 8) & 0xFF
            current = registers[2] & 0xFF
            
            # Update state
            self._state.position = position
            self._state.position_request = pos_request
            self._state.current = current
            self._state.is_activated = (g_sta == 3)
            self._state.is_moving = (g_obj == 0 and g_gto == 1)
            self._state.object_detected = (g_obj == 1 or g_obj == 2)
            self._state.fault_code = g_flt
            self._state.fault_message = self._get_fault_message(g_flt)
            
            # Update mm position if calibrated
            if self._state.is_calibrated:
                self._state.position_mm = self._bit_to_mm(position)
            
        except Exception as e:
            logger.error("Error reading state: %s", e)
        
        return self._state
    
    def _get_fault_message(self, fault_code: int) -> str:
        """Get human-readable fault message."""
        fault_messages = {
            0: "No fault",
            5: "Action delayed - reactivation required",
            7: "Activation bit must be set prior to action",
            8: "Max temperature exceeded - wait for cool-down",
            9: "No communication for 1 second",
            10: "Under minimum voltage - reset required",
            11: "Automatic release in progress",
            12: "Internal fault - contact support",
            13: "Activation fault - verify no interference",
            14: "Overcurrent triggered",
            15: "Automatic release completed",
        }
        return fault_messages.get(fault_code, f"Unknown fault: {fault_code}")
    
    def activate(self, reset_first: bool = True) -> bool:
        """Activate the gripper.
        
        Warning: The gripper will fully open and close during activation.
        Ensure the gripper can move freely.
        
        Args:
            reset_first: Whether to reset before activation
            
        Returns:
            bool: True if activation successful
        """
        if not self._connected:
            return False
        
        try:
            if reset_first:
                self.reset()
                time.sleep(0.5)
            
            # Activate: rACT=1
            self._write_registers(1000, [0b0000000100000000, 0, 0])
            
            # Wait for activation to complete
            start_time = time.time()
            
            while time.time() - start_time < self._timeout:
                self.read_state()
                
                if self._state.is_activated:
                    logger.info("Activation completed in %.2fs", time.time() - start_time)
                    return True
                
                time.sleep(0.1)
            
            logger.warning("Activation timed out")
            return False
            
        except Exception as e:
            logger.error("Activation failed: %s", e)
            return False
    
    def reset(self) -> bool:
        """Reset the gripper.
        
        Returns:
            bool: True if reset successful
        """
        if not self._connected:
            return False
        
        try:
            self._write_registers(1000, [0, 0, 0])
            self._state.is_activated = False
            logger.info("Reset")
            return True
        except Exception as e:
            logger.error("Reset failed: %s", e)
            return False
    
    def move(self, position: int, speed: int = 255, force: int = 255) -> Tuple[int, bool]:
        """Move gripper to specified position.
        
        Args:
            position: Target position (0-255, 0=open, 255=closed)
            speed: Movement speed (0-255)
            force: Grip force (0-255)
            
        Returns:
            Tuple[int, bool]: (final_position, object_detected)
        """
        if not self._connected:
            raise RuntimeError("Gripper not connected")
        
        if not self._state.is_activated:
            raise RuntimeError("Gripper not activated")
        
        # Clamp values
        position = max(0, min(255, int(position)))
        speed = max(0, min(255, int(speed)))
        force = max(0, min(255, int(force)))
        
        try:
            # rACT=1, rGTO=1 (Go to position)
            # Register 0: 0b0000100100000000 = rGTO(3) + rACT(0)
            # Register 1: position
            # Register 2: speed * 256 + force
            self._write_registers(1000, [
                0b0000100100000000,
                position,
                speed * 256 + force
            ])
            
            # Wait for motion to complete
            start_time = time.time()
            
            while time.time() - start_time < self._timeout:
                self.read_state()
                
                # Check if motion completed or object detected
                g_obj_status = self._get_object_status()
                
                if g_obj_status in [1, 2]:  # Object detected
                    return self._state.position, True
                elif g_obj_status == 3:  # Position reached, no object
                    return self._state.position, False
                
                time.sleep(0.05)
            
            logger.warning("Move timed out")
            return self._state.position, False
            
        except Exception as e:
            logger.error("Move failed: %s", e)
            return self._state.position, False
    
    def _get_object_status(self) -> int:
        """Get object detection status from latest state read.
        
        Returns:
            int: 0=moving, 1=object opening, 2=object closing, 3=at position
        """
        registers = self._read_registers(2000, 1)
        gripper_status = (registers[0] >> 8) & 0xFF
        return (gripper_status >> 6) & 0b11
    
    def open(self, speed: int = 255, force: int = 255) -> Tuple[int, bool]:
        """Open the gripper fully.
        
        Args:
            speed: Movement speed (0-255)
            force: Grip force (0-255)
            
        Returns:
            Tuple[int, bool]: (final_position, object_detected)
        """
        return self.move(0, speed, force)
    
    def close(self, speed: int = 255, force: int = 255) -> Tuple[int, bool]:
        """Close the gripper fully.
        
        Args:
            speed: Movement speed (0-255)
            force: Grip force (0-255)
            
        Returns:
            Tuple[int, bool]: (final_position, object_detected)
        """
        return self.move(255, speed, force)
    
    def stop(self) -> bool:
        """Stop gripper motion.
        
        Note: Robotiq grippers don't have an explicit stop command.
        This is implemented by sending the current position as target.
        
        Returns:
            bool: True if stop successful
        """
        if not self._connected:
            return False
        
        try:
            self.read_state()
            # Move to current position to stop
            self.move(self._state.position, speed=0, force=0)
            return True
        except Exception as e:
            logger.error("Stop failed: %s", e)
            return False
    
    def calibrate(self, open_mm: float, close_mm: float) -> bool:
        """Calibrate the gripper for mm positioning.
        
        This performs a full open/close cycle to determine bit positions
        at the calibration points.
        
        Args:
            open_mm: Distance between fingers when fully open (mm)
            close_mm: Distance between fingers when fully closed (mm)
            
        Returns:
            bool: True if calibration successful
        """
        if not self._connected or not self._state.is_activated:
            return False
        
        try:
            self._state.open_mm = open_mm
            self._state.close_mm = close_mm
            
            # Open fully and record position
            self.open()
            self.read_state()
            self._open_bit = self._state.position
            
            # Close fully and record position
            self.close()
            self.read_state()
            self._close_bit = self._state.position
            
            # Calculate conversion coefficients
            # mm = a * bit + b
            o_bit = self._open_bit
            c_bit = self._close_bit
            
            if abs(c_bit - o_bit) < 1:
                logger.error("Calibration failed - no movement detected")
                return False
            
            self._a_coef = (close_mm - open_mm) / (c_bit - o_bit)
            self._b_coef = (open_mm * c_bit - o_bit * close_mm) / (c_bit - o_bit)
            
            self._state.is_calibrated = True
            logger.info("Calibrated: open=%s, close=%s", o_bit, c_bit)
            
            return True
            
        except Exception as e:
            logger.error("Calibration failed: %s", e)
            return False
    
    def _mm_to_bit(self, mm: float) -> int:
        """Convert mm position to bit position."""
        if not self._state.is_calibrated or self._a_coef is None:
            raise RuntimeError("Gripper not calibrated")
        
        bit = (mm - self._b_coef) / self._a_coef
        return max(0, min(255, int(bit)))
    
    def _bit_to_mm(self, bit: int) -> float:
        """Convert bit position to mm position."""
        if not self._state.is_calibrated or self._a_coef is None:
            raise RuntimeError("Gripper not calibrated")
        
        return self._a_coef * bit + self._b_coef
    
    def move_mm(self, position_mm: float, speed: int = 255, force: int = 255) -> Tuple[float, bool]:
        """Move gripper to position specified in mm.
        
        Args:
            position_mm: Target position in mm
            speed: Movement speed (0-255)
            force: Grip force (0-255)
            
        Returns:
            Tuple[float, bool]: (final_position_mm, object_detected)
        """
        if not self._state.is_calibrated:
            raise RuntimeError("Gripper must be calibrated for mm positioning")
        
        if position_mm > self._state.open_mm:
            logger.warning("Requested %smm exceeds max %smm", position_mm, self._state.open_mm)
            position_mm = self._state.open_mm
        
        position = self._mm_to_bit(position_mm)
        final_pos, obj_detected = self.move(position, speed, force)
        return self._bit_to_mm(final_pos), obj_detected
    
    def get_position_mm(self) -> Optional[float]:
        """Get current position in mm.
        
        Returns:
            float or None: Position in mm, or None if not calibrated
        """
        if not self._state.is_calibrated:
            return None
        self.read_state()
        return self._bit_to_mm(self._state.position)
    
    def print_info(self) -> None:
        """Print gripper status information."""
        self.read_state()
        info_lines = [
            "=== Robotiq Gripper Status ===",
            "Port: %s" % self._port,
            "Connected: %s" % self._connected,
            "Activated: %s" % self._state.is_activated,
            "Position: %s/255" % self._state.position,
            "Current: %s mA" % (self._state.current * 10),
            "Object detected: %s" % self._state.object_detected,
            "Moving: %s" % self._state.is_moving,
            "Calibrated: %s" % self._state.is_calibrated,
        ]
        if self._state.is_calibrated:
            info_lines.append("Position (mm): %.2f" % self.get_position_mm())
        info_lines.append("Fault: %s" % self._state.fault_message)
        info_lines.append("==============================")
        logger.info("\n".join(info_lines))
