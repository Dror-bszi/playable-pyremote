# PlayAble - Rehabilitation Gaming System

## Project Overview
PlayAble is a hybrid gesture-to-game control system for physical rehabilitation.
It maps body movements (via MediaPipe pose detection + camera) to PlayStation
button presses, while simultaneously supporting a physical DualSense controller.
The goal is to help rehabilitation patients reconnect through gaming and movement.

## My Role
You are my developer and consultant on this project. I will describe what I want
to build or fix, and you will implement it, test it, and iterate.

## Target Hardware (Raspberry Pi 5)
- **Host:** 192.168.0.145 (or playable-c0e1.local via mDNS)
- **User:** drorb
- **SSH:** `ssh drorb@192.168.0.145`
- **Project path:** ~/playable
- **OS:** Raspberry Pi OS 64-bit (Bookworm)

## Development Workflow
1. All code lives on the RPi at ~/playable
2. SSH into the RPi to run commands, edit files, install packages, and test
3. Before starting any session, verify SSH connectivity and check repo state:
   `git status` and `git log --oneline -5`
4. Always activate the Python venv before running Python commands:
   `source ~/playable/venv/bin/activate`
5. After completing any meaningful work, commit and push to GitHub

## First Session Checklist
1. SSH into the RPi: `ssh drorb@192.168.0.145`
2. Clone if not present:
   `git clone https://github.com/Dror-bszi/playable-pyremote.git ~/playable`
3. Run the installer (handles everything):
   `cd ~/playable && ./install.sh`
4. Reboot: `sudo reboot`
5. Verify service came up: `sudo systemctl status playable`
6. Open dashboard: `http://playable-c0e1.local:5000`
7. Pair DualSense if not yet done — see Bluetooth Setup section below

## Repository
- **GitHub:** https://github.com/Dror-bszi/playable-pyremote
- **Branch:** main
- **Local on RPi:** ~/playable

## Tech Stack
- **Vision:** Python + MediaPipe + OpenCV (pose detection)
- **Controller input:** C++ + SDL2 (Hardware Producer, captures DualSense)
- **PS5 connection:** pyremoteplay (Remote Play protocol, in-process library)
- **Web dashboard:** Flask
- **Network:** NetworkManager (nmcli) — WiFi station + hotspot AP mode
- **IPC:** Named pipe at /tmp/my_pipe
- **Hardware:** Raspberry Pi 5, IMX708 CSI camera, DualSense controller (Bluetooth)

## Architecture
Five components:
1. Hardware Producer (C++) — reads DualSense input via SDL2, writes to pipe
2. Vision Sensor (Python) — detects gestures via camera, writes to pipe
3. Remote Play Client (pyremoteplay) — PipeReader reads pipe, forwards to PS5
4. Web Dashboard (Flask) — therapist UI for config and monitoring
5. WiFi Manager (Python) — hotspot fallback when no WiFi at startup

## Project Structure

```
playable/
├── controller/          # Hardware Producer (C++ SDL2)
│   ├── main.cpp
│   ├── CMakeLists.txt
│   └── build/
│       └── detect_controller   # compiled binary
├── core/               # Vision Sensor (Python)
│   ├── gestures.py     # MediaPipe gesture detection
│   ├── mappings.py     # Gesture mapping configuration
│   └── vision_sensor.py
├── network/            # WiFi / hotspot management
│   ├── __init__.py
│   └── wifi_manager.py # WiFiManager class + get_hostname()
├── pyremoteplay/       # Remote Play client library (in-repo fork)
│   └── pipe_reader.py  # Reads named pipe, forwards to Controller API
├── web/                # Web Dashboard (Flask)
│   ├── server.py       # All API endpoints + PSNConnectionManager
│   ├── templates/
│   │   ├── dashboard.html
│   │   └── setup.html  # WiFi setup page (captive portal + /setup)
│   └── static/
│       ├── css/style.css
│       └── js/dashboard.js
├── config/
│   ├── mappings.json
│   ├── psn_tokens.json     # PSN OAuth tokens (online_id, credentials)
│   └── ps5_config.json     # last_host IP for reconnect convenience
├── main.py
├── requirements.txt
└── install.sh
```

## Design Priorities
- Low latency is critical (target <150ms end-to-end)
- This is a rehabilitation tool — reliability matters more than cleverness
- The README may have inconsistencies — treat the code as source of truth
- When in doubt about a design decision, ask before implementing

## Hardware Producer Notes
- Binary lives at `controller/build/detect_controller`
- Build: `cd controller && mkdir -p build && cd build && cmake .. && make`
- Requires: `libsdl2-dev`, `cmake`, `build-essential`
- Does NOT require a display (SDL_INIT_VIDEO removed — headless safe)
- Pipe open is non-blocking (O_NONBLOCK): retries every 500ms until a reader connects
- Handles SIGTERM/SIGINT via signal handler — exits event loop cleanly
- Pipe message format: buttons = `BUTTON_NAME\npress|release\n\n`, analog = `STICK\naxis\nvalue\n`
- 200ms heartbeat: if SDL is silent 200ms, sends neutral axes → PS5 axis state cleared

