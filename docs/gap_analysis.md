# PlayAble — Gap Analysis: PoC → Academic-Grade Final Project

**Date:** 2026-06-10
**Author:** Claude (gap analysis pass)
**Codebase commit:** e3aa94ef082b3f84857074fd71f4c329e48dfe9a (branch: main)

## Executive Summary

PlayAble is a working PoC that correctly wires together MediaPipe pose detection, a C++/SDL2 controller bridge, and pyremoteplay via a single named pipe, with sensible reliability mitigations for known hardware quirks (BCM4345C0 sniff-mode workaround, BT/WiFi co-existence, captive-portal hotspot fallback). However, the runtime metrics show the system is **operating at ~10 FPS** (slow-frame log lines record `Avg: 100–103 ms` per loop iteration against a `33.3 ms` target — `run.log:2026-06-10 22:51:31`), the FPS instrument itself reports `0.0` while `frame_count` is incrementing (a latent bug in `vision_sensor.py:240–263`), and there is **zero automated test coverage** (no `tests/` directory; only `debugging_utils/test_video_feed.py`). For an academic defense the most critical gaps are (1) absence of end-to-end latency measurement, (2) no temporal smoothing/filtering on landmarks (raw MediaPipe output drives detection with frame-to-frame differencing — `gestures.py:267–333`), (3) the gesture set is heuristically thresholded with no validation dataset or false-positive/false-negative numbers, and (4) MediaPipe Holistic is being used when only Pose is needed for the configured gestures, paying ~2× inference cost for nothing. Recommended priority order: instrument latency → cut Holistic→Pose-only and verify FPS recovery → add One-Euro filter on landmarks → add a recorded-clip evaluation harness → write unit tests for `mappings.py` and `pipe_reader.py` parser → harden `web/server.py` (input validation, lock scope).

## 1. Software & Algorithmic Gaps

### 1.1 Code Architecture and Separation of Concerns

- **Global mutable state in the Flask layer.** `web/server.py:53–56` declares four module-level globals (`gesture_detector`, `gesture_mapping`, `psn_connection_manager`, `bluetooth_manager`) that are then mutated by `init_app()` at `web/server.py:484–494`. Routes reference these via the global namespace (`web/server.py:567–572`). This precludes multiple Flask app instances, makes mocking for tests impossible without `monkeypatch`, and produces import-order coupling.
- **`web/server.py` is a 1,228-line god-file** mixing PSN OAuth (`web/server.py:92–214`), Remote Play session lifecycle (`web/server.py:216–334`), Bluetooth scanning (`web/server.py:349–481`), captive-portal probe handling (`web/server.py:1132–1161`), threshold validation (`web/server.py:921–965`), MJPEG video streaming (`web/server.py:1017–1087`), Flask routes, and process restart (`web/server.py:507–547`). Split into `web/routes/{psn,bluetooth,network,gestures,video}.py` + `services/{psn_manager,bluetooth_manager}.py`.
- **Two independent `GestureMapping` instances** exist concurrently: one owned by the orchestrator (`main.py:373–377`, passed into VisionSensor) and another created by the web `init_app()` is implicit through the threshold-update path (`web/server.py:951–956`) — actually they share the orchestrator's `gesture_mapping`. But `mappings.py:91–105` has a `load_mappings()` self-reload-before-write hack ("we don't clobber concurrent changes — web server and vision_sensor each have their own GestureMapping instance") which contradicts the orchestrator's shared-state design. Either the comment is stale and should be deleted, or there is in fact an aliasing bug to find; in either case this is a code-comprehension hazard.
- **`pyremoteplay/pipe_reader.py` is in the same git tree as a "library" but lives inside the `pyremoteplay` fork directory**, blurring the boundary between in-house code and vendored third-party. This complicates upstreaming/updating the pyremoteplay fork.
- **`main.py:78–119` defines `TouchpadReader`** — a parallel pipe writer that bypasses the C++ Hardware Producer entirely. This means the named pipe now has **three writers** (Hardware Producer, Vision Sensor, TouchpadReader) and **one reader** (PipeReader). Pipe writes from multiple processes are atomic only up to `PIPE_BUF` (4096 bytes on Linux), and the three writers send variable-length multi-line frames (`controller/main.cpp:21–25`, `vision_sensor.py:218`, `main.py:158`). Interleaved writes from concurrent processes can corrupt the protocol. NO synchronization exists.

