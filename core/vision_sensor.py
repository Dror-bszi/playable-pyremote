"""
Vision Sensor: MediaPipe gesture detection with Named Pipe output.

This module processes camera frames to detect body movements and writes
button events to a Named Pipe for consumption by pyremoteplay.
"""

import os
import time
import logging
from typing import Dict, Set, Optional
from core.gestures import GestureDetector
from core.mappings import GestureMapping


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VisionSensor:
    """Main vision sensor that detects gestures and writes to Named Pipe."""
    
    def __init__(self, pipe_path: str = '/tmp/my_pipe', camera_index: int = 0):
        """
        Initialize Vision Sensor.
        
        Args:
            pipe_path: Path to Named Pipe for writing button events
            camera_index: Camera device index
        """
        self.pipe_path = pipe_path
        self.camera_index = camera_index
        
        # Initialize gesture detection components
        self.gesture_detector = None
        self.gesture_mapping = None
        
        # Track active gesture states to send press/release only on state changes
        self.active_gestures: Set[str] = set()
        
        # Performance monitoring
        self.frame_count = 0
        self.start_time = time.time()
        self.last_fps_log = time.time()
        
        # Pipe file handle
        self.pipe = None
        
        # Running state
        self.running = False
    
    def initialize(self):
        """Initialize gesture detector and mapping configuration with retry logic."""
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Initializing GestureDetector (attempt {attempt + 1}/{max_retries})...")
                self.gesture_detector = GestureDetector(camera_index=self.camera_index)
                
                logger.info("Loading GestureMapping configuration...")
                self.gesture_mapping = GestureMapping()
                
                # Apply thresholds from configuration
                thresholds = self.gesture_mapping.get_thresholds()
                self.gesture_detector.update_thresholds(
                    thresholds['delta_threshold'],
                    thresholds['raise_minimum']
                )
                
                logger.info("Vision Sensor initialized successfully")
                logger.info(f"Active mappings: {self.gesture_mapping.get_active_mappings()}")
                logger.info(f"Thresholds: {thresholds}")
                return
                
            except RuntimeError as e:
                # Camera not found error
                logger.error(f"Camera initialization failed: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error("Failed to initialize camera after all retries")
                    raise RuntimeError(
                        f"Camera not found at index {self.camera_index}. "
                        "Please check camera connection and permissions."
                    )
            except ImportError as e:
                # MediaPipe initialization failure
                logger.error(f"MediaPipe initialization failed: {e}")
                logger.error("Please ensure MediaPipe is installed: pip install mediapipe")
                raise
            except Exception as e:
                logger.error(f"Failed to initialize Vision Sensor: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    raise
    
    def open_pipe(self):
        """Open Named Pipe for writing with retry logic."""
        max_retries = 5
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Opening Named Pipe: {self.pipe_path} (attempt {attempt + 1}/{max_retries})")
                
                # Check if pipe exists
                if not os.path.exists(self.pipe_path):
                    raise FileNotFoundError(f"Named Pipe not found: {self.pipe_path}")
                
                # Open pipe in write mode (blocking until reader connects)
                self.pipe = open(self.pipe_path, 'w')
                
                logger.info("Named Pipe opened successfully")
                return
                
            except FileNotFoundError:
                logger.error(f"Named Pipe not found: {self.pipe_path}")
                if attempt < max_retries - 1:
                    logger.info(f"Waiting for pipe to be created... Retrying in {retry_delay} seconds")
                    time.sleep(retry_delay)
                else:
                    logger.error("Please ensure the pipe is created before starting Vision Sensor")
                    raise
            except BrokenPipeError:
                logger.warning("Pipe reader not ready yet")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error("Failed to connect to pipe reader")
                    raise
            except Exception as e:
                logger.error(f"Failed to open Named Pipe: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    raise
    
    def write_button_event(self, button_name: str, action: str) -> bool:
        """
        Write button event to Named Pipe following Hardware Producer protocol.
        
        Protocol format:
            LINE 1: BUTTON_NAME
            LINE 2: press|release
            LINE 3: (empty line)
        
        Args:
            button_name: PlayStation button name (e.g., 'SQUARE', 'CIRCLE')
            action: 'press' or 'release'
            
        Returns:
            True if write successful, False otherwise
        """
        if self.pipe is None:
            logger.warning("Pipe not open, cannot write event")
            return False
        
        try:
            # Format message according to protocol
            message = f"{button_name}\n{action}\n\n"
            
            # Write to pipe
            self.pipe.write(message)
            self.pipe.flush()  # Ensure immediate delivery
            
            logger.debug(f"Wrote event: {button_name} {action}")
            return True
            
        except BrokenPipeError:
            logger.error("Broken pipe - reader may have disconnected")
            # Attempt to reopen pipe
            try:
                logger.info("Attempting to reopen pipe...")
                self.pipe.close()
                self.pipe = None
                self.open_pipe()
                # Retry write after reopening
                self.pipe.write(message)
                self.pipe.flush()
                logger.info("Pipe reopened and write successful")
                return True
            except Exception as reopen_error:
                logger.error(f"Failed to reopen pipe: {reopen_error}")
                return False
        except IOError as e:
            logger.error(f"IO error writing to pipe: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to write to pipe: {e}")
            return False
    
    def write_button_event_with_retry(self, button_name: str, action: str, 
                                     max_retries: int = 3) -> bool:
        """
        Write button event with retry logic.
        
        Args:
            button_name: PlayStation button name
            action: 'press' or 'release'
            max_retries: Maximum number of retry attempts
            
        Returns:
            True if write successful, False otherwise
        """
        for attempt in range(max_retries):
            if self.write_button_event(button_name, action):
                return True
            
            if attempt < max_retries - 1:
                logger.warning(f"Retry {attempt + 1}/{max_retries} for {button_name} {action}")
                time.sleep(0.01)  # Brief delay before retry
        
        logger.error(f"Failed to write event after {max_retries} attempts: {button_name} {action}")
        return False
    
    def process_gesture_events(self, detected_events: list):
        """
        Process detected gesture events and send press/release only on state changes.
        
        Args:
            detected_events: List of (button_name, action) tuples from gesture detector
        """
        # Track which buttons are currently active in this frame
        current_active = set()
        
        for button_name, action in detected_events:
            if action == 'press':
                current_active.add(button_name)
                
                # Only send press if this is a new activation
                if button_name not in self.active_gestures:
                    self.write_button_event_with_retry(button_name, 'press')
                    logger.info(f"Gesture activated: {button_name}")
        
        # Check for gestures that were active but are no longer detected
        for button_name in self.active_gestures:
            if button_name not in current_active:
                self.write_button_event_with_retry(button_name, 'release')
                logger.info(f"Gesture deactivated: {button_name}")
        
        # Update active gesture state
        self.active_gestures = current_active
    
    def log_fps(self):
        """Log FPS statistics periodically with warnings for low performance."""
        current_time = time.time()
        
        # Log every 5 seconds
        if current_time - self.last_fps_log >= 5.0:
            elapsed = current_time - self.start_time
            fps = self.frame_count / elapsed if elapsed > 0 else 0
            
            logger.info(f"FPS: {fps:.1f} | Frames processed: {self.frame_count}")
            
            # Warn if FPS is too low
            if fps < 15:
                logger.warning(
                    f"Low FPS detected: {fps:.1f} (target: 30+). "
                    "Consider reducing camera resolution or closing other applications."
                )
            elif fps < 25:
                logger.warning(
                    f"FPS below target: {fps:.1f} (target: 30+). "
                    "Performance may be degraded."
                )
            
            self.last_fps_log = current_time
    
    def run(self):
        """
        Main loop: process frames at 30+ FPS and detect gestures.
        
        This is the core processing loop that:
        1. Captures camera frames
        2. Detects gestures using MediaPipe
        3. Tracks gesture state changes
        4. Writes button events to Named Pipe
        5. Monitors performance
        """
        logger.info("Starting Vision Sensor main loop...")
        self.running = True
        
        try:
            # Initialize components
            self.initialize()
            
            # Open Named Pipe
            self.open_pipe()
            
            # Get active mappings
            mappings = self.gesture_mapping.get_active_mappings()
            
            if not mappings:
                logger.warning("No gesture mappings configured - no gestures will be detected")
            
            # Main processing loop
            logger.info("Vision Sensor running - processing frames...")
            
            while self.running:
                loop_start = time.time()
                
                # Detect gestures in current frame
                detected_events = self.gesture_detector.detect_gestures(mappings)
                
                # Process events and send state changes to pipe
                self.process_gesture_events(detected_events)
                
                # Update frame count
                self.frame_count += 1
                
                # Log FPS periodically
                self.log_fps()
                
                # Calculate frame processing time
                loop_time = time.time() - loop_start
                
                # Target 30 FPS = 33.3ms per frame
                target_frame_time = 1.0 / 30.0
                sleep_time = target_frame_time - loop_time
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
                elif loop_time > target_frame_time * 1.5:
                    # Warn if processing is significantly slower than target
                    logger.warning(
                        f"Frame processing slow: {loop_time*1000:.1f}ms "
                        f"(target: {target_frame_time*1000:.1f}ms)"
                    )
        
        except KeyboardInterrupt:
            logger.info("Vision Sensor interrupted by user")
        
        except Exception as e:
            logger.error(f"Vision Sensor error: {e}", exc_info=True)
            raise
        
        finally:
            self.cleanup()
    
    def stop(self):
        """Stop the vision sensor loop."""
        logger.info("Stopping Vision Sensor...")
        self.running = False
    
    def cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up Vision Sensor resources...")
        
        # Release all active gestures
        for button_name in self.active_gestures:
            self.write_button_event(button_name, 'release')
        
        # Close pipe
        if self.pipe:
            try:
                self.pipe.close()
                logger.info("Named Pipe closed")
            except Exception as e:
                logger.error(f"Error closing pipe: {e}")
        
        # Cleanup gesture detector
        if self.gesture_detector:
            try:
                self.gesture_detector.cleanup()
                logger.info("GestureDetector cleaned up")
            except Exception as e:
                logger.error(f"Error cleaning up GestureDetector: {e}")
        
        logger.info("Vision Sensor cleanup complete")


def main():
    """Entry point for running Vision Sensor standalone."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Vision Sensor for gesture detection')
    parser.add_argument(
        '--pipe',
        default='/tmp/my_pipe',
        help='Path to Named Pipe (default: /tmp/my_pipe)'
    )
    parser.add_argument(
        '--camera',
        type=int,
        default=0,
        help='Camera device index (default: 0)'
    )
    
    args = parser.parse_args()
    
    # Create and run vision sensor
    sensor = VisionSensor(pipe_path=args.pipe, camera_index=args.camera)
    
    try:
        sensor.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        sensor.stop()


if __name__ == '__main__':
    main()
