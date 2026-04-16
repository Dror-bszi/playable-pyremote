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
- **Host:** 192.168.0.145
- **User:** drorb
- **SSH:** Use `ssh drorb@192.168.0.145` for all commands on the RPi
- **Project path:** ~/playable
- **OS:** Raspberry Pi OS 64-bit

## Development Workflow
1. All code lives on the RPi at ~/playable
2. SSH into the RPi to run commands, edit files, install packages, and test
3. Before starting any session, verify SSH connectivity and check repo state:
   `git status` and `git log --oneline -5`
4. Always activate the Python venv before running Python commands:
   `source ~/playable/venv/bin/activate`
5. After completing any meaningful work, commit and push to GitHub

## First Session Checklist
On first connection, do the following in order:
1. SSH into the RPi and verify connectivity
2. Check if ~/playable exists and if the repo is already cloned
3. If not cloned:
   `git clone https://github.com/Dror-bszi/playable-pyremote.git ~/playable`
4. Check if venv exists (`~/playable/venv/`), if not, create it:
   `python3 -m venv ~/playable/venv`
5. Activate venv and run:
   `pip install -r requirements.txt`
6. Report current state of the project — what exists, what is missing, any obvious issues
7. Check if camera is detected:
   `ls /dev/video*`
8. Check if the named pipe exists:
   `ls -l /tmp/my_pipe`
   If not: `mkfifo /tmp/my_pipe && chmod 666 /tmp/my_pipe`
9. Apply Bluetooth system config if not already done (see Bluetooth Setup section)

## Repository
- **GitHub:** https://github.com/Dror-bszi/playable-pyremote
- **Branch:** main
- **Local on RPi:** ~/playable

## Tech Stack
- **Vision:** Python + MediaPipe + OpenCV (pose detection)
- **Controller input:** C++ + SDL2 (Hardware Producer, captures DualSense)
- **PS5 connection:** pyremoteplay (Remote Play protocol, in-process library)
- **Web dashboard:** Flask
- **IPC:** Named pipe at /tmp/my_pipe
- **Hardware:** Raspberry Pi 5, USB/Pi Camera, DualSense controller (Bluetooth)

## Architecture
Four components communicating via named pipe:
1. Hardware Producer (C++) — reads DualSense input via SDL2, writes to pipe
2. Vision Sensor (Python) — detects gestures via camera, writes to pipe
3. Remote Play Client (pyremoteplay) — PipeReader reads pipe, forwards to PS5
4. Web Dashboard (Flask) — therapist UI for config and monitoring

## Project Structure

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
├── pyremoteplay/       # Remote Play client library (in-repo fork)
│   └── pipe_reader.py  # Reads named pipe, forwards to Controller API
├── web/                # Web Dashboard (Flask)
│   ├── server.py       # All API endpoints + PSNConnectionManager
│   ├── templates/
│   │   └── dashboard.html
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
- Handles SIGTERM/SIGINT via signal handler — exits event loop cleanly without force-kill
- Pipe message format: buttons = `BUTTON_NAME\npress|release\n\n`, analog = `STICK\naxis\nvalue\n`

## Bluetooth Setup (system config — NOT in git, must be applied on fresh install)

### Required changes to /etc/bluetooth/input.conf
Two lines must be set (uncomment and change default):
```
UserspaceHID=true
ClassicBondedOnly=false
```
Then: `sudo systemctl restart bluetooth`

**Why UserspaceHID=true**: Routes BT HID through UHID instead of the old HIDP
kernel socket. UHID creates a proper HID bus device, `hid-playstation` binds to it
(alias hid:b0005g*v0000054Cp00000CE6), and `/dev/input/event*` nodes appear for SDL2.

**Why ClassicBondedOnly=false**: Allows the input profile to accept HID connections
during the pairing process before the bond is fully established.

### DualSense pairing procedure
Must be done in ONE bluetoothctl session so the agent handles the
"Authorize service" prompt that appears after pairing:

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

Verify success: `bluetoothctl info BC:C7:46:7D:51:0D` should show
`Bonded: yes`, `Trusted: yes`, `Connected: yes`.
Also check: `ls /dev/input/event5` and `cat /proc/bus/input/devices | grep DualSense`

### After a reboot
Press PS button on the controller — it auto-reconnects (bonded + trusted).
No re-pairing needed unless the device is explicitly removed.

**DualSense MAC:** BC:C7:46:7D:51:0D

## PSN Authentication
- Tokens stored in `config/psn_tokens.json` (online_id, credentials, expiration)
- Tokens expire — re-authenticate via the dashboard PSN Auth panel if needed
- The dashboard shows a re-auth link; follow it, copy the redirect URL back in

