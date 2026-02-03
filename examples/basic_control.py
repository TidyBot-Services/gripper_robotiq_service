#!/usr/bin/env python3
"""
Example: Basic Gripper Control Client

This example demonstrates how to use the GripperClient to control
a gripper through the GripperServer.

Start the gripper server first:
    ./start_server.sh --gripper robotiq

Then run this client:
    python examples/basic_control.py --ip localhost
"""

import argparse
import time
from gripper_server import GripperClient


def main(server_ip: str):
    """Main example function."""
    
    print(f"Connecting to GripperServer at {server_ip}...")
    
    # Create client and connect
    client = GripperClient(server_ip=server_ip, timeout=30.0)
    
    try:
        client.connect()
    except Exception as e:
        print(f"Failed to connect: {e}")
        print("Make sure the gripper server is running.")
        return
    
    # Print initial status
    client.print_status()
    
    # === Activation ===
    print("\n[1] Activating gripper...")
    print("    WARNING: Gripper will fully open and close during activation!")
    
    input("    Press Enter to continue...")
    
    if not client.activate():
        print("    Activation failed!")
        client.disconnect()
        return
    
    time.sleep(1.0)
    
    # === Open Gripper ===
    print("\n[2] Opening gripper...")
    position, obj_detected = client.open(speed=200)
    print(f"    Position: {position}, Object detected: {obj_detected}")
    
    time.sleep(1.0)
    
    # === Close Gripper ===
    print("\n[3] Closing gripper...")
    position, obj_detected = client.close(speed=200, force=150)
    print(f"    Position: {position}, Object detected: {obj_detected}")
    
    time.sleep(1.0)
    
    # === Move to specific position ===
    print("\n[4] Moving to position 128 (half-closed)...")
    position, obj_detected = client.move(position=128, speed=200, force=100)
    print(f"    Position: {position}, Object detected: {obj_detected}")
    
    time.sleep(1.0)
    
    # === Grasp demonstration ===
    print("\n[5] Grasp demonstration...")
    print("    Place an object between the gripper fingers.")
    input("    Press Enter when ready...")
    
    print("    Attempting to grasp...")
    grasped = client.grasp(speed=100, force=200)
    
    if grasped:
        print("    Object grasped successfully!")
        client.print_status()
        
        print("\n    Releasing in 3 seconds...")
        time.sleep(3.0)
        
        client.release()
        print("    Object released.")
    else:
        print("    No object detected.")
    
    # === Final status ===
    print("\n[6] Final status:")
    client.print_status()
    
    # Disconnect
    client.disconnect()
    print("Done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Basic Gripper Control Example"
    )
    parser.add_argument(
        "--ip",
        type=str,
        default="localhost",
        help="Gripper server IP address (default: localhost)"
    )
    
    args = parser.parse_args()
    main(args.ip)
