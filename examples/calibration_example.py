#!/usr/bin/env python3
"""
Example: Gripper Calibration and MM Control

This example demonstrates how to calibrate the gripper for
millimeter-based positioning.

Start the gripper server first:
    ./start_server.sh --gripper robotiq

Then run this client:
    python examples/calibration_example.py --ip localhost
"""

import argparse
import time
from gripper_server import GripperClient


def main(server_ip: str, open_mm: float, close_mm: float):
    """Main example function."""
    
    print(f"Connecting to GripperServer at {server_ip}...")
    
    with GripperClient(server_ip=server_ip) as client:
        
        # Activate if needed
        if not client.is_activated:
            print("Activating gripper...")
            client.activate()
        
        # Print initial status
        print("\nInitial status:")
        client.print_status()
        
        # === Calibration ===
        print(f"\n[1] Calibrating gripper...")
        print(f"    Open distance: {open_mm} mm")
        print(f"    Close distance: {close_mm} mm")
        print("    This will perform a full open/close cycle.")
        
        input("    Press Enter to continue...")
        
        if not client.calibrate(open_mm=open_mm, close_mm=close_mm):
            print("    Calibration failed!")
            return
        
        print("    Calibration complete!")
        
        time.sleep(1.0)
        
        # === Move to specific mm positions ===
        positions_mm = [open_mm * 0.75, open_mm * 0.5, open_mm * 0.25, 10.0]
        
        print(f"\n[2] Moving to various mm positions...")
        
        for target_mm in positions_mm:
            print(f"\n    Moving to {target_mm:.1f} mm...")
            final_mm, obj_detected = client.move_mm(target_mm, speed=150, force=100)
            print(f"    Reached: {final_mm:.1f} mm, Object: {obj_detected}")
            time.sleep(0.5)
        
        # === Open fully ===
        print(f"\n[3] Opening fully...")
        client.open()
        
        time.sleep(0.5)
        
        # === Final status ===
        print("\nFinal status:")
        client.print_status()
        
    print("Done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Gripper Calibration Example"
    )
    parser.add_argument(
        "--ip",
        type=str,
        default="localhost",
        help="Gripper server IP address (default: localhost)"
    )
    parser.add_argument(
        "--open-mm",
        type=float,
        default=85.0,
        help="Distance when fully open in mm (default: 85.0 for 2F-85)"
    )
    parser.add_argument(
        "--close-mm",
        type=float,
        default=0.0,
        help="Distance when fully closed in mm (default: 0.0)"
    )
    
    args = parser.parse_args()
    main(args.ip, args.open_mm, args.close_mm)
