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

## Repository
- **GitHub:** https://github.com/Dror-bszi/playable-pyremote
- **Branch:** main
- **Local on RPi:** ~/playable

## Tech Stack
- **Vision:** Python + MediaPipe + OpenCV (pose detection)
- **Controller input:** C++ + SDL2 (Hardware Producer, captures DualSense)
- **PS5 connection:** pyremoteplay (Remote Play protocol)
- **Web dashboard:** Flask
- **IPC:** Named pipe at /tmp/my_pipe
- **Hardware:** Raspberry Pi 5, USB/Pi Camera, DualSense controller

## Architecture
Four components communicating via named pipe:
1. Hardware Producer (C++) — reads DualSense input
2. Vision Sensor (Python) — detects gestures via camera
3. Remote Play Client (pyremoteplay) — sends input to PS5
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
├── pyremoteplay/       # Remote Play client library
├── web/                # Web Dashboard (Flask)
│   ├── server.py
│   ├── templates/
│   └── static/
├── config/
│   └── mappings.json
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
- Pipe open is non-blocking (O_NONBLOCK): retries every 500ms until a reader
  connects, so startup order with pyremoteplay does not matter

## Current Status (update at end of each session)
- **Last worked on:** 2026-04-12
- **Last completed:**
  - Initial setup: repo cloned, venv created, all Python deps installed
  - Named pipe created at /tmp/my_pipe
  - C++ Hardware Producer compiled (controller/build/detect_controller)
  - Fixed: removed SDL_INIT_VIDEO — binary now runs headless without a display
  - Fixed: pipe open is now non-blocking (O_NONBLOCK + ENXIO retry loop)
  - Fixed: write errors in sendPipeButton/sendPipeAnalog handle EAGAIN silently
- **Next task:** End-to-end smoke test — start main.py and verify Vision Sensor
  and Web Dashboard launch without errors (Hardware Producer will wait for pipe
  reader; no PS5 connection needed for this test)
- **Known issues:**
  - SDL_CONTROLLERDEVICEADDED/REMOVED events are nested inside the
    SDL_CONTROLLERAXISMOTION case in main.cpp — hot-plugging won't work
    (pre-existing bug, not yet fixed)
  - pyremoteplay is started via the web dashboard UI, not by main.py —
    the Hardware Producer will loop waiting for a pipe reader until it is started