## WiFi / Network

### Device identity (from RPi serial)
- Last 4 hex chars of `/proc/cpuinfo` Serial → device ID, e.g. `C0E1`
- Hostname: `playable-c0e1`  (mDNS: `playable-c0e1.local`)
- Hotspot SSID: `PlayAble-C0E1`  (open, no password)
- Hotspot IP: `192.168.4.1`
- `install.sh` sets the hostname on first run; avahi-daemon advertises it

### Startup network logic (main.py)
On startup, `check_and_configure_network()` runs before all other components:
1. Wait up to 20s for a WiFi station connection
2. If WiFi available → log SSID and continue
3. If no WiFi → `start_hotspot()` → PlayAble-XXXX AP comes up

### Hotspot mode components
| Component | What it does |
|---|---|
| `nmcli con add … mode ap ipv4.method shared` | Creates AP, NM handles DHCP |
| `/etc/NetworkManager/dnsmasq-shared.d/playable-captive.conf` | Redirects ALL DNS → 192.168.4.1 |
| nft table `playable-nat` | Redirects TCP :80 → :5000 (captive portal HTTP) |
| `/setup` route in Flask | WiFi setup page served to connecting devices |

### Captive portal flow
Phone connects → DNS returns 192.168.4.1 → HTTP probe hits port 80 → nft redirects
to 5000 → Flask returns 302 to `/setup` → phone shows "Sign in to network" popup.

### WiFi connection profile name
NetworkManager auto-names the WiFi profile `"preconfigured"` — NOT the SSID.
- ✓ `sudo nmcli con down preconfigured`
- ✗ `sudo nmcli con down "Dror&Yuval"`  ← won't work

### nftables (not iptables)
RPi OS Bookworm ships only `nft` (no iptables). `wifi_manager.py` uses
`nft -f -` with a `playable-nat` table. NM's own masquerading uses
`nm-shared-wlan0` table (set via `firewall-backend=nftables` in NM config).

### /setup page
- URL: `http://192.168.4.1:5000/setup` (hotspot mode) or `http://playable-c0e1.local:5000/setup`
- Lists visible networks (rescan button), password field, Connect button
- On success: shows QR code for `http://playable-c0e1.local:5000`
- "← Dashboard" back link shown only in WiFi mode (not hotspot)

## Auto-start (systemd)

PlayAble runs as a systemd service and starts automatically on every boot.

**Service file:** `/etc/systemd/system/playable.service` (not in git, written by install.sh)

```ini
[Unit]
Description=PlayAble Rehabilitation Gaming System
After=network.target bluetooth.target
Wants=network.target bluetooth.target

[Service]
Type=simple
User=drorb
WorkingDirectory=/home/drorb/playable
ExecStart=/home/drorb/playable/venv/bin/python3 /home/drorb/playable/main.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
```

**Useful commands:**
```bash
sudo systemctl status playable      # check status
sudo systemctl restart playable     # restart
sudo journalctl -u playable -f      # live logs
sudo journalctl -u playable -n 50   # last 50 lines
```

**Restart button behaviour:**
When running under systemd (`INVOCATION_ID` env var is set), the dashboard
"Restart System" button calls `sudo systemctl restart playable`.
When run directly (dev mode), it falls back to writing and executing `_restart.sh`.

## Bluetooth Setup (system config — written by install.sh)

### Required changes to /etc/bluetooth/input.conf
```
UserspaceHID=true
ClassicBondedOnly=false
```
Then: `sudo systemctl restart bluetooth`

**Why UserspaceHID=true**: Routes BT HID through UHID so `hid-playstation` binds
(alias `hid:b0005g*v0000054Cp00000CE6`) and `/dev/input/event*` nodes appear for SDL2.

**Why ClassicBondedOnly=false**: Allows HID connections during the DualSense
pairing process before the bond is fully established.

### DualSense pairing procedure
Must be done in ONE bluetoothctl session:

```bash
bluetoothctl remove BC:C7:46:7D:51:0D 2>/dev/null; true
# Put DualSense in pairing mode (PS + Create, rapid flash), then:
{ echo "agent NoInputNoOutput"; echo "default-agent"; sleep 1
  echo "scan on"; sleep 8; echo "scan off"
  echo "pair BC:C7:46:7D:51:0D"; sleep 10
  echo "trust BC:C7:46:7D:51:0D"; sleep 1
  echo "connect BC:C7:46:7D:51:0D"; sleep 8; echo "quit"
} | bluetoothctl
```

