#!/bin/bash
# PlayAble Installation Script
# Sets up the PlayAble rehabilitation gaming system on a fresh Raspberry Pi 5
# running Raspberry Pi OS 64-bit (Bookworm).
#
# Run as the project user from the repo root:
#   ./install.sh
#
# After completion, reboot.  PlayAble auto-starts via systemd on every boot.

set -e

echo "=========================================="
echo "  PlayAble Installation Script"
echo "  Target: Raspberry Pi 5 / RPi OS Bookworm"
echo "=========================================="
echo ""

# ── Configurable constants ────────────────────────────────────────────────────
# DualSense Bluetooth MAC address — update when replacing the controller.
DUALSENSE_MAC="BC:C7:46:7D:51:0D"

# ── Fixed paths ───────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
BINARY="$SCRIPT_DIR/controller/build/detect_controller"
PIPE_PATH="/tmp/my_pipe"
BT_CONF="/etc/bluetooth/input.conf"
UDEV_RULE="/etc/udev/rules.d/99-dualsense-nosniff.rules"
USB_UDEV_RULE="/etc/udev/rules.d/99-dualsense-usb.rules"
BT_PAIR_SCRIPT="/usr/local/bin/playable-bt-pair.sh"
NM_PM_CONF="/etc/NetworkManager/conf.d/99-wifi-powersave.conf"
NM_MAIN_CONF="/etc/NetworkManager/NetworkManager.conf"
NM_DNSMASQ_DIR="/etc/NetworkManager/dnsmasq-shared.d"
NM_CAPTIVE_CONF="$NM_DNSMASQ_DIR/playable-captive.conf"
SERVICE_FILE="/etc/systemd/system/playable.service"

cd "$SCRIPT_DIR"

# ── 0. Platform check ─────────────────────────────────────────────────────────
echo "[0/10] Platform check..."
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo "WARNING: This script targets Raspberry Pi OS (Linux)."
    read -p "Continue anyway? (y/n) " -n 1 -r; echo
    [[ ! $REPLY =~ ^[Yy]$ ]] && exit 1
fi
echo "  Project root: $SCRIPT_DIR"

# ── 1. System packages ────────────────────────────────────────────────────────
echo ""
echo "[1/10] Installing system packages..."

sudo apt-get update -qq
sudo apt-get install -y \
    libsdl2-dev \
    cmake \
    build-essential \
    python3-venv \
    python3-pip \
    python3-opencv \
    python3-picamera2 \
    bluez \
    dnsmasq \
    avahi-daemon \
    network-manager

# dnsmasq binary is used internally by NetworkManager for hotspot DHCP/DNS.
# The standalone system service must be disabled to avoid a port-53 conflict.
echo "  Disabling dnsmasq system service (NM uses the binary directly)..."
sudo systemctl disable dnsmasq 2>/dev/null || true
sudo systemctl stop dnsmasq 2>/dev/null || true

echo "  System packages installed."

# ── 2. Python virtual environment ─────────────────────────────────────────────
echo ""
echo "[2/10] Setting up Python virtual environment..."

# picamera2 is installed as a system package (python3-picamera2).
# The venv must use --system-site-packages so it can import picamera2
# and its libcamera bindings.
if [ -d "$VENV_DIR" ]; then
    SYSTEM_SITE=$(grep "^include-system-site-packages" "$VENV_DIR/pyvenv.cfg" 2>/dev/null \
                  | cut -d= -f2 | tr -d ' ')
    if [ "$SYSTEM_SITE" = "false" ]; then
        echo "  Existing venv is missing --system-site-packages — recreating..."
        rm -rf "$VENV_DIR"
    else
        echo "  Existing venv OK."
    fi
fi

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR" --system-site-packages
    echo "  venv created."
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  Python dependencies installed."

# ── 3. Bluetooth config ───────────────────────────────────────────────────────
echo ""
echo "[3/10] Configuring Bluetooth (input.conf)..."

[ ! -f "$BT_CONF" ] && sudo bash -c "printf '[Policy]\n' > $BT_CONF"