### 1.2 Latency Bottlenecks

A realistic end-to-end budget against the **150 ms target**:

| Stage | Code reference | Estimated | Measured? |
|---|---|---|---|
| Camera capture (Picamera2 RGB888 640×480) | `gestures.py:79–81` | 5–15 ms | NOT MEASURED |
| MediaPipe Holistic inference (model_complexity=0, pose+face) on RPi5 CPU | `gestures.py:38–42`, `gestures.py:97` | 60–90 ms | NOT MEASURED — but slow-frame log of 100 ms avg implies ≥60 ms here |
| Gesture eval (per-button arithmetic, dict iteration) | `gestures.py:267–333` | <1 ms | NOT MEASURED |
| Debounce (3 frames at 10 FPS = 300 ms) | `vision_sensor.py:23–24`, `vision_sensor.py:225–246` | **+300 ms at current FPS** | implicit |
| Python pipe write (`os.write` of ~30 bytes) | `vision_sensor.py:216–219` | <1 ms | NOT MEASURED |
| pyremoteplay encode + send | `pipe_reader.py:189–211` | NOT MEASURED | NOT MEASURED |
| LAN to PS5 + PS5 input register | external | 20–50 ms | NOT MEASURED |
| **Total to PS5 input** | | **~390–460 ms** | NOT MEASURED |

**The dominant latency is debounce-at-low-FPS**: 3 confirmed frames × (1/10 FPS) = 300 ms of waiting before a `press` is even emitted. At 30 FPS this collapses to 100 ms. **No measurement instrumentation exists anywhere in the pipeline.** There is no per-stage timer, no tracing ID per event, no histogram. The only timing artefact is the slow-frame warning in `vision_sensor.py:374–387`, which measures the *Python loop* (capture+inference+gesture+pipe write) but not the rest of the chain.

### 1.3 MediaPipe Holistic Limitations

`gestures.py:42–46` instantiates `mp.solutions.holistic.Holistic` with `model_complexity=0`. Holistic runs three sub-models per frame:

- **Pose**: 33 landmarks (the only ones used by all gestures except `mouth_open` — see `gestures.py:280–287`).
- **Face mesh**: 468 landmarks (used only for `mouth_open`, `gestures.py:431–434`).
- **Hands**: 21×2 landmarks (NEVER used — no gesture references hand landmarks).

On a Pi 5 CPU, `Holistic(model_complexity=0)` typically runs 60–80 ms/frame; `Pose(model_complexity=0)` alone runs ~30–40 ms. **Switching to `mp.solutions.pose.Pose` and gating `mouth_open` behind an explicit face-mesh pass only when that mapping is active would nearly double FPS.** Hand model is dead weight in the current configuration.

What Holistic does NOT give you, regardless of complexity: depth in metric units (`z` is image-relative pseudo-depth), multi-person disambiguation (single subject only), or any occlusion robustness across self-occlusion (e.g. arm crossing torso). For rehabilitation use cases where a patient may rotate or partially occlude, this is a real limitation — a custom Pose model fine-tuned on rehabilitation poses, or BlazePose 3D with calibrated depth, would be justified if range-of-motion measurement (not just gesture triggering) becomes a requirement.

### 1.4 Skeletal Data Smoothing/Filtering

**There is zero landmark smoothing.** `gestures.py:113–116` writes `self.current_landmarks = results.pose_landmarks` and `gestures.py:265` writes `self.previous_landmarks = self.current_landmarks` — raw MediaPipe normalized coordinates are used directly, frame to frame, with no EMA, no Kalman, no One-Euro filter, no temporal smoothing window. The delta calculation at `gestures.py:139–141` is a single-frame difference, which makes `delta_y` extremely noisy at low FPS (the noise floor of MediaPipe Pose normalized coords is ~0.005–0.01 even on a stationary subject; with `delta_threshold=0.03` at `mappings.json:3`, this is only ~3× the noise floor).