Verify: `bluetoothctl info BC:C7:46:7D:51:0D` → `Bonded: yes`, `Trusted: yes`, `Connected: yes`
Also: `ls /dev/input/event5` and `cat /proc/bus/input/devices | grep DualSense`

**DualSense MAC:** BC:C7:46:7D:51:0D

After a reboot: press PS button — auto-reconnects (no re-pairing needed).

### Anti-sniff system config (written by install.sh)

**Root cause:** BCM4345C0 chip (RPi5) enters L2CAP sniff mode (`sniff_max_interval=800`,
~500ms), dropping HID report rate to near-zero. SDL2 stops receiving events; PS5
latches the last non-zero stick value forever.

**Fix 1 — udev rule:** `/etc/udev/rules.d/99-dualsense-nosniff.rules`
```
ACTION=="add", SUBSYSTEM=="input", ATTRS{uniq}=="BC:C7:46:7D:51:0D", \
    RUN+="/bin/sh -c 'sleep 2 && /usr/bin/hcitool lp BC:C7:46:7D:51:0D rswitch'"
```
Fires on every DualSense reconnect. Verify: `hcitool lp BC:C7:46:7D:51:0D` → `RSWITCH`.
**Update `DUALSENSE_MAC` in `install.sh` if replacing the controller.**

**Fix 2 — WiFi power management off:** `/etc/NetworkManager/conf.d/99-wifi-powersave.conf`
```
[connection]
wifi.powersave = 2
```
Why: BCM4345C0 shares WiFi/BT antenna; WiFi PM causes BT stalls.

**Fix 3 — C++ 200ms heartbeat:** in `controller/main.cpp`.
Sends neutral axes if SDL silent 200ms → prevents PS5 latching stale non-zero axis.

## PSN Authentication
- Tokens stored in `config/psn_tokens.json` (online_id, credentials, expiration)
- Tokens expire — re-authenticate via the dashboard PSN Auth panel if needed
- The dashboard shows a re-auth link; follow it, copy the redirect URL back in

## Current Status
- **Last worked on:** 2026-04-16
- **Last completed:**
  - WiFi hotspot fallback: PlayAble-C0E1 AP with captive portal
    - network/wifi_manager.py: serial-based device ID, hotspot start/stop
    - NM shared mode (DHCP), dnsmasq DNS redirect, nft port 80→5000
    - /setup page: scan, select, connect, QR code on success
    - Dashboard Network panel: WiFi/Hotspot badge, SSID, link to /setup
    - Back button on /setup (visible in WiFi mode only)
  - systemd service: playable.service auto-starts on boot
    - Restart button now uses `systemctl restart` when INVOCATION_ID is set
  - Fixed captive portal: iptables → nft (RPi OS Bookworm has no iptables)
    - NM firewall-backend=nftables added to NetworkManager.conf
  - Hotspot fallback verified: WiFi down → 20s wait → PlayAble-C0E1 active
    - dnsmasq confirmed running with --conf-dir=dnsmasq-shared.d
    - playable-nat nft table confirmed with :80→:5000 redirect
  - install.sh comprehensive overhaul: all system config in one script
    - Added: dnsmasq, avahi-daemon, udev anti-sniff, WiFi powersave,
      NM firewall-backend, hostname from serial, captive portal config
    - Renumbered sections [0/10]…[10/10], verification pass at end

- **Next task:** Full gesture → PS5 test session; then add shoulder shrug gesture

- **Known issues:**
  - WiFi connection profile is named `preconfigured` by NM (not the SSID);
    `nmcli con down "Dror&Yuval"` fails — use `nmcli con down preconfigured`
  - pyremoteplay is started via the web dashboard UI, not by main.py —
    pipe writers loop waiting for a reader until pyremoteplay connects
  - Vision Sensor FPS is ~20-26 (target 30+) — MediaPipe pose detection is the
    bottleneck on RPi5; not yet optimized
  - Flask dev server thread does not stop cleanly within 5s on shutdown
    (logs a warning, exits eventually)
  - pyremoteplay logs ~10 "Version not accepted" protobuf errors during
    session negotiation — pre-existing, does not prevent READY state
  - udev sniff-disable rule 'sleep 2' delay may need tuning on slow BT reconnects

## Gesture Configuration
- **Current mappings:** right_elbow_raise → CIRCLE, left_elbow_raise → CROSS
- **Thresholds:** delta_threshold=0.03 (speed), raise_minimum=0.10 (height)
- **Debounce:** 3 press frames, 3 release frames
- **Config file:** config/mappings.json (live-reloaded every 3s by vision_sensor)
- **Restart:** Dashboard "Restart System" button → `systemctl restart playable`
  (when running as a service) or writes `_restart.sh` and runs it detached (direct)