_set_bt() {
    local KEY="$1" VAL="$2"
    if grep -q "^${KEY}=${VAL}" "$BT_CONF"; then
        echo "  ${KEY}=${VAL} already set."
    elif grep -q "^#*[[:space:]]*${KEY}" "$BT_CONF"; then
        sudo sed -i "s|^#*[[:space:]]*${KEY}.*|${KEY}=${VAL}|" "$BT_CONF"
        echo "  Set ${KEY}=${VAL}."
    else
        echo "${KEY}=${VAL}" | sudo tee -a "$BT_CONF" > /dev/null
        echo "  Added ${KEY}=${VAL}."
    fi
}

# UserspaceHID=true  — routes BT HID through UHID so hid-playstation binds
#                      and SDL2 sees /dev/input/event* nodes over Bluetooth.
# ClassicBondedOnly=false — allows HID connections during the DualSense
#                           pairing process before the bond is established.
_set_bt UserspaceHID true
_set_bt ClassicBondedOnly false

sudo systemctl restart bluetooth
echo "  Bluetooth configured."

# ── 4. Anti-sniff + WiFi powersave + NM firewall backend ─────────────────────
echo ""
echo "[4/10] Configuring network for low-latency Bluetooth..."

# 4a. udev rule: disable BT sniff mode for DualSense on every reconnect.
#
#     Root cause: BCM4345C0 (RPi5 BT chip) enters L2CAP sniff mode with
#     sniff_max_interval=800 (~500ms), dropping HID report rate to near-zero.
#     SDL2 stops receiving events; PS5 latches the last non-zero stick value.
#     'hcitool lp rswitch' removes SNIFF from the link policy, restoring
#     full HID report rate.  The rule fires on every DualSense INPUT add event
#     (i.e., every reconnect after pairing).
#
#     If you replace the DualSense controller, update DUALSENSE_MAC at the
#     top of this script and re-run install.sh.
if [ -f "$UDEV_RULE" ] && grep -q "$DUALSENSE_MAC" "$UDEV_RULE"; then
    echo "  udev anti-sniff rule already present."
else
    sudo tee "$UDEV_RULE" > /dev/null << UDEVEOF
# Disable BT sniff mode for DualSense when it connects (prevents HID report rate drop)
ACTION=="add", SUBSYSTEM=="input", ATTRS{uniq}=="$DUALSENSE_MAC", \
    RUN+="/bin/sh -c 'sleep 2 && /usr/bin/hcitool lp $DUALSENSE_MAC rswitch'"
UDEVEOF
    sudo udevadm control --reload-rules
    echo "  udev anti-sniff rule installed: $UDEV_RULE"
fi

# 4a-2. USB-triggered BT pairing script and udev rules.
#
#     When DualSense is plugged into USB:
#       - udev fires: systemd-run launches playable-bt-pair.sh pair
#       - Script waits 3s, then pairs + trusts + connects via BT
#       - Result logged to /tmp/playable-bt-pair.log
#
#     When DualSense is unplugged from USB:
#       - udev fires: systemd-run launches playable-bt-pair.sh connect
#       - Script reconnects via BT immediately
#
#     systemd-run --no-block is used so the script runs outside the udev
#     event timeout (bluetoothctl needs several seconds per command).
#
#     If you replace the DualSense controller, update DUALSENSE_MAC at the
#     top of this script and re-run install.sh.

# Write the pairing script (with the configured MAC substituted in)
sudo tee "$BT_PAIR_SCRIPT" > /dev/null << BPEOF
#!/bin/bash
# PlayAble — DualSense USB-triggered BT pairing helper
# Invoked by udev on DualSense USB connect/disconnect.
# Usage:
#   playable-bt-pair.sh pair     — USB plugged in: pair + trust + connect
#   playable-bt-pair.sh connect  — USB unplugged: connect only

MAC="$DUALSENSE_MAC"
LOG="/tmp/playable-bt-pair.log"
ACTION="\${1:-pair}"

