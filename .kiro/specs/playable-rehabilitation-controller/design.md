# Design Document

## Overview

PlayAble integrates three major components into a cohesive rehabilitation gaming system:

1. **Hardware Producer** (C++ SDL2) - Already implemented, captures physical controller and keyboard inputs
2. **Vision Sensor** (Python MediaPipe) - To be implemented, detects body movements and generates virtual button presses
3. **pyremoteplay Consumer** - To be modified, reads from Named Pipe and communicates with PS5

The system uses a Named Pipe (`/tmp/my_pipe`) as the communication backbone. Both the Hardware Producer and Vision Sensor write commands to the pipe independently, while pyremoteplay reads from the pipe and forwards all commands to the PS5. This direct channel minimizes latency by eliminating intermediate processing layers.

## Architecture

### High-Level Data Flow

```
┌─────────────────────┐      ┌─────────────────────┐
│  USB/Pi Camera      │      │  DualSense          │
│                     │      │  Controller         │
└──────┬──────────────┘      └──────┬──────────────┘
       │ Video Frames               │ SDL2 Events
       ▼                            ▼
┌─────────────────────┐      ┌─────────────────────┐
│  Vision Sensor      │      │  Hardware Producer  │
│  (Python MediaPipe) │      │  (C++ SDL2)         │
│  ❌ To Implement    │      │  ✅ Implemented     │
└──────┬──────────────┘      └──────┬──────────────┘
       │                             │
       │ Write to Pipe               │ Write to Pipe
       │                             │
       └──────────┬──────────────────┘
                  │
                  ▼
         ┌────────────────────┐
         │   Named Pipe       │
         │   /tmp/my_pipe     │
         └────────┬───────────┘
                  │
                  │ Read from Pipe
                  ▼
         ┌────────────────────┐
         │   pyremoteplay     │
         │   + PipeReader     │
         │   ⚠️  To Modify    │
         └────────┬───────────┘
                  │
                  │ Remote Play Protocol
                  ▼
         ┌────────────────────┐
         │   PS5 Console      │
         └────────────────────┘
```

### Component Interaction

```
┌──────────────────────────────────────────────────────────┐
│                    Main Orchestrator                      │
│                    (main.py)                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Subprocess:  │  │ Thread:      │  │ Thread:      │  │
│  │ Hardware     │  │ Vision       │  │ Web          │  │
│  │ Producer     │  │ Sensor       │  │ Dashboard    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└──────────────────────────────────────────────────────────┘
                           │
                           │ Starts subprocess
                           ▼
                  ┌────────────────────┐
                  │   pyremoteplay     │
                  │   (Subprocess)     │
                  │   Reads from Pipe  │
                  └────────────────────┘
```

**Key Design Principle:** Direct pipe-to-PS5 communication path minimizes latency by eliminating intermediate processing layers. Both input sources write independently to the pipe, and pyremoteplay consumes and forwards all commands directly to the PS5.

## Components and Interfaces

### 1. Hardware Producer (Existing - C++ SDL2)

**Status:** ✅ Fully Implemented

**Responsibilities:**
- Capture SDL2 events from DualSense controller
- Capture keyboard events (WASD for D-pad, Q to quit)
- Write button press/release events to Named Pipe
- Write analog stick movements to Named Pipe
- Handle trigger buttons (L2/R2) with threshold detection

**Pipe Protocol (Already Defined):**

Button Events:
```
<BUTTON_NAME>\n
<press|release>\n
\n
```

Analog Events:
```
<LEFT|RIGHT>\n
<x|y>\n
<float_value>\n
```

**Supported Buttons:**
- D-Pad: UP, DOWN, LEFT, RIGHT
- Face Buttons: CROSS, CIRCLE, SQUARE, TRIANGLE
- Shoulder Buttons: L1, R1, L2, R2
- Stick Buttons: L3, R3
- System: OPTIONS, PS

### 2. Vision Sensor (To Be Implemented - Python MediaPipe)

**File Structure:**
```
core/
├── gestures.py      # MediaPipe pose detection and gesture recognition
└── mappings.py      # Configuration for gesture-to-button mappings
```

**Responsibilities:**
- Initialize camera capture (USB or Pi Camera)
- Run MediaPipe Pose estimation on each frame
- Detect configured gestures based on landmark positions
- Calculate movement deltas and compare against thresholds
- Write virtual button events to Named Pipe using same protocol as Hardware Producer
- Expose current pose data for web dashboard visualization

**Key Classes:**