Recommendation: insert a One-Euro filter (Casiez et al. 2012) on each used landmark before any thresholding. This is ~30 lines of Python, well-cited in HCI literature, and is what every production gesture system uses. It gives a defensible "noise reduction" component in the methodology chapter.

### 1.5 Gesture Detection Robustness

Looking at actual logic:

- **`_check_elbow_raise` (`gestures.py:284–339`)** triggers if `vertical_diff > raise_minimum` **OR** if `delta_y < -delta_threshold` **AND** `vertical_diff > 0`. The OR-clause is a position trigger; the AND-clause is a motion trigger. **There is no hysteresis** — the same threshold is used to enter and leave the detected state, so a landmark hovering near `raise_minimum ± noise` will oscillate every frame (this is the reason the 3-frame debounce was added downstream).
- **`mappings.json` currently has `raise_minimum: 0.05`** which is half of the code default (`gestures.py:50`, `mappings.py:24`) of `0.10`. This will dramatically increase false-positive rate. At 0.05, the threshold is barely 5% of frame height — natural shoulder rise during breathing can exceed this.
- **`_check_arm_forward` (`gestures.py:341–360`)** uses raw `delta_z` from MediaPipe. MediaPipe's `z` is image-plane pseudo-depth, not metric, and is the noisiest of the three landmark dimensions. Without smoothing or a 3D calibration, this gesture is unreliable by construction.
- **`_check_shoulder_shrug` (`gestures.py:362–389`)** compares `right_sh.y - left_sh.y` against `shrug_minimum=0.05`. The shoulders' natural y-difference depends on subject posture and camera angle — a slightly tilted subject head-on will trigger this without shrugging. **No baseline calibration** subtracts the resting asymmetry.
- **`_check_mouth_open` (`gestures.py:391–411`)** uses raw `lip_gap` in normalized face-mesh coordinates with no normalization against face size. A subject closer to the camera has a larger lip gap for the same physical mouth opening.
- **No `visibility` field check anywhere.** MediaPipe provides per-landmark `visibility ∈ [0,1]`; the code reads `.x`, `.y`, `.z` without checking `.visibility`. When a limb is out of frame or occluded, MediaPipe returns hallucinated coordinates with low visibility, and the system happily evaluates gestures on those.
- **No false-positive / false-negative measurement exists in the repo.** No labeled dataset, no confusion matrix, no per-gesture precision/recall numbers. For an academic project this is the single largest evidence gap.

### 1.6 Error Handling Coverage

- **Broad `except Exception` clauses that swallow context:**
  - `gestures.py:90` (`return None` on any capture failure — no logging).
  - `gestures.py:78`, `gestures.py:419–423` (cleanup silently swallows everything via `try/except: pass`).
  - `pipe_reader.py:99–101`, `pipe_reader.py:111–113` (broad recovery with sleep).
  - `web/server.py:77–78` (`_load_ps5_config` swallows JSON corruption silently — returns `{}`).
  - `mappings.py:91–94` (`load_mappings(...) except Exception: pass` before saving — a corrupted config file is silently ignored, then overwritten).
- **`web/server.py:75`** opens `PS5_CONFIG_PATH` without `with` is fine — actually it does use `with`. But `_save_ps5_config` at `web/server.py:82–89` writes without `fsync` or atomic-rename — a crash mid-write will leave a truncated file that the silent-swallow above will then ignore.
- **`vision_sensor.py:227–248`** has a reopen-on-BrokenPipeError path that references `message` from the outer scope after closing — if `open_pipe()` returns with `self.pipe = None` (lines 195–203), the subsequent `self.pipe.write(message)` at line 235 will throw `AttributeError`. **This recovery path is broken.**
- **`pipe_reader.py:159` accepts `value` in `[-1.0, 1.0]`** and clamps if out of range, but does not check for NaN/Inf. `float('nan')` will pass the parser and propagate into the controller.

### 1.7 Test Coverage

