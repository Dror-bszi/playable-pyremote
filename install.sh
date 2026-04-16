#!/bin/bash

# PlayAble Installation Script
# Sets up the PlayAble rehabilitation gaming system on Raspberry Pi 5

set -e  # Exit on error

echo "=========================================="
echo "  PlayAble Installation Script"
echo "  Target: Raspberry Pi 5"
echo "=========================================="
echo ""

# -----------------------------------------------
# 0. PLATFORM CHECK
# -----------------------------------------------
echo "[0/7] Platform check..."
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo "WARNING: This script is designed for Raspberry Pi OS (Linux)"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Resolve project root (script may be run from anywhere)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
echo "  Project root: $SCRIPT_DIR"

# -----------------------------------------------
# 1. SYSTEM PACKAGES
# -----------------------------------------------
echo ""
echo "[1/7] Installing system packages..."
echo "      libsdl2-dev       - Hardware Producer (DualSense via SDL2)"
echo "      cmake             - C++ build system"
echo "      build-essential   - C++ compiler toolchain"
echo "      python3-venv      - Python virtual environment support"
echo "      python3-pip       - Python package manager"
echo "      python3-opencv    - OpenCV system library"
echo "      python3-picamera2 - Pi Camera libcamera Python bindings"
echo "      bluez             - Bluetooth stack (DualSense pairing)"
echo ""

sudo apt-get update -qq
sudo apt-get install -y \
    libsdl2-dev \
    cmake \
    build-essential \
    python3-venv \
    python3-pip \
    python3-opencv \
    python3-picamera2 \
    bluez

echo "  System packages installed."

# dnsmasq is installed for its binary only — NM uses it internally for hotspot
# shared mode.  The system dnsmasq service must be disabled to avoid port 53 conflict.
if systemctl is-enabled --quiet dnsmasq 2>/dev/null; then
    echo "  Disabling dnsmasq system service (NM uses it internally)..."
    sudo systemctl disable dnsmasq
    sudo systemctl stop dnsmasq 2>/dev/null || true
else
    echo "  dnsmasq system service already disabled — OK."
fi

# -----------------------------------------------
# 2. PYTHON VIRTUAL ENVIRONMENT
# -----------------------------------------------
echo ""
echo "[2/7] Setting up Python virtual environment..."

VENV_DIR="venv"

# picamera2 is installed as a system package (python3-picamera2).
# The venv must be created with --system-site-packages so it can
# import picamera2 and its libcamera bindings.
if [ -d "$VENV_DIR" ]; then
    SYSTEM_SITE=$(grep "^include-system-site-packages" "$VENV_DIR/pyvenv.cfg" 2>/dev/null | cut -d= -f2 | tr -d ' ')
    if [ "$SYSTEM_SITE" = "false" ]; then
        echo "  Existing venv was created WITHOUT --system-site-packages."
        echo "  Removing and recreating so picamera2 is accessible inside venv..."
        rm -rf "$VENV_DIR"
    else
        echo "  Existing venv has --system-site-packages — OK."
    fi
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "  Creating venv with --system-site-packages..."
    python3 -m venv "$VENV_DIR" --system-site-packages
    echo "  Virtual environment created."
fi

echo "  Activating virtual environment..."
source "$VENV_DIR/bin/activate"

echo "  Upgrading pip..."
pip install --upgrade pip -q

echo "  Installing Python dependencies from requirements.txt..."
pip install -r requirements.txt -q

echo "  Python environment ready."

# -----------------------------------------------
# 3. BLUETOOTH CONFIGURATION
# -----------------------------------------------
echo ""
echo "[3/7] Configuring Bluetooth..."

BT_CONF="/etc/bluetooth/input.conf"

if [ ! -f "$BT_CONF" ]; then
    echo "  $BT_CONF not found — creating it..."
    sudo bash -c "echo '[Policy]' > $BT_CONF"
fi

# UserspaceHID=true
# Routes BT HID through UHID so hid-playstation binds and creates
# /dev/input/event* nodes that SDL2 can read.
if grep -q "^UserspaceHID=true" "$BT_CONF"; then
    echo "  UserspaceHID=true already set."