```python
# gestures.py

class GestureDetector:
    """Detects body movements using MediaPipe Pose."""
    
    def __init__(self, camera_index=0):
        self.camera = cv2.VideoCapture(camera_index)
        self.pose = mp.solutions.pose.Pose(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.previous_landmarks = None
        self.thresholds = {
            'delta_threshold': 0.05,  # Speed of movement
            'raise_minimum': 0.1      # Range of movement
        }
    
    def detect_gestures(self, mappings: dict) -> list[tuple[str, str]]:
        """
        Process one frame and return detected gestures.
        Returns: List of (button_name, action) tuples
        """
        pass
    
    def get_current_frame(self) -> np.ndarray:
        """Return current frame with pose overlay for dashboard."""
        pass
    
    def update_thresholds(self, delta: float, raise_min: float):
        """Update detection thresholds in real-time."""
        pass
```

```python
# mappings.py

class GestureMapping:
    """Manages gesture-to-button mappings."""
    
    def __init__(self, config_file='config/mappings.json'):
        self.mappings = self.load_mappings(config_file)
    
    def load_mappings(self, file_path: str) -> dict:
        """Load mappings from JSON file."""
        pass
    
    def save_mappings(self, file_path: str):
        """Persist mappings to JSON file."""
        pass
    
    def add_mapping(self, gesture_name: str, button: str):
        """Add or update a gesture mapping."""
        pass
    
    def get_active_mappings(self) -> dict:
        """Return currently active gesture mappings."""
        pass
```

**Gesture Detection Logic:**

Gestures are defined by landmark movements:
- **Left Elbow Raise**: Left elbow Y-coordinate decreases significantly
- **Right Elbow Raise**: Right elbow Y-coordinate decreases significantly
- **Left Arm Forward**: Left wrist Z-coordinate increases (moves toward camera)
- **Right Arm Forward**: Right wrist Z-coordinate increases
- **Shoulder Shrug**: Both shoulders Y-coordinate decreases

Detection Algorithm:
1. Calculate delta between current and previous landmark positions
2. Check if delta exceeds `delta_threshold` (speed requirement)
3. Check if absolute position exceeds `raise_minimum` (range requirement)
4. If both conditions met, trigger mapped button press
5. When movement stops (delta below threshold), trigger button release

### 3. pyremoteplay Pipe Consumer (To Be Modified)

**File:** `pyremoteplay/__main__.py` (modify existing)

**Responsibilities:**
- Open and continuously read from Named Pipe in a dedicated thread
- Parse incoming messages (button events and analog events)
- Maintain connection to PS5 via existing pyremoteplay Session
- Forward button presses/releases using existing `Controller.button()` API
- Forward analog stick movements using existing `Controller.stick()` API
- Handle connection errors and reconnection logic

**Modification Strategy:**

The existing `pyremoteplay/__main__.py` likely starts a Remote Play session. We need to add a pipe reader thread that runs alongside the session:

```python
# Add to pyremoteplay/__main__.py

import threading
import os

class PipeReader:
    """Reads from Named Pipe and forwards to Controller."""
    
    def __init__(self, controller, pipe_path='/tmp/my_pipe'):
        self.controller = controller
        self.pipe_path = pipe_path
        self.running = False
        self.thread = None
    
    def start(self):
        """Start pipe reader thread."""
        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Stop pipe reader thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
    
    def _read_loop(self):
        """Continuously read from pipe."""
        while self.running:
            try:
                with open(self.pipe_path, 'r') as pipe:
                    while self.running:
                        message = self._parse_message(pipe)
                        if message:
                            self._forward_to_controller(message)
            except Exception as e:
                print(f"Pipe read error: {e}")
                time.sleep(1)  # Wait before retry
    
    def _parse_message(self, pipe) -> dict:
        """Parse pipe message into structured data."""
        try:
            line1 = pipe.readline().strip()
            if not line1:
                return None
            
            line2 = pipe.readline().strip()
            line3 = pipe.readline().strip()
            
            # Check if it's a button message
            if line2 in ['press', 'release']:
                return {
                    'type': 'button',
                    'button': line1,
                    'action': line2
                }
            # Otherwise it's an analog message
            else:
                return {
                    'type': 'analog',
                    'stick': line1,
                    'axis': line2,
                    'value': float(line3)
                }
        except Exception as e:
            print(f"Parse error: {e}")
            return None
    
    def _forward_to_controller(self, message: dict):
        """Send command to PS5 via Controller."""
        try:
            if message['type'] == 'button':
                self.controller.button(
                    message['button'],
                    message['action']
                )
            elif message['type'] == 'analog':
                self.controller.stick(
                    message['stick'],
                    message['axis'],
                    message['value']
                )
        except Exception as e:
            print(f"Controller error: {e}")

# In main() function, after creating controller:
# pipe_reader = PipeReader(controller)
# pipe_reader.start()
```

