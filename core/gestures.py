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
        # Use model_complexity=0 for better performance on Raspberry Pi
        # 0 = fastest, 1 = balanced, 2 = most accurate
        self.mp_pose = mp.solutions.pose
        self.mp_drawing = mp.solutions.drawing_utils
        self.pose = self.mp_pose.Pose(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            model_complexity=0  # Use 0 for better performance on Raspberry Pi
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
        
        If no frame has been processed yet, reads a fresh frame from the camera.
        
        Returns:
            Frame with pose landmarks drawn, or None if camera is not available
        """
        # If no frame has been processed yet, try to read one directly from camera
        if self.current_frame is None:
            if not self.camera or not self.camera.isOpened():
                return None
            # Read a fresh frame for the web feed
            ret, frame = self.camera.read()
            if not ret or frame is None:
                return None
            # Process it to get landmarks (but don't update previous_landmarks to avoid affecting gesture detection)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.pose.process(rgb_frame)
            frame_to_use = frame.copy()
            landmarks_to_use = results.pose_landmarks if results.pose_landmarks else None
        else:
            frame_to_use = self.current_frame.copy()
            landmarks_to_use = self.current_landmarks
        
        # Create a copy to draw on
        annotated_frame = frame_to_use.copy()
        
        # Draw pose landmarks if available
        if landmarks_to_use:
            self.mp_drawing.draw_landmarks(
                annotated_frame,
                landmarks_to_use,
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
            # No pose detected - this is normal if person not in frame
            # Log occasionally to help debugging
            if not hasattr(self, '_pose_detection_counter'):
                self._pose_detection_counter = 0
            self._pose_detection_counter += 1
            if self._pose_detection_counter % 150 == 0:  # Log every 150 frames (~1 minute at 2.5 FPS)
                import logging
                logger = logging.getLogger(__name__)
                logger.debug("No pose detected in frame - make sure you're visible to the camera")
            return detected_events
        
        # Reset counter when pose is detected
        if hasattr(self, '_pose_detection_counter'):
            if self._pose_detection_counter > 0:
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(f"Pose detected! (after {self._pose_detection_counter} frames without detection)")
            self._pose_detection_counter = 0
        
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
        # Positive vertical_diff means elbow is above shoulder
        vertical_diff = shoulder.y - elbow.y
        
        # Check if elbow is currently raised (position check)
        is_raised = vertical_diff > self.thresholds['raise_minimum']
        
        # If we have previous frame, also check for upward movement
        if self.previous_landmarks is not None:
            delta = self.calculate_landmark_delta(elbow_id)
            if delta:
                # delta[1] is negative when moving upward (Y decreases upward)
                # So we want delta_y to be negative (moving up) OR already raised
                delta_y = delta[1]  # Keep sign - negative means moving up
                
                # Check if moving upward (negative delta_y) with sufficient speed
                moving_up = delta_y < -self.thresholds['delta_threshold']
                
                # Gesture detected if:
                # 1. Elbow is currently raised above threshold, OR
                # 2. Elbow is moving upward with sufficient speed
                detected = is_raised or (moving_up and vertical_diff > 0)
                
                # Log diagnostic info occasionally (every 50 frames to help debugging)
                if hasattr(self, '_debug_counter'):
                    self._debug_counter += 1
                else:
                    self._debug_counter = 0
                
                if self._debug_counter % 50 == 0:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info(
                        f"Elbow raise: vertical_diff={vertical_diff:.3f} "
                        f"(min={self.thresholds['raise_minimum']:.3f}), "
                        f"delta_y={delta_y:.3f} (threshold={self.thresholds['delta_threshold']:.3f}), "
                        f"is_raised={is_raised}, moving_up={moving_up}, detected={detected}"
                    )
                
                return detected
        
        # If no previous frame, just check if currently raised
        # Log first check to help debugging
        if not hasattr(self, '_first_check_logged'):
            import logging
            logger = logging.getLogger(__name__)
            logger.info(
                f"Elbow raise (no previous frame): vertical_diff={vertical_diff:.3f} "
                f"(threshold={self.thresholds['raise_minimum']:.3f}), detected={is_raised}"
            )
            self._first_check_logged = True
        
        return is_raised
    
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
        if hasattr(self, 'camera') and self.camera:
            self.camera.release()
        if hasattr(self, 'pose') and self.pose:
            self.pose.close()
    
    def __del__(self):
        """Ensure cleanup on deletion."""
        self.cleanup()