## Current Status
- **Last worked on:** 2026-04-16
- **Last completed:**
  - Initial setup: repo cloned, venv created, all Python deps installed
  - Named pipe at /tmp/my_pipe, Hardware Producer compiled and running headless
  - pyremoteplay integrated as in-process library (not subprocess)
  - Web dashboard full overhaul: PS5 device panel, real controller status,
    Bluetooth pairing UI, PSN auth panel, live status polling
  - Dashboard: PSN username (online_id) shown on PS5 device cards
  - Dashboard: Paired Controllers section with per-device Connect button
  - Fixed: controller status detection uses bluetoothctl BT fallback when
    /proc/bus/input/devices misses BT HID devices (HIDP path)
  - Fixed: DualSense BT full chain — UserspaceHID=true + ClassicBondedOnly=false
    + clean re-pair with persistent bonding. hid-playstation binds over BT via
    UHID, /dev/input/event5 (js0) created, SDL2 hotplug detects it
  - End-to-end chain verified with strace: DualSense BT → SDL2 → /tmp/my_pipe
    → PipeReader → pyremoteplay Controller API → PS5 button presses confirmed
  - Smoke test: all components launch cleanly, graceful shutdown
  - Web dashboard: live at http://192.168.0.145:5000
  - install.sh: full overhaul for RPi5 — python3-picamera2, bluez, BT config,
    venv --system-site-packages, startup checks (7 sections, idempotent)
  - Fixed camera: GestureDetector now uses Picamera2 instead of cv2.VideoCapture
    (IMX708 CSI camera requires libcamera; OpenCV V4L2 path does not work on RPi5)
  - Fixed venv: recreated with --system-site-packages so picamera2 is importable
  - Fixed numpy ABI: pinned numpy<2.0 in requirements.txt (system simplejpeg
    built against numpy 1.x; 2.x causes ValueError on dtype size mismatch)
  - Fixed vision FPS: open_pipe periodic retry now uses max_retries=1 — previously
    each retry blocked the frame loop for 10s (5 attempts × 2s); FPS now ~11
  - main.py starts cleanly: all 5 components up, Vision FPS ~11 and rising
  - Fixed: mappings.json race condition — add_mapping/remove_mapping now reload
    from disk before modifying, preventing two-instance stale-write clobber
  - Fixed: PS5 not registering gestures — missing controller.start() call after
    session connect; pyremoteplay requires it to send periodic STATE heartbeats
  - Gesture thresholds tuned: delta_threshold=0.03, raise_minimum=0.10
    (calibrated from live elbow diagnostic logs showing user peak ~0.194)
  - Debounce: 3 frames press + 3 frames release (was 5) for faster response
  - Fixed: analog stick latch on disconnect — SDL_CONTROLLERDEVICEREMOVED now
    sends four 0.0f axis messages before closing; controller was nested in wrong
    switch case (SDL_CONTROLLERAXISMOTION) — moved to outer switch(e.type)
  - Dashboard threshold panel: replaced sliders with +/- stepper buttons,
    instant apply, delta step=0.01, raise step=0.05
  - Dashboard: Restart System button in System Status panel — shows confirm
    dialog, POSTs to /api/system/restart, auto-reloads after 8s
  - Fixed restart button: was using inline bash 'exec >> log' with DEVNULL fds
    (silent failure) and sleep 2 (too short — shutdown takes ~6s, port conflict
    killed new process). Fix: write _restart.sh to disk, sleep 9 before relaunch
  - Gesture detection confirmed end-to-end: camera → MediaPipe → pipe → PS5
- **Next task:** Full gesture → PS5 test session; then add shoulder shrug gesture
- **Known issues:**
  - pyremoteplay is started via the web dashboard UI, not by main.py —
    pipe writers loop waiting for a reader until pyremoteplay connects
  - Vision Sensor FPS is ~26 (target 30+) — MediaPipe pose detection is the
    bottleneck on RPi5; not yet optimized
  - Flask dev server thread does not stop cleanly within 5s timeout on
    shutdown (logs a warning, exits eventually)
  - pyremoteplay logs ~10 "Version not accepted" protobuf errors during
    session negotiation — pre-existing, does not prevent READY state

## Gesture Configuration
- **Current mappings:** right_elbow_raise → CIRCLE, left_elbow_raise → CROSS
- **Thresholds:** delta_threshold=0.03 (speed), raise_minimum=0.10 (height)
- **Debounce:** 3 press frames, 3 release frames
- **Config file:** config/mappings.json (live-reloaded every 3s by vision_sensor)
- **Restart:** Dashboard "Restart System" button writes ~/playable/_restart.sh
  and runs it detached; _restart.sh is gitignored (auto-generated)
