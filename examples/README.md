# Gripper Server Examples

This directory contains example scripts demonstrating how to use the GripperClient.

## Prerequisites

1. Start the gripper server on the machine connected to the gripper:

```bash
# On the gripper machine
cd /path/to/gripper_server
./setup_server.sh      # First time only
./start_server.sh --gripper robotiq
```

2. Install client dependencies on your control machine:

```bash
pip install pyzmq msgpack
# Or install the full package:
pip install -e /path/to/gripper_server
```

## Examples

### Basic Control (`basic_control.py`)

Demonstrates basic gripper operations:
- Activation
- Open/Close
- Move to position
- Grasp/Release

```bash
python basic_control.py --ip SERVER_IP
```

### Calibration (`calibration_example.py`)

Demonstrates gripper calibration for millimeter-based positioning:
- Calibration procedure
- Moving to mm positions

```bash
# For Robotiq 2F-85 (85mm opening)
python calibration_example.py --ip SERVER_IP --open-mm 85.0 --close-mm 0.0

# For Robotiq 2F-140 (140mm opening)
python calibration_example.py --ip SERVER_IP --open-mm 140.0 --close-mm 0.0
```

### Pick and Place (`pick_and_place.py`)

Demonstrates a simple pick and place operation:
- Multiple cycles
- Object detection

```bash
python pick_and_place.py --ip SERVER_IP --cycles 5
```

## Command Line Options

All examples support:
- `--ip`: Gripper server IP address (default: localhost)

## Using in Your Code

```python
from gripper_server import GripperClient

# Option 1: Manual connection
client = GripperClient(server_ip="192.168.1.100")
client.connect()

client.activate()
client.open()
position, obj_detected = client.close(force=200)
if obj_detected:
    print("Object grasped!")

client.disconnect()

# Option 2: Context manager (recommended)
with GripperClient(server_ip="192.168.1.100") as client:
    client.activate()
    client.grasp(force=200)
    # ... do something with the object
    client.release()
```
