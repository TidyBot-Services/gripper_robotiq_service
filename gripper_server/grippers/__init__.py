"""
Gripper implementations.

This module provides drivers for various gripper types.
"""

from gripper_server.grippers.base import BaseGripper, GripperState
from gripper_server.grippers.robotiq import RobotiqGripper

# Registry of available gripper types
GRIPPER_REGISTRY = {
    "robotiq": RobotiqGripper,
    "robotiq_2f85": RobotiqGripper,
    "robotiq_2f140": RobotiqGripper,
    "robotiq_hande": RobotiqGripper,
}


def get_gripper(gripper_type: str, **kwargs) -> BaseGripper:
    """Factory function to create a gripper instance.
    
    Args:
        gripper_type: Type of gripper (e.g., "robotiq", "robotiq_2f85")
        **kwargs: Additional arguments passed to gripper constructor
        
    Returns:
        BaseGripper: Gripper instance
        
    Raises:
        ValueError: If gripper type is not supported
    """
    gripper_type = gripper_type.lower()
    
    if gripper_type not in GRIPPER_REGISTRY:
        available = ", ".join(GRIPPER_REGISTRY.keys())
        raise ValueError(f"Unknown gripper type: {gripper_type}. Available: {available}")
    
    gripper_class = GRIPPER_REGISTRY[gripper_type]
    return gripper_class(**kwargs)


__all__ = [
    "BaseGripper",
    "GripperState",
    "RobotiqGripper",
    "GRIPPER_REGISTRY",
    "get_gripper",
]
