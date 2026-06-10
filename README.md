# PlayAble — Rehabilitation Gaming System

PlayAble is a hybrid gesture-to-game control system designed for physical
rehabilitation. It maps body movements (detected via a Raspberry Pi camera +
MediaPipe pose/face landmarks) onto PlayStation 5 button presses, while also
forwarding inputs from a physical DualSense controller. Therapists can
configure gesture→button mappings live from a web dashboard, and patients
play real PS5 games using a mix of physical and movement-based controls.

> **Status:** working proof of concept on Raspberry Pi 5. Honest perf today:
> ~10 FPS vision (see [Known Limitations](#known-limitations)). Roadmap and
> gap analysis are in [`docs/gap_analysis.md`](docs/gap_analysis.md).

## Table of contents

- [How it works](#how-it-works)
- [Hardware](#hardware)
- [Architecture](#architecture)
- [Gestures](#gestures)
- [Installation](#installation)
- [Usage](#usage)
- [Web dashboard](#web-dashboard)
- [Bluetooth — DualSense pairing](#bluetooth--dualsense-pairing)
- [Network — WiFi & hotspot fallback](#network--wifi--hotspot-fallback)
- [Auto-start (systemd)](#auto-start-systemd)
- [Configuration files](#configuration-files)
- [Known limitations](#known-limitations)
- [Roadmap](#roadmap)
- [Repository layout](#repository-layout)
- [License & acknowledgements](#license--acknowledgements)

## How it works

1. The **camera** captures the patient at 640×480.
2. The **Vision Sensor** (Python) feeds frames into MediaPipe Holistic
   (pose + face landmarks) and evaluates a set of rule-based gesture
   detectors (e.g. *right elbow raise*, *mouth open*).
3. When a gesture passes a 3-frame debounce, the Vision Sensor writes a
   `BUTTON_NAME\npress|release\n\n` message to `/tmp/my_pipe`.
4. The **Hardware Producer** (C++/SDL2) concurrently writes button and
   analog-stick messages from the physical DualSense to the same pipe.
5. The **Remote Play Client** (`pyremoteplay`) reads the pipe and forwards
   each input to the PS5 over the Sony Remote Play protocol.
6. The **Web Dashboard** (Flask) is the therapist's control surface:
   live video feed with pose overlay, gesture/button mapping editor,
   threshold sliders, PSN auth, BT pairing, WiFi setup.

Target end-to-end latency: **< 150 ms**. Actual today: not directly measured;
slow-frame logs imply ~100 ms in the Python loop alone. See
[`docs/gap_analysis.md`](docs/gap_analysis.md) §1.2.

## Hardware

| Item | Notes |
|---|---|
| **Raspberry Pi 5** (8 GB) | BCM2712 4×A76 @ 2.4 GHz. Pi 4 is **not** sufficient for the current pipeline. |
| **IMX708 CSI camera** (Pi Camera Module 3) | Configured at 640×480 RGB888 via Picamera2. |
| **Sony DualSense** wireless controller | Bluetooth or USB-C. MAC currently pinned in `install.sh`. |
| **PlayStation 5** | Remote Play must be enabled; PSN account with Remote Play permission. |
| Local WiFi network (or none — see [hotspot](#network--wifi--hotspot-fallback)) | Same LAN as the PS5. |

## Architecture

Six components — three of them are pipe writers:

```
              ┌───────────────────────┐
   camera ──▶ │ Vision Sensor (Py)    │──▶┐
              └───────────────────────┘   │
              ┌───────────────────────┐   │
  DualSense ─▶│ Hardware Producer (C++)│──▶│  /tmp/my_pipe  ──▶  pyremoteplay  ──▶  PS5
              └───────────────────────┘   │  (named pipe)        (PipeReader)       (Remote Play)
              ┌───────────────────────┐   │
 evdev event7 │ TouchpadReader (Py)    │──▶┘
              └───────────────────────┘
                       ▲
                       │ config / status / video
              ┌───────────────────────┐
              │ Web Dashboard (Flask) │  ←── therapist
              └───────────────────────┘
              ┌───────────────────────┐
              │ WiFi Manager (Py)     │  ←── station / hotspot fallback
              └───────────────────────┘
```

**Why three writers?** The DualSense touchpad click is reported on a
separate evdev node (`/dev/input/event7`) that SDL2's `GameController` API
does not see over Bluetooth, so `TouchpadReader` reads it directly.

**Atomicity:** all messages are ≤100 B, well below Linux's `PIPE_BUF`
(4096 B), so concurrent writes are atomic by kernel guarantee. This is a
fragile invariant — see [`docs/gap_analysis.md`](docs/gap_analysis.md) §2.5.

## Gestures

| Gesture | Detector | Default threshold | Notes |
|---|---|---|---|
| `left_elbow_raise` | elbow.y above shoulder.y by `raise_minimum`, or upward delta_y < −`delta_threshold` | 0.10 / 0.03 | Position OR motion trigger |
| `right_elbow_raise` | same, mirrored | 0.10 / 0.03 | |
| `left_arm_forward` | wrist.z toward camera by delta_threshold | 0.03 | Uses MediaPipe pseudo-depth — noisy |
| `right_arm_forward` | same, mirrored | 0.03 | |
| `left_shoulder_shrug` | shoulder.y rises by `shrug_minimum` | 0.05 | Compared to opposite shoulder; no baseline calibration |
| `right_shoulder_shrug` | same, mirrored | 0.05 | |
| `mouth_open` | lip gap > `mouth_open_minimum` | 0.02 | Face mesh; no face-size normalization yet |

Mappings target any DualSense button: `CROSS`, `CIRCLE`, `SQUARE`, `TRIANGLE`,
`L1`, `R1`, `L2`, `R2`. Mappings are configured live from the dashboard and
persist in `config/mappings.json`, which the Vision Sensor re-reads every 3 s.

## Installation

The installer is a single script that handles system packages, Python
dependencies, the C++ build, hostname & mDNS, Bluetooth/udev rules, WiFi
power-save, captive-portal DNS, and the systemd unit:

```bash
git clone https://github.com/Dror-bszi/playable-pyremote.git ~/playable
cd ~/playable
./install.sh
sudo reboot
```

After reboot, `playable.service` starts automatically. The dashboard is
reachable at `http://playable-<id>.local:5000` (the `<id>` is the last 4
hex chars of `/proc/cpuinfo` Serial; on the reference device it is
`playable-c0e1`).

## Usage

```bash
# Status / logs / restart
sudo systemctl status playable
sudo journalctl -u playable -f
sudo systemctl restart playable

# Manual run (overrides the service — stop the service first)
sudo systemctl stop playable
source ~/playable/venv/bin/activate
python ~/playable/main.py
```

Once running:

1. Open the dashboard.
2. Authenticate with PSN (one-time — tokens persist in `config/psn_tokens.json`).
3. Pair the DualSense if not already done — see [Bluetooth](#bluetooth--dualsense-pairing).
4. Configure gesture→button mappings.
5. Click **Connect to PS5**. The Remote Play session starts and the pipe
   reader attaches; until that moment, the C++ producer and Vision Sensor
   loop quietly with no consumer.

## Web dashboard

Routes (Flask, defined in `web/server.py`):

- `/` — main dashboard
- `/setup` — WiFi setup page (also the captive portal target in hotspot mode)
- `/video_feed` — MJPEG live camera feed with MediaPipe overlay
- `/api/status` — system status (camera, FPS, mappings)
- `/api/ps5/devices` — saved PS5 devices from pyremoteplay profile
- `/api/controller/status` — DualSense state from HW Producer
- `/api/bluetooth/*` — scan, pair, connect, grab (USB-triggered pairing),
  paired-device list, USB/BT status
- `/api/psn/*` — OAuth flow, PIN, callback
- `/api/remoteplay/*` — start, stop, status
- `/api/mappings/*` — list, add, remove
- `/api/thresholds/*` — get, set
- `/api/network/*` — current mode, scan, connect, hostname
- `/api/system/restart` — restart the service (or `_restart.sh` in dev)

Dashboard features include: pose-overlay video feed, QR code modal for the
dashboard URL, BT scan & pair, Grab Controller button (60 s retry window
when USB cable is plugged in), threshold sliders, network mode badge.

## Bluetooth — DualSense pairing

PlayAble installs system-level Bluetooth changes (see `install.sh`):

- `/etc/bluetooth/input.conf` — `UserspaceHID=true`, `ClassicBondedOnly=false`
- `/etc/udev/rules.d/99-dualsense-nosniff.rules` — disables BT L2CAP sniff
  mode on the DualSense via `hcitool lp <MAC> rswitch`, run 2 s after the
  input node appears. Without this, the BCM4345C0 chip on the Pi 5 puts
  the link into sniff mode and HID report rate collapses, freezing input.
- `/etc/NetworkManager/conf.d/99-wifi-powersave.conf` — disables WiFi PM
  (BCM4345C0 shares WiFi/BT antenna; WiFi PM stalls BT).

### Pairing flows

**Wireless pairing** — one-shot bluetoothctl session:

```bash
bluetoothctl remove <MAC> 2>/dev/null; true
# DualSense in pairing mode (PS + Create), rapid flash, then:
{ echo "agent NoInputNoOutput"; echo "default-agent"; sleep 1
  echo "scan on"; sleep 8; echo "scan off"
  echo "pair <MAC>"; sleep 10
  echo "trust <MAC>"; sleep 1
  echo "connect <MAC>"; sleep 8; echo "quit"
} | bluetoothctl
```

**USB-triggered pairing (Grab Controller)** — plug the DualSense in over
USB-C, click **Grab Controller** in the dashboard. The server polls
`/dev/hidraw*` looking for the DualSense USB device for up to 60 s
(20 attempts × 3 s) with a live attempt counter in the UI. The controller
then auto-bonds to the Pi for subsequent wireless use.

After reboot: press the PS button on the DualSense — it auto-reconnects.

## Network — WiFi & hotspot fallback

PlayAble must reach a network for PS5 Remote Play; therapists deploying it
in a clinic without WiFi need a way to configure it. On startup
(`main.py:check_and_configure_network`):

1. Wait up to 20 s for a WiFi station connection.
2. If WiFi is up → log the SSID and continue.
3. If no WiFi → call `WiFiManager.start_hotspot()`:
   - `nmcli` creates an AP profile in shared mode (NM handles DHCP).
   - SSID `PlayAble-<ID>`, IP 192.168.4.1, no password.
   - `dnsmasq` (via NM's `dnsmasq-shared.d`) redirects all DNS → 192.168.4.1.
   - An `nft` table (`playable-nat`) redirects TCP :80 → :5000 so phone
     captive-portal probes hit Flask.
4. Phone connects to `PlayAble-<ID>` → "Sign in to network" popup → Flask
   serves `/setup` → user picks SSID, enters password, hits Connect.
5. On success, a QR code for `http://playable-<id>.local:5000` is shown.

> NetworkManager auto-names the WiFi station profile `preconfigured`, **not**
> the SSID. To bring it down: `sudo nmcli con down preconfigured`.

> RPi OS Bookworm ships only `nft` (no `iptables`). NM is configured with
> `firewall-backend=nftables` so its own masquerading uses nft too.

## Auto-start (systemd)

`install.sh` writes `/etc/systemd/system/playable.service`:

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

The dashboard **Restart System** button detects `INVOCATION_ID` to choose
between `systemctl restart playable` (when running as a service) and a
detached `_restart.sh` shim (when run directly).

## Configuration files

| File | Purpose |
|---|---|
| `config/mappings.json` | Gesture→button mappings + thresholds. Re-read every 3 s. |
| `config/ps5_config.json` | Last connected PS5 host + MAC→IP map. |
| `config/psn_tokens.json` | PSN OAuth tokens (online_id, credentials). Persist across reboots. |

Example `mappings.json`:

```json
{
  "thresholds": {
    "delta_threshold": 0.03,
    "shrug_minimum": 0.05,
    "mouth_open_minimum": 0.02,
    "raise_minimum": 0.10
  },
  "mappings": {
    "right_elbow_raise": "CIRCLE",
    "left_elbow_raise": "CROSS",
    "mouth_open": "TRIANGLE"
  }
}
```

## Known limitations

These are tracked in detail in [`docs/gap_analysis.md`](docs/gap_analysis.md).
Short list:

- **Vision FPS is ~10**, not 30+. Three compounding causes: MediaPipe Holistic
  runs when only Pose is needed; the `/video_feed` endpoint re-runs inference
  per frame; the legacy MediaPipe Python API does not use the Pi 5 GPU
  delegate. (gap_analysis.md §2.2)
- **FPS instrument is broken** — `vision_sensor.py:240–263` divides total
  frames by total process uptime; the log shows `0.0` while real loop time
  is ~100 ms.
- **No landmark smoothing** — raw MediaPipe coordinates drive thresholds.
  No Kalman, EMA, or One-Euro filter. Frame-to-frame noise dominates at
  current FPS.
- **No tests, no labeled dataset, no precision/recall numbers.** Gesture
  thresholds are heuristic, not validated.
- **No end-to-end latency instrumentation.** Only the Python loop is timed.
- **Three pipe writers with no synchronization.** Safe today because
  message size < PIPE_BUF, but undocumented in code.
- **`mappings.json` on the deployed device has `raise_minimum: 0.05`** (half
  the code default) — false-positive prone.
- **No per-subject calibration.** Resting shoulder asymmetry, neutral elbow
  position, and lip gap are not measured.
- **BT sniff-mode mitigation is fragile** — depends on a 2 s udev delay.
- **Flask dev server** does not stop cleanly within the shutdown timeout.
- **pyremoteplay** logs ~10 "Version not accepted" protobuf errors during
  session negotiation. Cosmetic — does not prevent READY state.

## Roadmap

Three milestones from `docs/gap_analysis.md`:

- **M1 (1–2 weeks) — Make it measurable.** Fix FPS instrument; add per-event
  latency UUIDs; switch Holistic→Pose; fix `/video_feed` double-inference.
- **M2 (2–4 weeks) — Make it robust.** One-Euro filter; hysteresis on
  thresholds; visibility checks on landmarks; pytest suite for mappings,
  debounce, pipe parser; split `web/server.py` into blueprints.
- **M3 (4–8 weeks) — Make it research-defensible.** Patient profiles:
  per-subject baseline calibration saved to `config/profiles/<id>.json`.
  Recorded-clip evaluation harness (5 subjects × 7 gestures, hand-labeled,
  precision/recall + confusion matrix). Migrate to
  `mp.tasks.vision.PoseLandmarker` with GPU delegate. Thermal monitoring.
  Auto-exposure lock.

## Repository layout

```
playable/
├── controller/                  # Hardware Producer (C++ SDL2)
│   ├── main.cpp
│   ├── CMakeLists.txt
│   └── build/detect_controller  # compiled binary
├── core/                        # Vision Sensor (Python)
│   ├── gestures.py              # MediaPipe + gesture detectors
│   ├── mappings.py              # GestureMapping (load/save/validate)
│   └── vision_sensor.py         # main loop, debounce, pipe write
├── network/
│   ├── __init__.py
│   └── wifi_manager.py          # WiFiManager + get_hostname() (serial-based)
├── pyremoteplay/                # in-tree fork of pyremoteplay
│   └── pipe_reader.py           # reads /tmp/my_pipe → Controller API
├── web/                         # Flask dashboard
│   ├── server.py                # routes + PSN/BT/network managers
│   ├── templates/{dashboard,setup}.html
│   └── static/{css,js,qr.png}
├── config/
│   ├── mappings.json
│   ├── ps5_config.json
│   └── psn_tokens.json
├── docs/
│   └── gap_analysis.md          # PoC→academic gap analysis
├── debugging_utils/             # manual scripts (not pytest)
├── main.py                      # orchestrator + TouchpadReader
├── install.sh                   # full system bring-up
├── requirements.txt
└── README.md                    # this file
```

## License & acknowledgements

- **MediaPipe** (Google) — pose & face landmark detection
- **pyremoteplay** — PS5 Remote Play protocol (vendored in `pyremoteplay/`)
- **SDL2** — DualSense input on Linux
- **NetworkManager + nft + dnsmasq + avahi** — networking stack