**There are no tests.** `~/playable/tests` does not exist; the only `test_*.py` is `debugging_utils/test_video_feed.py` (which by its location is a manual debug script, not pytest). No CI configuration, no coverage report, no fixtures.

A minimum suite that fits in a final-project scope:

- `tests/test_mappings.py` — JSON load/save round-trip, validation of invalid gesture/button names (`mappings.py:107–145`), threshold range checks (`mappings.py:174–210`).
- `tests/test_pipe_protocol.py` — fuzz `PipeReader._parse_message` (`pyremoteplay/pipe_reader.py:118–186`) with malformed inputs, partial reads, interleaved messages. Currently the parser will treat a corrupted line as "invalid" and return None, but interleaved 3-line and 3-line messages from concurrent writers (see §1.1) are unhandled.
- `tests/test_gestures.py` — synthetic landmark sequences (mock `current_landmarks`) verifying threshold edges and hysteresis (once added).
- `tests/test_debounce.py` — sequence of (press,press,press,release,...) inputs into `VisionSensor.process_gesture_events` and assert correct emit pattern.
- `tests/integration/test_pipe_e2e.py` — spawn a fake pipe reader, send known frames, assert button calls (mocked Controller).

### 1.8 Concurrency Model and Thread Safety

- Threads in the system: main thread (orchestrator), VisionSensorThread (`main.py:381–391`), WebDashboardThread (`main.py:403–419`), TouchpadReader (`main.py:99–108`), BTScanThread (`web/server.py:365–367`), WiFiConnect (`web/server.py:1218`), RemotePlayThread (`web/server.py:277–282`) plus the asyncio loop it owns, PipeReader (`pyremoteplay/pipe_reader.py:43–47`), and a Flask request thread pool (`web/server.py:1096`).
- **`gesture_detector.thresholds` is a dict mutated from Flask route thread via `update_thresholds()`** (`gestures.py:160–173`) while the vision thread reads it on every frame in `_check_elbow_raise` etc. (`gestures.py:306`). Reads/writes of single Python dict slots are atomic under CPython GIL today, but the bracketed assign `self.thresholds['delta_threshold'] = delta` is two ops conceptually and there is **no lock**.
- **`PSNConnectionManager._lock` (`web/server.py:104`)** is held across the entire `start_remoteplay` (lines 218–306) including a 10-second `ready_event.wait(timeout=10)` — meaning a concurrent `/api/remoteplay/disconnect` request blocks the Flask worker for up to 10 s. The lock scope is too wide.
- **`PipeReader._forward_to_controller` (`pyremoteplay/pipe_reader.py:188–222`)** is called from the pipe reader thread but `controller.button()` / `controller.stick()` from pyremoteplay are designed to be invoked from the session asyncio loop. The pyremoteplay `Controller` may use locks internally, but the cross-thread call is undocumented and a latent race.
- **GIL implications**: MediaPipe inference releases the GIL during native compute; Flask request threads can therefore run concurrently with vision processing. However, the camera feed endpoint `/video_feed` (`web/server.py:1017–1087`) calls `gesture_detector.get_current_frame()` (`gestures.py:148–187`) which itself runs MediaPipe (`gestures.py:165`) — **a second concurrent Holistic inference** while the vision thread is doing its own. This roughly halves effective FPS whenever a browser is watching the live feed.

## 2. Hardware Gaps

### 2.1 RPi 5 Compute Limitations

The Pi 5 (BCM2712, 4× Cortex-A76 @ 2.4 GHz) has no NPU. MediaPipe Tasks `Pose Landmarker` can use XNNPACK delegate (CPU) but not Hexagon / Edge TPU. The `solutions.holistic` API used in `gestures.py:42` is the **legacy** MediaPipe API and pins to CPU TFLite. The newer `mediapipe.tasks.python.vision.PoseLandmarker` supports `BaseOptions(delegate=BaseOptions.Delegate.GPU)` and on Pi 5 will use the VideoCore VII GPU via OpenGL ES, typically halving inference cost. **The code is using the slower of the two MediaPipe Python APIs.**

