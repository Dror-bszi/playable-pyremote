# Requirements Document

## Introduction

PlayAble is a hybrid gesture-to-game control system designed for physical rehabilitation. The system enables specific PlayStation buttons to be triggered by body movements detected via computer vision while maintaining full functionality of a physical PS5 DualSense controller. The primary goal is to help rehabilitation patients reconnect through gaming and movement by combining traditional controller input with therapeutic body movements.

**Current Implementation Status:**
- Hardware Producer (C++ SDL2): ✅ Implemented - captures DualSense controller and keyboard inputs, writes to Named Pipe
- Remote Play Client (pyremoteplay): ✅ Available - Python library for PS5 Remote Play communication
- Vision Sensor (MediaPipe): ❌ Not implemented - needs gesture detection and pipe integration
- Web Dashboard (Flask): ❌ Not implemented - needs monitoring and configuration interface
- Main Orchestrator: ❌ Not implemented - needs to coordinate all components

## Glossary

- **PlayAble System**: The complete rehabilitation gaming system including all components
- **Hardware Producer**: The C++ SDL2 component that captures real-time interrupts from the DualSense controller or keyboard
- **Vision Sensor**: The Python MediaPipe component that processes camera frames to detect gestures
- **Central Hub**: The Python Remote Play component that consumes combined data and transmits commands to the PS5
- **Named Pipe**: A Linux inter-process communication mechanism used for streaming data between components
- **DualSense Controller**: Sony's PlayStation 5 wireless controller
- **MediaPipe**: Google's framework for building multimodal machine learning pipelines
- **Remote Play**: Sony's technology for streaming PlayStation games over a network
- **Gesture Mapping**: The configuration that associates specific body movements with PlayStation button presses
- **Delta Threshold**: The speed of movement required to trigger a gesture detection
- **Raise Minimum**: The range of movement required to trigger a gesture detection
- **Web Dashboard**: The Flask-based web interface for monitoring and configuration
- **Main Orchestrator**: The Python component that coordinates startup and shutdown of all system components
- **Installation Script**: The automated setup script that configures the PlayAble System on new hardware

## Requirements

### Requirement 1

**User Story:** As a rehabilitation patient, I want to trigger PlayStation buttons using body movements, so that I can engage in therapeutic gaming exercises

#### Acceptance Criteria

1. WHEN THE Vision Sensor detects a configured body movement, THE Central Hub SHALL transmit the corresponding button press to the PS5 within 100 milliseconds
2. WHILE a gesture is being performed, THE Vision Sensor SHALL continuously evaluate movement against configured thresholds
3. THE Vision Sensor SHALL support detection of elbow raises, arm extensions, and shoulder movements
4. WHERE a gesture mapping is configured, THE Central Hub SHALL inject the virtual button press into the command stream
5. THE System SHALL process camera frames at a minimum rate of 30 frames per second

### Requirement 2

**User Story:** As a rehabilitation patient, I want to use my physical DualSense controller simultaneously with gesture controls, so that I can maintain familiar gaming interactions while performing therapeutic movements

#### Acceptance Criteria

1. THE Hardware Producer SHALL capture all physical button presses from the DualSense controller with zero added latency
2. WHEN a physical button press occurs, THE Hardware Producer SHALL stream the interrupt data to the Named Pipe within 10 milliseconds
3. THE Central Hub SHALL merge physical controller inputs and gesture-triggered inputs into a single command stream
4. THE System SHALL maintain the original timing and sequence of all physical controller inputs
5. WHILE both physical and gesture inputs are active, THE Central Hub SHALL prioritize physical inputs when conflicts occur

### Requirement 3

**User Story:** As a therapist, I want to adjust movement sensitivity thresholds in real-time, so that I can customize the system to each patient's physical capabilities

#### Acceptance Criteria

1. THE Web Dashboard SHALL provide controls for adjusting Delta Threshold values between 0.1 and 2.0
2. THE Web Dashboard SHALL provide controls for adjusting Raise Minimum values between 0.0 and 1.0
3. WHEN a threshold value is changed, THE Vision Sensor SHALL apply the new value within 1 second
4. THE System SHALL persist threshold configurations across restarts
5. THE Web Dashboard SHALL display the current threshold values at all times

### Requirement 4

**User Story:** As a therapist, I want to map specific body movements to PlayStation buttons, so that I can design custom therapeutic gaming exercises

#### Acceptance Criteria

1. THE Web Dashboard SHALL provide an interface for assigning body movements to PlayStation buttons
2. THE System SHALL support mapping for CROSS, CIRCLE, SQUARE, TRIANGLE, R1, R2, L1, and L2 buttons
3. WHEN a gesture mapping is created, THE Vision Sensor SHALL begin detecting that movement pattern
4. THE System SHALL allow multiple gestures to be mapped to different buttons simultaneously
5. THE System SHALL persist gesture mappings across restarts

### Requirement 5

**User Story:** As a therapist, I want to monitor the patient's movements and system status through a web interface, so that I can ensure the system is functioning correctly during therapy sessions

#### Acceptance Criteria

