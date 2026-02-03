#!/usr/bin/env python3
"""
Example: Pick and Place Operation

This example demonstrates a simple pick and place operation
using the gripper client.

Start the gripper server first:
    ./start_server.sh --gripper robotiq

Then run this client:
    python examples/pick_and_place.py --ip localhost
"""

import argparse
import time
from gripper_server import GripperClient


def pick(client: GripperClient, grasp_width: int = 128, force: int = 200) -> bool:
    """Pick up an object.
    
    Args:
        client: Connected gripper client
        grasp_width: Expected grasp width (0-255)
        force: Grip force (0-255)
        
    Returns:
        bool: True if object was picked successfully
    """
    # Open gripper to prepare for pick
    print("  Opening gripper for pick...")
    client.open(speed=200)
    time.sleep(0.5)
    
    # Close to grasp object
    print(f"  Grasping with force {force}...")
    position, obj_detected = client.close(speed=100, force=force)
    
    if obj_detected:
        print(f"  Object picked! Position: {position}")
        return True
    else:
        print("  No object detected")
        return False


def place(client: GripperClient) -> None:
    """Place the object.
    
    Args:
        client: Connected gripper client
    """
    print("  Releasing object...")
    client.open(speed=150)
    time.sleep(0.3)
    print("  Object placed")


def main(server_ip: str, cycles: int):
    """Main example function."""
    
    print(f"Connecting to GripperServer at {server_ip}...")
    
    with GripperClient(server_ip=server_ip) as client:
        
        # Activate if needed
        if not client.is_activated:
            print("Activating gripper...")
            client.activate()
        
        print(f"\nPerforming {cycles} pick and place cycles")
        print("Place an object between the gripper fingers when prompted.\n")
        
        success_count = 0
        
        for i in range(cycles):
            print(f"=== Cycle {i + 1}/{cycles} ===")
            
            input("Press Enter to pick...")
            
            if pick(client, force=180):
                success_count += 1
                
                print("  Holding object for 2 seconds...")
                time.sleep(2.0)
                
                input("Press Enter to place...")
                place(client)
            else:
                print("  Skipping place (no object)")
            
            print()
        
        # Summary
        print(f"=== Summary ===")
        print(f"Successful picks: {success_count}/{cycles}")
        
        # Final open
        client.open()
        
    print("Done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pick and Place Example"
    )
    parser.add_argument(
        "--ip",
        type=str,
        default="localhost",
        help="Gripper server IP address (default: localhost)"
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=3,
        help="Number of pick and place cycles (default: 3)"
    )
    
    args = parser.parse_args()
    main(args.ip, args.cycles)