**Integration Points:**

1. Import PipeReader class in `__main__.py`
2. After establishing Remote Play session and creating Controller
3. Start PipeReader thread before entering main event loop
4. Ensure PipeReader stops gracefully on session end

**Pipe Reading Strategy:**

The pipe protocol has two message formats:

Button Message (3 lines):
```
LINE 1: Button name
LINE 2: "press" or "release"
LINE 3: Empty line (delimiter)
```

Analog Message (3 lines):
```
LINE 1: Stick name ("LEFT" or "RIGHT")
LINE 2: Axis ("x" or "y")
LINE 3: Float value as string
```

Parser reads lines in groups of 3, determines message type by checking if LINE 2 is "press"/"release" or an axis name.

### 4. Web Dashboard (To Be Implemented - Flask)

**File Structure:**
```
web/
├── server.py           # Flask application
├── templates/
│   └── dashboard.html  # Main UI
└── static/
    ├── css/
    │   └── style.css
    └── js/
        └── dashboard.js
```

**Responsibilities:**
- Serve web interface on port 5000
- **Manage PS5 Remote Play connection lifecycle**
- **Handle PSN OAuth authentication flow**
- **Capture redirect URLs and process authentication codes**
- **Provide PIN code input interface**
- **Start/stop pyremoteplay subprocess with authenticated credentials**
- Stream camera feed with pose overlays via WebSocket or MJPEG
- Provide controls for adjusting thresholds
- Display connection status (controller, PS5, camera)
- Allow gesture mapping configuration
- Show real-time landmark positions

**API Endpoints:**

```python
# server.py

@app.route('/')
def dashboard():
    """Serve main dashboard page."""
    pass

@app.route('/api/status')
def get_status():
    """Return system status JSON."""
    return {
        'controller_connected': bool,
        'ps5_connected': bool,
        'camera_active': bool,
        'active_mappings': dict,
        'psn_authenticated': bool
    }

@app.route('/api/psn/login', methods=['POST'])
def psn_login():
    """Initiate PSN OAuth flow."""
    # Start OAuth flow using pyremoteplay.oauth
    # Return authorization URL for user to visit
    pass

@app.route('/api/psn/callback', methods=['POST'])
def psn_callback():
    """Handle OAuth redirect URL."""
    # Extract code from redirect URL
    # Exchange code for tokens
    # Store tokens securely
    pass

@app.route('/api/psn/pin', methods=['POST'])
def submit_pin():
    """Submit Remote Play PIN code."""
    # Use PIN to complete registration
    pass

@app.route('/api/remoteplay/connect', methods=['POST'])
def connect_remoteplay():
    """Start Remote Play session."""
    # Start pyremoteplay subprocess with stored credentials
    # Return connection status
    pass

@app.route('/api/remoteplay/disconnect', methods=['POST'])
def disconnect_remoteplay():
    """Stop Remote Play session."""
    # Terminate pyremoteplay subprocess gracefully
    pass

@app.route('/api/thresholds', methods=['GET', 'POST'])
def thresholds():
    """Get or update detection thresholds."""
    pass

@app.route('/api/mappings', methods=['GET', 'POST', 'DELETE'])
def mappings():
    """Manage gesture mappings."""
    pass

@app.route('/video_feed')
def video_feed():
    """Stream camera feed with pose overlay."""
    # Return MJPEG stream
    pass
```

**Dashboard UI Sections:**

1. **PSN Connection Panel** (NEW)
   - Login button to start OAuth flow
   - Redirect URL input field (for manual paste if needed)
   - PIN code input field
   - Connect/Disconnect buttons
   - Connection status indicator

2. **Status Panel**
   - PSN authentication status
   - PS5 connection indicator
   - Controller connection indicator
   - Camera status indicator
   - Current FPS display

3. **Video Feed**
   - Live camera view with MediaPipe skeleton overlay
   - Highlighted landmarks for active gestures
   - Visual feedback when gesture detected

4. **Threshold Controls**
   - Slider for Delta Threshold (0.01 - 0.5)
   - Slider for Raise Minimum (0.0 - 1.0)
   - Real-time value display
   - Apply button

5. **Gesture Mapping**
   - Dropdown to select gesture type
   - Dropdown to select PS button
   - Add/Remove mapping buttons
   - List of active mappings

**PSN Authentication Flow:**