### 2.2 Current ~10 FPS vs 30+ Target — Root Cause

Three compounding causes, in order of impact:

1. **Holistic instead of Pose** (§1.3) — running 3 models when 1 is needed. Switching to `mp.solutions.pose.Pose` should bring inference from ~80 ms to ~40 ms. *Estimated +15 FPS.*
2. **Legacy MediaPipe API on CPU** (§2.1) — switching to `mp.tasks.vision.PoseLandmarker` with GPU delegate should halve again. *Estimated +10 FPS.*
3. **`/video_feed` runs a second Holistic inference per request** (`gestures.py:165`, §1.8). If the dashboard is open during a session, FPS halves. **Fix: have `get_current_frame()` reuse the latest `self.current_frame` and `self.current_landmarks` without re-running inference.** *Estimated: prevents FPS halving when dashboard is watched.*

**The FPS instrument itself is broken.** `vision_sensor.py:240–263` computes `fps = self.frame_count / elapsed` where `elapsed = current_time - self.start_time`. `start_time` is set in `__init__` (line 60) and **never reset**. As the process runs longer, `frame_count / (huge elapsed)` approaches 0. The log entries showing `FPS: 0.0 | Frames processed: 60934` (`run.log` repeated) are the symptom: the instrument is averaging over the entire process lifetime, not a recent window. Fix: maintain a rolling window — e.g. `fps = (self.frame_count - self._last_window_frame_count) / (current_time - self._last_window_time)`, then snapshot both at the end of `log_fps()`.

### 2.3 Thermal Constraints

No thermal monitoring exists in the code. The Pi 5 will thermal-throttle at 85 °C (BCM2712 default) — under sustained MediaPipe load on a closed enclosure with the camera ribbon nearby (typical PlayAble form factor), the SoC can reach this within minutes. Recommendation: log `/sys/class/thermal/thermal_zone0/temp` every 30 s and surface it on the dashboard. If a session experiences thermal throttling mid-rehabilitation, the FPS will drop further and skew detection.

### 2.4 Camera Hardware (IMX708)

The IMX708 is a 12 MP sensor capable of 1080p60. `gestures.py:23–26` configures it at **640×480**, which is appropriate for MediaPipe (Pose internally downsamples to 256×256 anyway). The `format="RGB888"` choice (line 25) avoids YUV→RGB conversion in software. **One gap:** auto-exposure is left default; in a clinical room with mixed sunlight + LED, AE hunting can cause 30–100 ms exposure swings that affect landmark stability. The Picamera2 `set_controls({'AeEnable': False, 'ExposureTime': N, 'AnalogueGain': G})` API can lock exposure once a stable subject is detected.

### 2.5 IPC: Named Pipe vs Alternatives

- **Three writers, one reader, no synchronization** (§1.1, `main.py:158`, `vision_sensor.py:218`, `controller/main.cpp:23`).
- **Write atomicity:** POSIX `write()` on a pipe is atomic up to `PIPE_BUF` (4096 B on Linux). All current messages are <100 B, so individual writes are safe. **However**, the protocol is multi-line — a "press" event is one `write()` of three lines, which is atomic. So in practice interleaving at byte level does not happen today. **But**: `vision_sensor.py:218` calls `self.pipe.write(message)` followed by `self.pipe.flush()`. Python file objects buffer; if the buffer threshold is crossed mid-message during a write, the flush could split. This is fragile.
- **No backpressure handling**: if the PipeReader is slow (e.g. blocked on a slow `controller.button()` call), writers will eventually block on `write()` (since the read side opens in blocking mode, `pyremoteplay/pipe_reader.py:67`). The C++ side opens `O_NONBLOCK` (`controller/main.cpp:91`) so a full pipe will cause `EAGAIN` and silently drop events (`controller/main.cpp:21–25` — note the `errno != EAGAIN` guard suppresses the error log).
- Alternative: a Unix domain socket with `SOCK_SEQPACKET` gives framed, atomic, multi-writer-safe semantics. Or move to ZeroMQ PUB/SUB with topic = button-name. For a research-grade project, the pipe-based design is defensible but should be acknowledged in the limitations section.

