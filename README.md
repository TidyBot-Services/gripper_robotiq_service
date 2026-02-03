# Gripper Server

A modular gripper control framework for lab environments. Provides a server/client architecture for controlling various grippers through a unified interface.

## Architecture

```
Your Control Code <--ZMQ--> GripperServer <--Serial/USB--> Gripper Hardware
```

The server runs on the machine connected to the gripper hardware, while clients can connect from anywhere on the network.

## Supported Grippers

- **Robotiq 2F-85/2F-140/Hand-E**: Via Modbus RTU over USB/RS485

## Installation

### Server Setup (run on machine connected to gripper)

**Note:** You are responsible for creating and managing your own Python virtual environment.

```bash
# Create and activate a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install the package
pip install -e .

# Or use the setup script
./setup_server.sh

# For Robotiq grippers, ensure serial port permissions:
sudo chmod 666 /dev/ttyUSB0
```

### Client Setup (can run anywhere)

```bash
# Activate your virtual environment
source venv/bin/activate

# Option 1: Install minimal dependencies only
pip install pyzmq msgpack

# Option 2: Install the full package
pip install -e /path/to/gripper_server
```

## Usage

### Starting the Server

```bash
# Activate your virtual environment first
source venv/bin/activate

# Start server with Robotiq gripper (auto-detect port)
python -m gripper_server.server --gripper robotiq

# Or specify the serial port
python -m gripper_server.server --gripper robotiq --port /dev/ttyUSB0

# Custom network ports
python -m gripper_server.server --gripper robotiq --cmd-port 5570 --state-port 5571

# Or use the convenience script
./start_server.sh --gripper robotiq
```

### Using the Client

```python
from gripper_server import GripperClient

# Connect to server
client = GripperClient(server_ip="localhost")
client.connect()

# Basic operations
client.activate()           # Activate/initialize gripper
client.open()               # Open gripper fully
client.close()              # Close gripper fully
client.move(position=128)   # Move to position (0-255)

# Get state
state = client.get_state()
print(f"Position: {state.position}, Is grasped: {state.object_detected}")

# Disconnect
client.disconnect()
```

### Using with Context Manager

```python
from gripper_server import GripperClient

with GripperClient(server_ip="localhost") as client:
    client.activate()
    client.open()
    client.close(force=200)
```

## Adding New Gripper Types

1. Create a new class inheriting from `BaseGripper` in `gripper_server/grippers/`
2. Implement the required methods: `connect()`, `activate()`, `open()`, `close()`, `move()`, `read_state()`
3. Register the gripper type in `gripper_server/grippers/__init__.py`

Example:

```python
from gripper_server.grippers.base import BaseGripper, GripperState

class MyCustomGripper(BaseGripper):
    def __init__(self, **kwargs):
        super().__init__()
        # Initialize your gripper
    
    def connect(self) -> bool:
        # Connection logic
        return True
    
    def activate(self, reset_first: bool = True) -> bool:
        # Activation logic
        return True
    
    # ... implement other required methods
```

Then register it in `grippers/__init__.py`:

```python
from gripper_server.grippers.my_gripper import MyCustomGripper

GRIPPER_REGISTRY = {
    "robotiq": RobotiqGripper,
    "my_gripper": MyCustomGripper,  # Add your gripper
}
```

## Network Ports

| Port | Purpose |
|------|---------|
| 5570 | Command port (REQ/REP) |
| 5571 | State publishing port (PUB/SUB) |

## Dependencies

### Server
- pyzmq
- msgpack
- pyserial
- minimalmodbus

### Client (minimal)
- pyzmq
- msgpack

## License

Apache License 2.0
