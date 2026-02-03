"""
Base Gripper Interface

Defines the abstract interface that all gripper implementations must follow.
This allows the server to work with any gripper type through a common API.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Tuple, Optional


@dataclass
class GripperState:
    """Internal gripper state representation.
    
    This is the internal format used by gripper implementations.
    It gets converted to GripperStateMsg for network transmission.
    """
    # Position
    position: int = 0           # Current position (0-255)
    position_request: int = 0   # Requested position echo
    
    # Motor
    current: int = 0            # Motor current (0-255)
    
    # Status
    is_activated: bool = False
    is_moving: bool = False
    object_detected: bool = False
    
    # Calibration
    is_calibrated: bool = False
    position_mm: float = 0.0
    open_mm: float = 0.0
    close_mm: float = 0.0
    
    # Faults
    fault_code: int = 0
    fault_message: str = ""


class BaseGripper(ABC):
    """Abstract base class for gripper implementations.
    
    All gripper drivers must inherit from this class and implement
    the required methods.
    """
    
    def __init__(self):
        """Initialize the base gripper."""
        self._state = GripperState()
        self._connected = False
    
    @property
    def connected(self) -> bool:
        """Check if gripper is connected."""
        return self._connected
    
    @property
    def state(self) -> GripperState:
        """Get current gripper state."""
        return self._state
    
    @abstractmethod
    def connect(self) -> bool:
        """Connect to the gripper hardware.
        
        Returns:
            bool: True if connection successful
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the gripper hardware."""
        pass
    
    @abstractmethod
    def activate(self, reset_first: bool = True) -> bool:
        """Activate/initialize the gripper.
        
        Args:
            reset_first: Whether to reset the gripper before activation
            
        Returns:
            bool: True if activation successful
        """
        pass
    
    @abstractmethod
    def reset(self) -> bool:
        """Reset the gripper.
        
        Returns:
            bool: True if reset successful
        """
        pass
    
    @abstractmethod
    def move(self, position: int, speed: int = 255, force: int = 255) -> Tuple[int, bool]:
        """Move gripper to specified position.
        
        Args:
            position: Target position (0-255, 0=open, 255=closed)
            speed: Movement speed (0-255)
            force: Grip force (0-255)
            
        Returns:
            Tuple[int, bool]: (final_position, object_detected)
        """
        pass
    
    @abstractmethod
    def open(self, speed: int = 255, force: int = 255) -> Tuple[int, bool]:
        """Open the gripper fully.
        
        Args:
            speed: Movement speed (0-255)
            force: Grip force (0-255)
            
        Returns:
            Tuple[int, bool]: (final_position, object_detected)
        """
        pass
    
    @abstractmethod
    def close(self, speed: int = 255, force: int = 255) -> Tuple[int, bool]:
        """Close the gripper fully.
        
        Args:
            speed: Movement speed (0-255)
            force: Grip force (0-255)
            
        Returns:
            Tuple[int, bool]: (final_position, object_detected)
        """
        pass
    
    @abstractmethod
    def stop(self) -> bool:
        """Stop gripper motion immediately.
        
        Returns:
            bool: True if stop command successful
        """
        pass
    
    @abstractmethod
    def read_state(self) -> GripperState:
        """Read current state from gripper hardware.
        
        Returns:
            GripperState: Current gripper state
        """
        pass
    
    def calibrate(self, open_mm: float, close_mm: float) -> bool:
        """Calibrate the gripper for mm positioning.
        
        This method can be overridden by subclasses for hardware-specific
        calibration procedures.
        
        Args:
            open_mm: Distance between fingers when fully open (mm)
            close_mm: Distance between fingers when fully closed (mm)
            
        Returns:
            bool: True if calibration successful
        """
        self._state.open_mm = open_mm
        self._state.close_mm = close_mm
        self._state.is_calibrated = True
        return True
    
    def move_mm(self, position_mm: float, speed: int = 255, force: int = 255) -> Tuple[float, bool]:
        """Move gripper to position specified in mm.
        
        Args:
            position_mm: Target position in mm
            speed: Movement speed (0-255)
            force: Grip force (0-255)
            
        Returns:
            Tuple[float, bool]: (final_position_mm, object_detected)
            
        Raises:
            RuntimeError: If gripper is not calibrated
        """
        if not self._state.is_calibrated:
            raise RuntimeError("Gripper must be calibrated before using mm positioning")
        
        # Convert mm to bit position
        position = self._mm_to_bit(position_mm)
        final_pos, obj_detected = self.move(position, speed, force)
        return self._bit_to_mm(final_pos), obj_detected
    
    def _mm_to_bit(self, mm: float) -> int:
        """Convert mm position to bit position (0-255).
        
        Args:
            mm: Position in mm
            
        Returns:
            int: Position in bits (0-255)
        """
        if not self._state.is_calibrated:
            raise RuntimeError("Gripper must be calibrated")
        
        # Linear interpolation
        # When open (position=0), we're at open_mm
        # When closed (position=255), we're at close_mm
        open_mm = self._state.open_mm
        close_mm = self._state.close_mm
        
        # Calculate position
        if abs(open_mm - close_mm) < 0.001:
            return 0
        
        ratio = (mm - open_mm) / (close_mm - open_mm)
        position = int(ratio * 255)
        return max(0, min(255, position))
    
    def _bit_to_mm(self, bit: int) -> float:
        """Convert bit position (0-255) to mm.
        
        Args:
            bit: Position in bits (0-255)
            
        Returns:
            float: Position in mm
        """
        if not self._state.is_calibrated:
            raise RuntimeError("Gripper must be calibrated")
        
        open_mm = self._state.open_mm
        close_mm = self._state.close_mm
        
        # Linear interpolation
        ratio = bit / 255.0
        return open_mm + ratio * (close_mm - open_mm)
    
    def get_position_mm(self) -> Optional[float]:
        """Get current position in mm.
        
        Returns:
            float or None: Position in mm, or None if not calibrated
        """
        if not self._state.is_calibrated:
            return None
        return self._bit_to_mm(self._state.position)
    
    @property
    def is_activated(self) -> bool:
        """Check if gripper is activated."""
        return self._state.is_activated
    
    @property
    def is_moving(self) -> bool:
        """Check if gripper is currently moving."""
        return self._state.is_moving
    
    @property
    def object_detected(self) -> bool:
        """Check if an object is detected (grasped)."""
        return self._state.object_detected
    
    @property
    def is_calibrated(self) -> bool:
        """Check if gripper is calibrated for mm positioning."""
        return self._state.is_calibrated
    
    @property
    def fault_code(self) -> int:
        """Get current fault code (0 = no fault)."""
        return self._state.fault_code
    
    @property
    def position(self) -> int:
        """Get current position (0-255)."""
        return self._state.position
    
    @property
    def current(self) -> int:
        """Get current motor current (0-255)."""
        return self._state.current