### 2.6 BT HID Stability

The BCM4345C0 sniff-mode workaround (udev rule + `hcitool lp rswitch`) documented in CLAUDE.md is a known fragile mitigation. The C++ heartbeat (`controller/main.cpp:248–254`, 200 ms neutral-axis send) compensates for the *symptom*. Long-term fixes that would be more defensible academically:

- Use a **wired USB-C** connection to the DualSense for the academic demo; eliminates BT entirely. Existing `_dualsense_usb_connected()` at `web/server.py:811–822` already detects this. Document BT as "best-effort secondary".
- Or replace the BCM4345C0 with an external USB BT 5.0 dongle (Realtek RTL8761B is well-supported on Linux) — bypasses the sniff bug.

## 3. Actionable Recommendations

| # | Gap | Severity | Fix | Complexity |
|---|-----|----------|-----|------------|
| 1 | FPS instrument reports 0.0 — no usable performance metric | Critical | Rolling-window FPS in `vision_sensor.py:240–263` (snapshot frame_count and time on each log) | Low |
| 2 | No end-to-end latency measurement anywhere | Critical | Add per-event UUID timestamp at gesture detection; log when PipeReader forwards; compute Δ. Emit histogram. | Low |
| 3 | MediaPipe Holistic when only Pose+(optional)FaceMesh is needed | Critical | Replace `gestures.py:42–46` with `mp.solutions.pose.Pose`; gate FaceMesh behind `mouth_open` mapping presence | Low |
| 4 | `/video_feed` re-runs MediaPipe per frame, halving FPS when dashboard is open | Critical | In `gestures.py:148–187` reuse `self.current_frame` + `self.current_landmarks`, do not call `holistic.process()` | Low |
| 5 | No landmark smoothing — raw noisy coords drive thresholds | Critical | Add One-Euro filter on used landmarks before `_check_*` methods | Medium |
| 6 | No automated tests | Critical | Add pytest suite per §1.7; minimum: mappings, debounce, pipe parser, gesture-edge | Medium |
| 7 | No labeled-dataset evaluation of gesture detection | Critical | Record 30–60 s per gesture × 5 subjects, hand-label, compute precision/recall vs current thresholds | Medium |
| 8 | Three pipe writers without synchronization risks corruption under load | High | Document protocol max-size guarantee (≤PIPE_BUF) in code; consider SOCK_SEQPACKET migration if grows | Medium |
| 9 | No hysteresis — same threshold for enter/exit causes oscillation | High | Two thresholds per gesture: `enter > exit`, e.g. enter=0.10, exit=0.07 in `_check_elbow_raise` | Low |
| 10 | No visibility check on landmarks | High | Gate gesture eval on `landmark.visibility > 0.5` in `gestures.py:_check_*` | Low |
| 11 | Broken pipe-recovery path in `vision_sensor.py:227–248` | High | Guard `self.pipe.write(message)` with `if self.pipe is not None` after `open_pipe()` | Low |
| 12 | `mappings.json` has `raise_minimum: 0.05` (half of code default) — increases FP rate | High | Restore to 0.10 unless a calibration justifies the change; document the decision | Low |
| 13 | `web/server.py` is 1228 lines, poor separation of concerns | High | Split into `web/routes/*.py` and `services/*.py`; routes register via blueprint | Medium |
| 14 | `PSNConnectionManager._lock` held for 10 s during `start_remoteplay` | Medium | Narrow lock to state-mutation only; use a separate `connecting` flag for guard | Low |
| 15 | No thermal monitoring during sustained sessions | Medium | Add `/sys/class/thermal/thermal_zone0/temp` poll to dashboard status endpoint | Low |
| 16 | Camera auto-exposure left default — causes landmark instability under mixed lighting | Medium | Add Picamera2 `set_controls({'AeEnable': False, ...})` after stable detection | Medium |
| 17 | `_check_arm_forward` uses raw MediaPipe `z` (noisiest dim) without smoothing | Medium | Apply One-Euro to z; consider removing this gesture if smoothing insufficient | Low |
| 18 | No NaN/Inf check in pipe analog parser | Medium | Add `math.isfinite(value)` check in `pipe_reader.py:160` before clamp | Low |
| 19 | Legacy MediaPipe Python API; no GPU delegate | Medium | Migrate to `mp.tasks.vision.PoseLandmarker` with `Delegate.GPU` | High |
| 20 | TouchpadReader (`main.py:78–119`) duplicates evdev reading that SDL should handle | Low | Document why; or upstream-fix SDL to read all hidraw nodes; or merge into Hardware Producer process | Medium |

