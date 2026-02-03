#!/usr/bin/env python3
"""
Gripper Server - A modular gripper control framework.

This package provides a server/client architecture for controlling
various grippers in a lab environment. Supports multiple gripper types
through a common interface.
"""
from setuptools import setup, find_packages

setup(
    name="gripper_server",
    version="0.1.0",
    description="Modular gripper control server for lab environments",
    author="Lab Robotics Team",
    packages=find_packages(),
    install_requires=[
        "pyzmq>=22.0.0",
        "msgpack>=1.0.0",
        "pyserial>=3.5",
        "minimalmodbus>=2.0.0",
    ],
    extras_require={
        "dev": [
            "pytest",
            "black",
            "flake8",
        ],
    },
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "gripper-server=gripper_server.server:main",
        ],
    },
)
