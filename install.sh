#!/bin/bash

# PlayAble Installation Script
# This script sets up the PlayAble rehabilitation gaming system on Raspberry Pi 4

set -e  # Exit on error

echo "=========================================="
echo "PlayAble Installation Script"
echo "=========================================="
echo ""

# Check if running on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo "Warning: This script is designed for Linux systems (Raspberry Pi OS)"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Update package lists
echo "Updating package lists..."
sudo apt-get update

# Install system dependencies
echo ""
echo "Installing system dependencies..."
echo "  - libsdl2-dev (for Hardware Producer)"
echo "  - python3-opencv (for Vision Sensor)"
echo "  - cmake (for building C++ components)"
echo "  - python3-venv (for virtual environment)"
echo "  - python3-pip (for Python package management)"
echo ""

sudo apt-get install -y \
    libsdl2-dev \
    python3-opencv \
    cmake \
    python3-venv \
    python3-pip \
    build-essential

# Create Python virtual environment
echo ""
echo "Creating Python virtual environment..."
if [ -d "venv" ]; then
    echo "Virtual environment already exists, skipping creation"
else
    python3 -m venv venv
    echo "Virtual environment created"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip

# Install Python dependencies
echo ""
echo "Installing Python dependencies from requirements.txt..."
pip install -r requirements.txt

# Compile Hardware Producer
echo ""
echo "Compiling Hardware Producer (C++ SDL2 component)..."
cd controller

if [ -d "build" ]; then
    echo "Build directory exists, cleaning..."
    rm -rf build
fi

mkdir build
cd build

echo "Running CMake..."
cmake ..

echo "Compiling with make..."
make

cd ../..

# Verify Hardware Producer binary
if [ -f "controller/build/detect_controller" ]; then
    echo "✓ Hardware Producer compiled successfully"
else
    echo "✗ Error: Hardware Producer binary not found"
    exit 1
fi

# Create Named Pipe
echo ""
echo "Creating Named Pipe for inter-process communication..."
PIPE_PATH="/tmp/my_pipe"

if [ -p "$PIPE_PATH" ]; then
    echo "Named Pipe already exists at $PIPE_PATH"
else
    mkfifo "$PIPE_PATH"
    chmod 666 "$PIPE_PATH"
    echo "✓ Named Pipe created at $PIPE_PATH"
fi

# Create config directory if it doesn't exist
echo ""
echo "Setting up configuration directory..."
if [ ! -d "config" ]; then
    mkdir config
    echo "✓ Config directory created"
else
    echo "Config directory already exists"
fi

# Verify config/mappings.json exists
if [ ! -f "config/mappings.json" ]; then
    echo "Warning: config/mappings.json not found"
    echo "The system will create default mappings on first run"
fi

echo ""
echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Pair your DualSense controller via Bluetooth"
echo "  2. Connect your USB or Pi Camera"
echo "  3. Ensure your PS5 is on the same network"
echo "  4. Run: source venv/bin/activate"
echo "  5. Run: python main.py"
echo "  6. Open web dashboard: http://localhost:5000"
echo ""
echo "For more information, see README.md"
echo ""