else
    echo "  Setting UserspaceHID=true..."
    if grep -q "^#*[[:space:]]*UserspaceHID" "$BT_CONF"; then
        sudo sed -i 's/^#*[[:space:]]*UserspaceHID.*/UserspaceHID=true/' "$BT_CONF"
    else
        sudo bash -c "echo 'UserspaceHID=true' >> $BT_CONF"
    fi
fi

# ClassicBondedOnly=false
# Allows HID connections from devices not yet fully bonded —
# required during the DualSense pairing process.
if grep -q "^ClassicBondedOnly=false" "$BT_CONF"; then
    echo "  ClassicBondedOnly=false already set."
else
    echo "  Setting ClassicBondedOnly=false..."
    if grep -q "^#*[[:space:]]*ClassicBondedOnly" "$BT_CONF"; then
        sudo sed -i 's/^#*[[:space:]]*ClassicBondedOnly.*/ClassicBondedOnly=false/' "$BT_CONF"
    else
        sudo bash -c "echo 'ClassicBondedOnly=false' >> $BT_CONF"
    fi
fi

echo "  Restarting Bluetooth service..."
sudo systemctl restart bluetooth
echo "  Bluetooth configured."

# -----------------------------------------------
# 4. HARDWARE PRODUCER (C++ SDL2)
# -----------------------------------------------
echo ""
echo "[4/7] Building Hardware Producer (C++ SDL2)..."

BINARY="controller/build/detect_controller"

if [ -f "$BINARY" ]; then
    echo "  Binary already exists: $BINARY"
    echo "  Skipping build. (Delete controller/build/ to force a rebuild.)"
else
    echo "  Compiling..."
    cd controller
    mkdir -p build
    cd build
    cmake .. -DCMAKE_BUILD_TYPE=Release
    make
    cd ../..

    if [ -f "$BINARY" ]; then
        echo "  Hardware Producer compiled successfully."
    else
        echo "  ERROR: Binary not found after build — check compiler output above."
        exit 1
    fi
fi

# -----------------------------------------------
# 5. NAMED PIPE
# -----------------------------------------------
echo ""
echo "[5/7] Setting up Named Pipe..."

PIPE_PATH="/tmp/my_pipe"

if [ -p "$PIPE_PATH" ]; then
    echo "  Named Pipe already exists: $PIPE_PATH — OK."
elif [ -e "$PIPE_PATH" ]; then
    echo "  $PIPE_PATH exists but is NOT a FIFO — removing and recreating..."
    rm "$PIPE_PATH"
    mkfifo "$PIPE_PATH"
    chmod 666 "$PIPE_PATH"
    echo "  Named Pipe recreated."
else
    mkfifo "$PIPE_PATH"
    chmod 666 "$PIPE_PATH"
    echo "  Named Pipe created: $PIPE_PATH"
fi

# Note: /tmp is cleared on reboot. Run install.sh again after reboot,
# or add pipe creation to a systemd service / /etc/rc.local.

# -----------------------------------------------
# 6. CONFIG DIRECTORY
# -----------------------------------------------
echo ""
echo "[6/7] Setting up config directory..."

mkdir -p config

if [ ! -f "config/mappings.json" ]; then
    echo "  WARNING: config/mappings.json not found."
    echo "           Default gesture mappings will be created on first run."
else
    echo "  config/mappings.json present."
fi

# -----------------------------------------------
# 7. STARTUP CHECKS
# -----------------------------------------------
echo ""
echo "[7/7] Running startup checks..."

CHECKS_PASSED=true

# Camera device
CAMERA_FOUND=false
for dev in /dev/video0 /dev/video1 /dev/video2 /dev/video3; do
    if [ -e "$dev" ]; then
        CAMERA_FOUND=true
        echo "  [OK]   Camera device found: $dev"
        break
    fi
done
if [ "$CAMERA_FOUND" = false ]; then
    echo "  [WARN] No camera device found at /dev/video0-3."
    echo "         Connect a Pi Camera Module or USB webcam before running."
    CHECKS_PASSED=false
fi

# picamera2 importable inside venv
source "$VENV_DIR/bin/activate"
if python3 -c "import picamera2" 2>/dev/null; then
    echo "  [OK]   picamera2 importable in venv."