```python
# Integration with pyremoteplay OAuth

from pyremoteplay.oauth import OAuth
from pyremoteplay.register import register

class PSNConnectionManager:
    """Manages PSN authentication and Remote Play connection."""
    
    def __init__(self):
        self.oauth = OAuth()
        self.tokens = None
        self.remoteplay_process = None
    
    def start_oauth_flow(self) -> str:
        """Return authorization URL for user."""
        return self.oauth.get_authorization_url()
    
    def handle_redirect(self, redirect_url: str):
        """Extract code and exchange for tokens."""
        code = self.oauth.extract_code(redirect_url)
        self.tokens = self.oauth.get_tokens(code)
        # Store tokens in config file
    
    def register_device(self, pin: str):
        """Register device with PS5 using PIN."""
        register(self.tokens, pin)
    
    def start_remoteplay(self, ps5_ip: str):
        """Start pyremoteplay subprocess."""
        self.remoteplay_process = subprocess.Popen([
            'python', '-m', 'pyremoteplay', ps5_ip
        ], env={'PSN_TOKEN': self.tokens})
    
    def stop_remoteplay(self):
        """Stop pyremoteplay subprocess."""
        if self.remoteplay_process:
            self.remoteplay_process.terminate()
            self.remoteplay_process.wait(timeout=5)
```

### 5. Main Orchestrator (To Be Implemented)

**File:** `main.py`

**Responsibilities:**
- Create Named Pipe if it doesn't exist
- Start Hardware Producer as subprocess
- Start Vision Sensor in dedicated thread
- Start Web Dashboard in dedicated thread (which manages pyremoteplay connection)
- Handle graceful shutdown on SIGINT/SIGTERM
- Clean up resources on exit

**Startup Sequence:**

```python
def main():
    # 1. Create named pipe
    if not os.path.exists('/tmp/my_pipe'):
        os.mkfifo('/tmp/my_pipe')
    
    # 2. Start Hardware Producer (subprocess)
    hardware_process = subprocess.Popen([
        './controller/build/detect_controller'
    ])
    
    # 3. Initialize shared state
    gesture_detector = GestureDetector()
    gesture_mappings = GestureMapping()
    
    # 4. Start Vision Sensor (thread)
    vision_thread = threading.Thread(
        target=vision_sensor_loop,
        args=(gesture_detector, gesture_mappings)
    )
    vision_thread.start()
    
    # 5. Start Web Dashboard (thread)
    # Dashboard will handle PSN auth and pyremoteplay connection
    web_thread = threading.Thread(
        target=run_flask_app,
        args=(gesture_detector, gesture_mappings)
    )
    web_thread.start()
    
    # 6. Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
        # Cleanup handled by signal handlers
```

**Note:** The Web Dashboard now manages the pyremoteplay connection lifecycle, including PSN authentication, PIN entry, and starting/stopping the Remote Play session. The main orchestrator simply starts the dashboard and lets it handle PS5 connectivity.

## Data Models

### Configuration File (config/mappings.json)

```json
{
  "thresholds": {
    "delta_threshold": 0.05,
    "raise_minimum": 0.1
  },
  "mappings": {
    "left_elbow_raise": "SQUARE",
    "right_elbow_raise": "CIRCLE",
    "left_arm_forward": "L1",
    "right_arm_forward": "R1"
  }
}
```

### Gesture Detection State

```python
@dataclass
class GestureState:
    """Represents the state of a detected gesture."""
    gesture_name: str
    button: str
    is_active: bool
    confidence: float
    last_triggered: float  # timestamp
```

### System Status

```python
@dataclass
class SystemStatus:
    """Overall system health status."""
    controller_connected: bool
    ps5_connected: bool
    camera_active: bool
    fps: float
    active_gestures: list[str]
    pipe_open: bool
```

## Error Handling

### Hardware Producer Errors
- **Controller Disconnected**: Already handled - logs warning and waits for reconnection
- **Pipe Write Failure**: Should log error but continue running
- **SDL Initialization Failure**: Exit with error code

### Vision Sensor Errors
- **Camera Not Found**: Log error, retry connection every 5 seconds
- **MediaPipe Initialization Failure**: Exit with error message
- **Pipe Write Failure**: Log error, attempt to reopen pipe
- **Low FPS**: Log warning if FPS drops below 15

### pyremoteplay Pipe Reader Errors
- **Pipe Read Failure**: Attempt to reopen pipe, log error
- **PS5 Connection Lost**: Handled by existing pyremoteplay reconnection logic
- **Invalid Message Format**: Log warning, skip message, continue reading
- **Controller API Error**: Log error, continue operation