{
    echo "=== \$(date) — \$ACTION trigger ==="

    if [ "\$ACTION" = "pair" ]; then
        echo "Waiting 3s for USB HID to settle..."
        sleep 3
        echo "--- bluetoothctl pair ---"
        /usr/bin/bluetoothctl pair "\$MAC" 2>&1
        sleep 1
        echo "--- bluetoothctl trust ---"
        /usr/bin/bluetoothctl trust "\$MAC" 2>&1
        sleep 1
    else
        sleep 2
    fi

    echo "--- bluetoothctl connect ---"
    /usr/bin/bluetoothctl connect "\$MAC" 2>&1
    echo "=== done ==="
} >> "\$LOG" 2>&1
BPEOF
sudo chmod +x "$BT_PAIR_SCRIPT"
echo "  BT pairing script installed: $BT_PAIR_SCRIPT"

# Install USB udev rules
sudo tee "$USB_UDEV_RULE" > /dev/null << UDEVUSB
# PlayAble — DualSense USB connect/disconnect BT pairing triggers
# Sony DualSense: idVendor=054c, idProduct=0ce6
ACTION=="add",    SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", \
    ATTR{idVendor}=="054c", ATTR{idProduct}=="0ce6", \
    RUN+="/bin/systemd-run --no-block $BT_PAIR_SCRIPT pair"
ACTION=="remove", SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", \
    ATTR{idVendor}=="054c", ATTR{idProduct}=="0ce6", \
    RUN+="/bin/systemd-run --no-block $BT_PAIR_SCRIPT connect"
UDEVUSB
sudo udevadm control --reload-rules
echo "  USB udev rules installed: $USB_UDEV_RULE"

# 4b. Disable WiFi power management.
#     BCM4345C0 shares the WiFi/BT antenna. WiFi power-save mode causes
#     periodic BT stalls that manifest as input lag on the PS5.
if [ -f "$NM_PM_CONF" ]; then
    echo "  WiFi powersave config already present."
else
    sudo mkdir -p /etc/NetworkManager/conf.d
    printf '[connection]\nwifi.powersave = 2\n' | sudo tee "$NM_PM_CONF" > /dev/null
    echo "  WiFi powersave disabled: $NM_PM_CONF"
fi
sudo iw dev wlan0 set power_save off 2>/dev/null || true

# 4c. Set NM firewall backend to nftables.
#     RPi OS Bookworm does not include iptables; only nft is available.
#     NM needs this for hotspot masquerading (shared mode).
if grep -q "^firewall-backend=nftables" "$NM_MAIN_CONF"; then
    echo "  NM firewall-backend=nftables already set."
else
    if grep -q "^\[main\]" "$NM_MAIN_CONF"; then
        sudo sed -i '/^\[main\]/a firewall-backend=nftables' "$NM_MAIN_CONF"
    else
        printf '\n[main]\nfirewall-backend=nftables\n' | sudo tee -a "$NM_MAIN_CONF" > /dev/null
    fi
    echo "  NM firewall-backend=nftables added."
fi

sudo systemctl reload-or-restart NetworkManager 2>/dev/null || true
echo "  Network config done."

# ── 5. Hardware Producer (C++ SDL2) ───────────────────────────────────────────
echo ""
echo "[5/10] Building Hardware Producer (C++ SDL2)..."

if [ -f "$BINARY" ]; then
    echo "  Binary exists: $BINARY"
    echo "  Skipping build. (Delete controller/build/ to force rebuild.)"
else
    echo "  Compiling..."
    cd "$SCRIPT_DIR/controller"
    mkdir -p build && cd build
    cmake .. -DCMAKE_BUILD_TYPE=Release -DCMAKE_VERBOSE_MAKEFILE=OFF
    make
    cd "$SCRIPT_DIR"
    if [ -f "$BINARY" ]; then
        echo "  Hardware Producer compiled successfully."
    else
        echo "  ERROR: Binary not found after build — check output above."
        exit 1
    fi
fi

# ── 6. Named pipe ─────────────────────────────────────────────────────────────
echo ""
echo "[6/10] Setting up named pipe..."

