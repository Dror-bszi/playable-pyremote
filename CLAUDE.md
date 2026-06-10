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
Six components, three of which write to the named pipe:
1. **Hardware Producer** (C++) — reads DualSense buttons/sticks via SDL2 → pipe
2. **Vision Sensor** (Python) — detects gestures via camera → pipe
3. **TouchpadReader** (Python, main.py:78–119) — reads /dev/input/event7 evdev
   directly (SDL2 doesn't see touchpad over BT) → pipe
4. **Remote Play Client** (pyremoteplay) — PipeReader reads pipe → forwards to PS5
5. **Web Dashboard** (Flask) — therapist UI for config, monitoring, BT scan,
   PSN auth, WiFi/hotspot, video feed
6. **WiFi Manager** (Python) — station detection at startup, hotspot AP fallback

Pipe atomicity: messages are <100 B, well under Linux PIPE_BUF (4096 B), so
concurrent writes from the three producers are atomic by kernel guarantee.
This is fragile if message format grows — not enforced in code.

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
- **Last worked on:** 2026-06-10
- **Last completed (since 2026-04-16):**
  - Gesture set expanded to 7 gestures (core/gestures.py):
    - left/right_elbow_raise, left/right_arm_forward (z-axis),
      left/right_shoulder_shrug, mouth_open (face mesh)
  - Switched vision pipeline from MediaPipe Pose → Holistic
    (pose + face in one pass; hands sub-model unused — see gap_analysis.md)
  - Added TouchpadReader (main.py:78–119): reads /dev/input/event7 directly,
    bypasses SDL2 (BT GameController API never fires touchpad). This adds
    a THIRD writer to /tmp/my_pipe — see Architecture note below.
  - Bluetooth: USB-triggered BT pairing flow + Grab Controller button
    (60s window, 20×3s retries, live attempt counter in UI)
  - Bluetooth: BT scan + paired-device list in dashboard
  - Dashboard: QR code modal for dashboard URL; mDNS hostname displayed
  - C++ producer: uint16 sequence-number overflow fix (control loss after ~65535 sends)
  - C++ producer: stdout pipe blocking fix (root cause of intermittent control loss)
  - log rotation: run.log → run.log.1 on every startup (main.py:91–95)
  - Fixed valid_gestures list in core/mappings.py to include the 3 new gestures
  - Wrote docs/gap_analysis.md — academic-grade PoC→final gap report

- **Next tasks (priority order):**
  1. Critical perf fixes from gap_analysis.md:
     - Fix broken FPS instrument (rolling window) — vision_sensor.py:240–263
     - Switch Holistic → Pose-only (hands model is dead weight) — gestures.py:42
     - Stop /video_feed re-running MediaPipe per request — gestures.py:165
     - Add One-Euro filter on landmarks before thresholding
  2. Add end-to-end latency instrumentation (per-event UUID, hop timestamps)
  3. Restore raise_minimum to 0.10 in config/mappings.json (currently 0.05 → FP-prone)
  4. Document & guard the 3-writer pipe protocol (PIPE_BUF size constraint)
  5. Add pytest suite (mappings, debounce, pipe parser)
  6. **Patient profiles (planned, not built):** per-subject calibration baseline
     (resting shoulder asymmetry, neutral elbow position, lip gap) saved to
     config/profiles/<subject_id>.json, subtracted from runtime measurements.
     Required for academic-grade reproducibility.
  7. Recorded-clip eval harness (5 subjects × 7 gestures, labeled, P/R metrics)

- **Architecture note: THREE pipe writers** (not two as docs once said):
  1. Hardware Producer (C++)
  2. Vision Sensor (Python)
  3. TouchpadReader (Python, main.py:78–119) — reads evdev directly
  All write multi-line messages <100 B (under PIPE_BUF = 4096 B) so writes
  are atomic by Linux pipe semantics. NOT enforced in code — fragile if
  message format grows.

- **Known issues:**
  - **Vision FPS ~10 (target 30+)** — three compounding causes documented in
    docs/gap_analysis.md §2.2: Holistic instead of Pose, /video_feed double
    inference, legacy MediaPipe API on CPU
  - **FPS instrument reports 0.0** — bug in vision_sensor.py:240–263 (divides
    total frames by total uptime; not a rolling window)
  - **No landmark smoothing** — raw MediaPipe coords drive thresholds, see
    gap_analysis.md §1.4
  - **No tests** — gap_analysis.md §1.7
  - WiFi connection profile is named `preconfigured` by NM (not the SSID);
    use `nmcli con down preconfigured`
  - pyremoteplay is started via the web dashboard UI, not by main.py —
    pipe writers loop waiting for a reader until pyremoteplay connects
  - Flask dev server thread does not stop cleanly within 5s on shutdown
  - pyremoteplay logs ~10 "Version not accepted" protobuf errors during
    session negotiation — pre-existing, does not prevent READY state
  - udev sniff-disable rule 'sleep 2' delay may need tuning on slow BT reconnects

## Gesture Configuration
- **All gestures (7):**
  - `left_elbow_raise`, `right_elbow_raise` — vertical elbow rise above shoulder
  - `left_arm_forward`, `right_arm_forward` — wrist z-axis toward camera
  - `left_shoulder_shrug`, `right_shoulder_shrug` — shoulder rise above baseline
  - `mouth_open` — lip gap from face mesh (no face-size normalization yet)
- **Live config:** `right_elbow_raise → CIRCLE` only; other mappings unassigned
- **Thresholds (config/mappings.json):**
  - `delta_threshold=0.03` (motion speed)
  - `raise_minimum=0.05` (height — NOTE: code default is 0.10; current value
    is half — FP-prone per gap_analysis.md §1.5)
  - `shrug_minimum=0.05`, `mouth_open_minimum=0.02`
- **Debounce:** 3 press frames, 3 release frames
- **Config file:** config/mappings.json (live-reloaded every 3s by vision_sensor)
- **Restart:** Dashboard "Restart System" button → `systemctl restart playable`
  (when running as a service) or writes `_restart.sh` and runs it detached (direct)

## Reference docs
- `docs/gap_analysis.md` — PoC vs final-project gap analysis with line-cited findings,
  20-item recommendation table, and 3-milestone roadmap. Read this before any
  meaningful refactor or performance work.