### Web Dashboard Errors
- **Port Already in Use**: Try alternative ports (5001, 5002, etc.)
- **Camera Access Denied**: Display error message in UI
- **WebSocket Connection Lost**: Attempt automatic reconnection

### Main Orchestrator Errors
- **Hardware Producer Crash**: Log error, attempt restart once
- **Thread Exception**: Log full traceback, attempt thread restart
- **Shutdown Timeout**: Force kill subprocesses after 5 seconds

## Testing Strategy

### Unit Tests

**Vision Sensor Tests:**
- Test gesture detection with mock landmark data
- Test threshold calculations
- Test mapping configuration load/save
- Test pipe message formatting

**pyremoteplay Pipe Reader Tests:**
- Test pipe message parsing
- Test Controller API integration (mocked)
- Test message forwarding accuracy
- Test error handling for malformed messages

**Web Dashboard Tests:**
- Test API endpoints with mock data
- Test threshold update propagation
- Test mapping CRUD operations

### Integration Tests

**Pipe Communication:**
- Test Hardware Producer → pyremoteplay message flow
- Test Vision Sensor → pyremoteplay message flow
- Test concurrent writes from both producers
- Test message ordering and timing

**End-to-End:**
- Test physical button press → PS5 response
- Test gesture detection → PS5 response
- Test simultaneous physical + gesture input
- Test threshold adjustment → detection behavior change

### Performance Tests

**Latency Measurements:**
- Measure Hardware Producer → Pipe → pyremoteplay → PS5 latency
- Measure Vision Sensor frame processing time
- Measure gesture detection → PS5 response time
- Target: < 150ms end-to-end for gestures

**Stress Tests:**
- Test rapid button presses (> 10/second)
- Test continuous analog stick movement
- Test multiple simultaneous gestures
- Test system stability over 1-hour session

### Manual Testing

**Rehabilitation Scenarios:**
- Test with various body types and ranges of motion
- Test threshold tuning for different physical capabilities
- Test gesture mapping customization workflow
- Test system usability for therapists

**Hardware Compatibility:**
- Test on Raspberry Pi 4 (primary target)
- Test with USB cameras and Pi Camera
- Test with different DualSense controller firmware versions
- Test network latency with various PS5 connection qualities

## Security Considerations

- **Network Security**: PS5 Remote Play uses encrypted connection (handled by pyremoteplay)
- **Local Access**: Web dashboard should only bind to localhost or local network
- **Input Validation**: Sanitize all user inputs from web dashboard
- **Resource Limits**: Prevent excessive camera frame processing from consuming all CPU
- **Pipe Permissions**: Named pipe should have appropriate file permissions (0666)

## Performance Optimization

### Vision Sensor Optimizations
- Use MediaPipe's lightweight pose model
- Reduce camera resolution if FPS drops below 30
- Skip frames if processing falls behind
- Use NumPy vectorized operations for landmark calculations

### pyremoteplay Optimizations
- Use non-blocking pipe reads with timeout in reader thread
- Batch multiple messages if pipe has backlog
- Maintain persistent PS5 connection (avoid reconnection overhead)
- Use efficient string parsing (avoid regex)

### Web Dashboard Optimizations
- Limit video stream to 15 FPS (sufficient for monitoring)
- Use MJPEG instead of individual frame requests
- Cache static assets
- Use WebSocket for real-time updates instead of polling

## Deployment Considerations

### Raspberry Pi 4 Setup
- Requires 64-bit Raspberry Pi OS
- Minimum 2GB RAM (4GB recommended)
- USB 3.0 port for camera (better bandwidth)
- Bluetooth enabled for DualSense pairing
- Network connection to PS5 (wired preferred for lower latency)

### Dependencies
- System: SDL2, CMake, Python 3.9+, OpenCV, MediaPipe
- Python: Flask, pyremoteplay, opencv-python, mediapipe, numpy
- Build: GCC/G++ for ARM64

### Installation Script
- Install system dependencies via apt
- Compile Hardware Producer
- Create Python virtual environment
- Install Python dependencies
- Create Named Pipe
- Set up systemd service (optional)

## Future Enhancements

1. **Multiple Camera Support**: Track full body with multiple angles
2. **Gesture Recording**: Allow therapists to record custom gestures
3. **Progress Tracking**: Log movement data for rehabilitation progress analysis
4. **Haptic Feedback**: Use DualSense haptics to provide movement feedback
5. **Voice Commands**: Add voice control for hands-free operation
6. **Cloud Sync**: Sync configurations and progress across devices
7. **Mobile App**: Remote monitoring and configuration via smartphone