# Note: main.py also creates the pipe on startup, so it survives /tmp clears.
if [ -p "$PIPE_PATH" ]; then
    echo "  $PIPE_PATH already exists."
elif [ -e "$PIPE_PATH" ]; then
    rm "$PIPE_PATH"
    mkfifo "$PIPE_PATH" && chmod 666 "$PIPE_PATH"
    echo "  Recreated $PIPE_PATH (was not a FIFO)."
else
    mkfifo "$PIPE_PATH" && chmod 666 "$PIPE_PATH"
    echo "  Created $PIPE_PATH."
fi

# ── 7. Config directory ───────────────────────────────────────────────────────
echo ""
echo "[7/10] Checking config directory..."

mkdir -p "$SCRIPT_DIR/config"
if [ -f "$SCRIPT_DIR/config/mappings.json" ]; then
    echo "  config/mappings.json present."
else
    echo "  [WARN] config/mappings.json missing — defaults created on first run."
fi

# ── 8. Hostname + captive portal DNS config ───────────────────────────────────
echo ""
echo "[8/10] Setting device hostname from serial number..."

SERIAL=$(grep '^Serial' /proc/cpuinfo 2>/dev/null | awk '{print $3}')
if [ -n "$SERIAL" ] && [ "${#SERIAL}" -ge 4 ]; then
    DEVICE_ID=$(printf '%s' "$SERIAL" | tail -c 4 | tr 'a-z' 'A-Z')
    TARGET_HOSTNAME="playable-$(printf '%s' "$DEVICE_ID" | tr 'A-Z' 'a-z')"
    CURRENT_HOSTNAME=$(hostname)

    if [ "$CURRENT_HOSTNAME" = "$TARGET_HOSTNAME" ]; then
        echo "  Hostname already $TARGET_HOSTNAME — OK."
    else
        echo "  Setting hostname: $CURRENT_HOSTNAME → $TARGET_HOSTNAME"
        sudo hostnamectl set-hostname "$TARGET_HOSTNAME"
        if grep -q "127.0.1.1" /etc/hosts; then
            sudo sed -i "s/^127\.0\.1\.1.*/127.0.1.1\t$TARGET_HOSTNAME/" /etc/hosts
        else
            printf '127.0.1.1\t%s\n' "$TARGET_HOSTNAME" | sudo tee -a /etc/hosts > /dev/null
        fi
        sudo systemctl restart avahi-daemon
        echo "  Hostname: $TARGET_HOSTNAME  (mDNS: $TARGET_HOSTNAME.local)"
    fi

    # NM dnsmasq drop-in: redirect all DNS queries to the hotspot IP when
    # the hotspot is active. NM reads this directory when starting shared mode.
    sudo mkdir -p "$NM_DNSMASQ_DIR"
    echo "address=/#/192.168.4.1" | sudo tee "$NM_CAPTIVE_CONF" > /dev/null
    echo "  Captive portal DNS config: $NM_CAPTIVE_CONF"
else
    echo "  [WARN] Could not read RPi serial — skipping hostname config."
fi

# ── 9. systemd service ────────────────────────────────────────────────────────
echo ""
echo "[9/10] Installing playable.service..."

VENV_PYTHON="$VENV_DIR/bin/python3"

sudo tee "$SERVICE_FILE" > /dev/null << SVCEOF
[Unit]
Description=PlayAble Rehabilitation Gaming System
After=network.target bluetooth.target
Wants=network.target bluetooth.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$SCRIPT_DIR
ExecStart=$VENV_PYTHON $SCRIPT_DIR/main.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVCEOF

sudo systemctl daemon-reload
sudo systemctl enable playable
echo "  playable.service enabled (auto-starts on boot)."

if systemctl is-active --quiet playable; then
    echo "  Service already running — restart manually if needed:"
    echo "    sudo systemctl restart playable"
else
    sudo systemctl start playable
    sleep 5
    if systemctl is-active --quiet playable; then
        echo "  [OK] playable.service started."
    else
        echo "  [FAIL] playable.service failed — check: journalctl -u playable -n 30"
    fi
fi

# ── 10. Verification ──────────────────────────────────────────────────────────
echo ""
echo "[10/10] Verification..."

