"""
MediaPipe-based gesture detection for rehabilitation gaming.
"""

import cv2
import mediapipe as mp
import numpy as np
from typing import Optional, List, Tuple
import time


class GestureDetector:
    """Detects body movements using MediaPipe Pose."""
    
    def __init__(self, camera_index: int = 0):
        """
        Initialize gesture detector with camera and MediaPipe Pose.
        
        Args:
            camera_index: Camera device index (0 for default USB, or path for Pi Camera)
        """
        # Initialize camera
        self.camera = cv2.VideoCapture(camera_index)
        if not self.camera.isOpened():
            raise RuntimeError(f"Failed to open camera at index {camera_index}")
        
        # Set camera properties for better performance
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.camera.set(cv2.CAP_PROP_FPS, 30)
        
        # Initialize MediaPipe Pose
        self.mp_pose = mp.solutions.pose
        self.mp_drawing = mp.solutions.drawing_utils
        self.pose = self.mp_pose.Pose(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            model_complexity=1  # Balance between accuracy and speed
        )
        
        # State tracking
        self.previous_landmarks = None
        self.current_frame = None
        self.current_landmarks = None
        self.last_frame_time = time.time()
        
        # Detection thresholds
        self.thresholds = {
            'delta_threshold': 0.05,  # Speed of movement
            'raise_minimum': 0.1      # Range of movement
        }
    
    def process_frame(self) -> Optional[mp.solutions.pose.PoseLandmark]:
        """
        Capture and process a single frame from the camera.
        
        Returns:
            Pose landmarks if detected, None otherwise
        """
        ret, frame = self.camera.read()
        if not ret:
            return None
        
        # Store frame for visualization
        self.current_frame = frame.copy()
        
        # Convert BGR to RGB for MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Process with MediaPipe
        results = self.pose.process(rgb_frame)
        
        if results.pose_landmarks:
            self.current_landmarks = results.pose_landmarks
            return results.pose_landmarks
        
        return None
    
    def calculate_landmark_delta(self, landmark_id: int) -> Optional[Tuple[float, float, float]]:
        """
        Calculate the change in position for a specific landmark.
        
        Args:
            landmark_id: MediaPipe landmark ID
            
        Returns:
            Tuple of (delta_x, delta_y, delta_z) or None if no previous landmarks
        """
        if self.previous_landmarks is None or self.current_landmarks is None:
            return None
        
        prev = self.previous_landmarks.landmark[landmark_id]
        curr = self.current_landmarks.landmark[landmark_id]
        
        delta_x = curr.x - prev.x
        delta_y = curr.y - prev.y
        delta_z = curr.z - prev.z
        
        return (delta_x, delta_y, delta_z)
    
    def get_current_frame(self) -> Optional[np.ndarray]:
        """
        Get the current frame with pose overlay for dashboard visualization.
        
        Returns:
            Frame with pose landmarks drawn, or None if no frame available
        """
        if self.current_frame is None:
            return None
        
        # Create a copy to draw on
        annotated_frame = self.current_frame.copy()
        
        # Draw pose landmarks if available
        if self.current_landmarks:
            self.mp_drawing.draw_landmarks(
                annotated_frame,
                self.current_landmarks,
                self.mp_pose.POSE_CONNECTIONS,
                landmark_drawing_spec=self.mp_drawing.DrawingSpec(
                    color=(0, 255, 0), thickness=2, circle_radius=2
                ),
                connection_drawing_spec=self.mp_drawing.DrawingSpec(
                    color=(0, 255, 255), thickness=2
                )
            )
        
        # Add FPS counter
        current_time = time.time()
        fps = 1.0 / (current_time - self.last_frame_time) if self.last_frame_time else 0
        self.last_frame_time = current_time
        
        cv2.putText(
            annotated_frame,
            f"FPS: {fps:.1f}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2
        )
        
        return annotated_frame
    
    def update_thresholds(self, delta: float, raise_min: float):
        """
        Update detection thresholds in real-time.
        
        Args:
            delta: New delta_threshold value (speed of movement)
            raise_min: New raise_minimum value (range of movement)
        """
        self.thresholds['delta_threshold'] = delta
        self.thresholds['raise_minimum'] = raise_min
    
    def get_thresholds(self) -> dict:
        """
        Get current detection thresholds.
        
        Returns:
            Dictionary of threshold values
        """
        return self.thresholds.copy()
    
    def is_active(self) -> bool:
        """
        Check if camera is active and capturing frames.
        
        Returns:
            True if camera is open and ready
        """
        return self.camera is not None and self.camera.isOpened()
    
    def get_fps(self) -> float:
        """
        Get current FPS estimate.
        
        Returns:
            Frames per second
        """
        current_time = time.time()
        elapsed = current_time - self.last_frame_time
        return 1.0 / elapsed if elapsed > 0 else 0.0
    
    def detect_gestures(self, mappings: dict) -> List[Tuple[str, str]]:
        """
        Process one frame and detect configured gestures.
        
        Args:
            mappings: Dictionary mapping gesture names to button names
            
        Returns:
            List of (button_name, action) tuples where action is 'press' or 'release'
        """
        detected_events = []
        
        # Process current frame
        landmarks = self.process_frame()
        if landmarks is None:
            return detected_events
        
        # MediaPipe landmark indices
        LEFT_ELBOW = self.mp_pose.PoseLandmark.LEFT_ELBOW.value
        RIGHT_ELBOW = self.mp_pose.PoseLandmark.RIGHT_ELBOW.value
        LEFT_WRIST = self.mp_pose.PoseLandmark.LEFT_WRIST.value
        RIGHT_WRIST = self.mp_pose.PoseLandmark.RIGHT_WRIST.value
        LEFT_SHOULDER = self.mp_pose.PoseLandmark.LEFT_SHOULDER.value
        RIGHT_SHOULDER = self.mp_pose.PoseLandmark.RIGHT_SHOULDER.value
        
        # Check each configured gesture
        for gesture_name, button_name in mappings.items():
            gesture_detected = False
            
            if gesture_name == "left_elbow_raise":
                gesture_detected = self._check_elbow_raise(LEFT_ELBOW, LEFT_SHOULDER)
            
            elif gesture_name == "right_elbow_raise":
                gesture_detected = self._check_elbow_raise(RIGHT_ELBOW, RIGHT_SHOULDER)
            
            elif gesture_name == "left_arm_forward":
                gesture_detected = self._check_arm_forward(LEFT_WRIST)
            
            elif gesture_name == "right_arm_forward":
                gesture_detected = self._check_arm_forward(RIGHT_WRIST)
            
            # Generate press/release events based on detection
            if gesture_detected:
                detected_events.append((button_name, 'press'))
            else:
                detected_events.append((button_name, 'release'))
        
        # Update previous landmarks for next frame
        self.previous_landmarks = self.current_landmarks
        
        return detected_events
    
    def _check_elbow_raise(self, elbow_id: int, shoulder_id: int) -> bool:
        """
        Check if elbow is raised above shoulder.
        
        Args:
            elbow_id: MediaPipe landmark ID for elbow
            shoulder_id: MediaPipe landmark ID for shoulder
            
        Returns:
            True if gesture detected
        """
        if self.current_landmarks is None:
            return False
        
        elbow = self.current_landmarks.landmark[elbow_id]
        shoulder = self.current_landmarks.landmark[shoulder_id]
        
        # Check if elbow is raised (Y decreases upward in image coordinates)
        vertical_diff = shoulder.y - elbow.y
        
        # Check delta if we have previous frame
        if self.previous_landmarks is not None:
            delta = self.calculate_landmark_delta(elbow_id)
            if delta:
                delta_y = abs(delta[1])
                # Must meet both speed and range requirements
                return (delta_y > self.thresholds['delta_threshold'] and 
                        vertical_diff > self.thresholds['raise_minimum'])
        
        # If no previous frame, just check position
        return vertical_diff > self.thresholds['raise_minimum']
    
    def _check_arm_forward(self, wrist_id: int) -> bool:
        """
        Check if arm is extended forward toward camera.
        
        Args:
            wrist_id: MediaPipe landmark ID for wrist
            
        Returns:
            True if gesture detected
        """
        if self.current_landmarks is None or self.previous_landmarks is None:
            return False
        
        # Check Z-axis movement (toward camera is positive)
        delta = self.calculate_landmark_delta(wrist_id)
        if delta is None:
            return False
        
        delta_z = delta[2]
        
        # Check if moving forward with sufficient speed
        return delta_z > self.thresholds['delta_threshold']
    
    def cleanup(self):
        """Release camera and MediaPipe resources."""
        if self.camera:
            self.camera.release()
        if self.pose:
            self.pose.close()
    
    def __del__(self):
        """Ensure cleanup on deletion."""
        self.cleanup()