### Severity definitions
**Critical**: blocks academic defense (no metric, no evaluation, dominant latency). **High**: visible reliability issue under normal use. **Medium**: edge-case or polish. **Low**: code-quality / sustainability.

## 4. Suggested Roadmap (3 milestones)

**M1 (1–2 weeks) — Make it measurable:**
- Fix FPS rolling-window bug (#1).
- Add end-to-end latency instrumentation: per-event UUID, log at every hop, histogram report (#2).
- Switch Holistic → Pose-only and gate FaceMesh behind mapping (#3).
- Fix `/video_feed` double-inference (#4).
- Verify FPS recovers to ≥25 on idle dashboard; ≥20 with dashboard open.

**M2 (2–4 weeks) — Make it robust:**
- One-Euro filter on landmarks (#5).
- Hysteresis on thresholds (#9), visibility checks (#10), broken-recovery fix (#11), NaN check (#18), restore raise_minimum (#12).
- pytest suite for mappings, debounce, pipe parser, threshold edges (#6).
- Refactor `web/server.py` into routes/services (#13).
- Narrow PSN lock scope (#14).

**M3 (4–8 weeks) — Make it research-defensible:**
- Recorded-clip evaluation harness: 5 subjects × 7 gestures × 30 s each, hand-labeled, run through pipeline offline (#7). Compute precision/recall, confusion matrix, latency histogram.
- Per-subject calibration: short baseline-capture at session start that records resting shoulder asymmetry, neutral elbow position, lip gap — subtract from runtime measurements.
- Migrate to `mp.tasks.vision.PoseLandmarker` GPU delegate; benchmark (#19).
- Thermal monitoring + auto-exposure lock (#15, #16).
- Document the BT sniff-mode mitigation and IPC choice in the thesis Limitations chapter (#8, §2.6).

## 5. Open Questions for the Author

1. **What latency was actually measured in patient sessions?** The CLAUDE.md target is <150 ms end-to-end but the run.log shows 100 ms loop time alone before pipe/network/encode. Is there any session recording where you measured wall-clock from gesture onset to PS5 reaction?
2. **What was the empirical false-positive rate for the deployed gestures during rehabilitation sessions?** Without labeled data, threshold values like `delta_threshold=0.03` are folklore. Is there an internal record (notebook, video) of when the system fired incorrectly?
3. **Why is `mappings.json` currently configured with only `right_elbow_raise → CIRCLE`?** Is this a deliberate clinical setup (single-arm rehab) or test leftover? The `raise_minimum: 0.05` is half the default — was it tuned on a specific patient?
4. **Has the system ever been used with the `mouth_open` or `*_shoulder_shrug` gestures by a real subject?** These gestures exist in code but the live config doesn't use them — are they validated or speculative?
5. **The TouchpadReader (`main.py:78–119`) bypasses SDL and reads `/dev/input/event7` directly. How brittle is the device-node numbering across reboots, controller swaps, and udev hotplugs?** Has it been seen to land on `event6` or `event8`?
6. **Why was pyremoteplay forked in-tree instead of vendored as a dependency?** What modifications were made vs upstream, and how will security patches be carried forward?
7. **What is the recovery story when the PS5 reboots, or the patient disconnects WiFi mid-session?** The code restarts components but the PSN session is not auto-resumed (`web/server.py:308–334`).
8. **For the IRB / clinical-trial path: does the system retain video frames or landmarks after the session?** I see no recording or PII-handling code, but a thesis defense will require a statement of data handling.