1. THE Web Dashboard SHALL display a live camera feed with MediaPipe pose estimation overlays
2. THE Web Dashboard SHALL update the camera feed at a minimum rate of 15 frames per second
3. THE Web Dashboard SHALL display the connection status of the DualSense controller
4. THE Web Dashboard SHALL display the connection status of the PS5 Remote Play session
5. THE Web Dashboard SHALL display the current active gesture mappings

### Requirement 5.1

**User Story:** As a therapist, I want to manage the PS5 Remote Play connection through the web dashboard, so that I can easily set up and maintain the connection without using command-line tools

#### Acceptance Criteria

1. THE Web Dashboard SHALL provide a form for entering PSN account credentials
2. THE Web Dashboard SHALL handle the OAuth authentication flow with PlayStation Network
3. WHEN a redirect URL is received from PSN, THE Web Dashboard SHALL capture and process the authentication code
4. THE Web Dashboard SHALL provide an input field for entering the Remote Play PIN code
5. WHEN the PS5 connection is established, THE Web Dashboard SHALL display a success indicator
6. THE Web Dashboard SHALL allow disconnecting and reconnecting to the PS5
7. THE Web Dashboard SHALL persist authentication tokens for automatic reconnection

### Requirement 6

**User Story:** As a system administrator, I want the system to run on a Raspberry Pi 4, so that the solution is affordable and portable for rehabilitation facilities

#### Acceptance Criteria

1. THE System SHALL operate on a Raspberry Pi 4 with 64-bit Raspberry Pi OS
2. THE System SHALL support USB cameras and Pi Camera modules
3. THE System SHALL establish Bluetooth connectivity with the DualSense controller
4. THE System SHALL communicate with the PS5 over a local network connection
5. THE Hardware Producer SHALL compile and execute on ARM64 architecture

### Requirement 7

**User Story:** As a rehabilitation patient, I want the system to respond to my movements with minimal delay, so that gaming feels natural and responsive

#### Acceptance Criteria

1. THE System SHALL maintain end-to-end latency from gesture detection to PS5 command transmission below 150 milliseconds
2. THE Hardware Producer SHALL process physical controller inputs with zero added latency beyond hardware limitations
3. THE Vision Sensor SHALL process each camera frame within 30 milliseconds
4. THE Named Pipe SHALL transfer data between components with latency below 5 milliseconds
5. THE Central Hub SHALL transmit commands to the PS5 within 20 milliseconds of receiving them

### Requirement 8

**User Story:** As a system administrator, I want an automated installation process, so that I can quickly deploy the system on new hardware

#### Acceptance Criteria

1. THE installation script SHALL install all required system dependencies
2. THE installation script SHALL compile the Hardware Producer binary
3. THE installation script SHALL install all Python dependencies from requirements.txt
4. THE installation script SHALL configure the Named Pipe for inter-process communication
5. THE installation script SHALL complete successfully on a fresh Raspberry Pi OS installation

### Requirement 9

**User Story:** As a rehabilitation patient, I want the system to start with a single command, so that I can begin my therapy session quickly

#### Acceptance Criteria

1. THE main orchestrator SHALL start the Hardware Producer process
2. THE main orchestrator SHALL start the Vision Sensor process
3. THE main orchestrator SHALL start the Central Hub process
4. THE main orchestrator SHALL start the Web Dashboard server
5. WHEN any component fails to start, THE main orchestrator SHALL log the error and terminate all processes

### Requirement 10

**User Story:** As a therapist, I want the system to provide visual feedback on detected movements, so that I can verify the patient is performing exercises correctly

#### Acceptance Criteria

1. THE Web Dashboard SHALL overlay skeletal tracking points on the live camera feed
2. THE Web Dashboard SHALL highlight body parts involved in configured gestures
3. WHEN a gesture is successfully detected, THE Web Dashboard SHALL display a visual indicator
4. THE Web Dashboard SHALL display the current position values for tracked body parts
5. THE Web Dashboard SHALL update visual feedback in real-time with the camera feed

### Requirement 11

**User Story:** As a system administrator, I want the Raspberry Pi to automatically become a WiFi hotspot when no known networks are available, so that I can configure network credentials without needing a wired connection or display

#### Acceptance Criteria

1. WHEN the Raspberry Pi boots and cannot connect to any known WiFi network, THE System SHALL automatically create a WiFi hotspot
2. THE WiFi hotspot SHALL have a recognizable SSID (e.g., "PlayAble-Setup-XXXX" where XXXX is a unique identifier)
3. THE WiFi hotspot SHALL be secured with a default password documented in the installation guide
4. WHEN a user connects to the hotspot, THE Web Dashboard SHALL be accessible at a known IP address (e.g., 192.168.4.1)
5. THE Web Dashboard SHALL provide a network configuration page for entering WiFi credentials
6. WHEN valid WiFi credentials are submitted, THE System SHALL attempt to connect to the specified network
7. WHEN the connection to the new WiFi network is successful, THE System SHALL disable the hotspot and operate in normal mode
8. THE System SHALL automatically retry the hotspot mode if the configured WiFi network becomes unavailable