else
    echo "  [FAIL] picamera2 NOT importable in venv."
    echo "         Ensure python3-picamera2 is installed and venv uses --system-site-packages."
    CHECKS_PASSED=false
fi

# Hardware Producer binary
if [ -f "$BINARY" ] && [ -x "$BINARY" ]; then
    echo "  [OK]   Hardware Producer binary: $BINARY"
else
    echo "  [FAIL] Hardware Producer binary missing or not executable: $BINARY"
    CHECKS_PASSED=false
fi

# Named pipe
if [ -p "$PIPE_PATH" ]; then
    echo "  [OK]   Named Pipe: $PIPE_PATH"
else
    echo "  [FAIL] Named Pipe missing: $PIPE_PATH"
    CHECKS_PASSED=false
fi

# Bluetooth service
if systemctl is-active --quiet bluetooth; then
    echo "  [OK]   Bluetooth service: running."
else
    echo "  [WARN] Bluetooth service not running."
    CHECKS_PASSED=false
fi

# Bluetooth input.conf settings
if grep -q "^UserspaceHID=true" "$BT_CONF" && grep -q "^ClassicBondedOnly=false" "$BT_CONF"; then
    echo "  [OK]   Bluetooth input.conf: UserspaceHID=true, ClassicBondedOnly=false."
else
    echo "  [FAIL] Bluetooth input.conf settings not applied correctly."
    CHECKS_PASSED=false
fi


# -----------------------------------------------
# 8. HOSTNAME FROM SERIAL (playable-XXXX)
# -----------------------------------------------
echo ''
echo "[8/8] Setting device hostname from serial number..."

SERIAL=$(grep '^Serial' /proc/cpuinfo | awk '{print $3}')
if [ -n "$SERIAL" ] && [ ${#SERIAL} -ge 4 ]; then
    DEVICE_ID=$(echo "$SERIAL" | tail -c 5 | tr 'a-z' 'A-Z')
    TARGET_HOSTNAME="playable-$(echo $DEVICE_ID | tr 'A-Z' 'a-z')"
    CURRENT_HOSTNAME=$(hostname)
    if [ "$CURRENT_HOSTNAME" = "$TARGET_HOSTNAME" ]; then
        echo "  Hostname already set to $TARGET_HOSTNAME — OK."
    else
        echo "  Setting hostname: $CURRENT_HOSTNAME → $TARGET_HOSTNAME"
        sudo hostnamectl set-hostname "$TARGET_HOSTNAME"
        sudo sed -i "s/127.0.1.1.*/127.0.1.1	$TARGET_HOSTNAME/" /etc/hosts
        sudo systemctl restart avahi-daemon
        echo "  Hostname set to $TARGET_HOSTNAME (mDNS: $TARGET_HOSTNAME.local)"
    fi

    # Create NM dnsmasq captive-portal config for hotspot mode
    NM_DNSMASQ_DIR="/etc/NetworkManager/dnsmasq-shared.d"
    NM_CAPTIVE_CONF="$NM_DNSMASQ_DIR/playable-captive.conf"
    sudo mkdir -p "$NM_DNSMASQ_DIR"
    echo "address=/#/192.168.4.1" | sudo tee "$NM_CAPTIVE_CONF" > /dev/null
    echo "  Captive portal DNS config: $NM_CAPTIVE_CONF"
else
    echo "  [WARN] Could not read RPi serial — skipping hostname config."
fi

# -----------------------------------------------
# SUMMARY
# -----------------------------------------------
echo ""
echo "=========================================="
if [ "$CHECKS_PASSED" = true ]; then
    echo "  Installation complete — all checks passed."
else
    echo "  Installation complete — some checks FAILED or WARNED."
    echo "  Review output above before running main.py."
fi
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. If DualSense is not yet paired:"
echo "       See 'Bluetooth Setup' in CLAUDE.md for pairing procedure"
echo "  2. Ensure the PS5 is on the same network as this RPi"
echo "  3. Activate venv:   source venv/bin/activate"
echo "  4. Start system:    python main.py"
echo "  5. Open dashboard:  http://$(hostname -I | awk '{print $1}'):5000"
echo ""