CHECKS_PASSED=true
_chk() {
    if [ "$2" = "true" ]; then printf '  [OK]   %s\n' "$1"
    else printf '  [FAIL] %s  —  %s\n' "$1" "$3"; CHECKS_PASSED=false; fi
}

# Camera
CAMERA_FOUND=false
for dev in /dev/video0 /dev/video1 /dev/video2 /dev/video3; do
    [ -e "$dev" ] && CAMERA_FOUND=true && break
done
_chk "Camera device" "$CAMERA_FOUND" "connect Pi Camera or USB webcam"

# picamera2 importable
source "$VENV_DIR/bin/activate"
python3 -c "import picamera2" 2>/dev/null \
    && _chk "picamera2 importable" true "" \
    || _chk "picamera2 importable" false "ensure python3-picamera2 installed, venv needs --system-site-packages"

# Hardware Producer binary
[ -f "$BINARY" ] && [ -x "$BINARY" ] \
    && _chk "Hardware Producer binary" true "" \
    || _chk "Hardware Producer binary" false "build failed — check compiler output"

# Named pipe
[ -p "$PIPE_PATH" ] \
    && _chk "Named pipe ($PIPE_PATH)" true "" \
    || _chk "Named pipe ($PIPE_PATH)" false "run: mkfifo $PIPE_PATH && chmod 666 $PIPE_PATH"

# Bluetooth service
systemctl is-active --quiet bluetooth \
    && _chk "Bluetooth service" true "" \
    || _chk "Bluetooth service" false "sudo systemctl start bluetooth"

# BT input.conf
grep -q "^UserspaceHID=true" "$BT_CONF" && grep -q "^ClassicBondedOnly=false" "$BT_CONF" \
    && _chk "Bluetooth input.conf" true "" \
    || _chk "Bluetooth input.conf" false "check $BT_CONF"

# udev anti-sniff
[ -f "$UDEV_RULE" ] \
    && _chk "udev anti-sniff rule" true "" \
    || _chk "udev anti-sniff rule" false "$UDEV_RULE missing"

# USB udev rules + BT pairing script
[ -f "$USB_UDEV_RULE" ] && [ -x "$BT_PAIR_SCRIPT" ] \
    && _chk "USB udev rules + BT pairing script" true "" \
    || _chk "USB udev rules + BT pairing script" false "$USB_UDEV_RULE or $BT_PAIR_SCRIPT missing"

# WiFi powersave config
[ -f "$NM_PM_CONF" ] \
    && _chk "WiFi powersave config" true "" \
    || _chk "WiFi powersave config" false "$NM_PM_CONF missing"

# NM firewall backend
grep -q "^firewall-backend=nftables" "$NM_MAIN_CONF" \
    && _chk "NM firewall-backend=nftables" true "" \
    || _chk "NM firewall-backend=nftables" false "check $NM_MAIN_CONF"

# Captive portal DNS config
[ -f "$NM_CAPTIVE_CONF" ] \
    && _chk "Captive portal DNS config" true "" \
    || _chk "Captive portal DNS config" false "$NM_CAPTIVE_CONF missing"

# playable.service running
systemctl is-active --quiet playable \
    && _chk "playable.service running" true "" \
    || _chk "playable.service running" false "journalctl -u playable -n 30"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "=========================================="
if [ "$CHECKS_PASSED" = true ]; then
    echo "  Installation complete — all checks passed."
else
    echo "  Installation complete — some checks failed."
    echo "  Review output above before rebooting."
fi
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Reboot:  sudo reboot"
echo "     (PlayAble starts automatically via systemd on boot)"
echo ""
echo "  2. If DualSense not yet paired:"
echo "     See 'Bluetooth Setup' in CLAUDE.md for the pairing procedure."
echo "     Anti-sniff MAC configured: $DUALSENSE_MAC"
echo ""
echo "  3. Dashboard:  http://$(hostname).local:5000"
echo "     (or http://$(hostname -I | awk '{print $1}' 2>/dev/null):5000)"
echo ""
