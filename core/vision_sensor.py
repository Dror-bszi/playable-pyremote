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


# Configure logging (if not already configured by main)
# Only configure if root logger has no handlers
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
logger = logging.getLogger(__name__)


class VisionSensor:
    """Main vision sensor that detects gestures and writes to Named Pipe."""
    
    def __init__(self, pipe_path: str = '/tmp/my_pipe', camera_index: int = 0,
                 gesture_detector: Optional[GestureDetector] = None,
                 gesture_mapping: Optional[GestureMapping] = None):
        """
        Initialize Vision Sensor.
        
        Args:
            pipe_path: Path to Named Pipe for writing button events
            camera_index: Camera device index (only used if gesture_detector not provided)
            gesture_detector: Shared GestureDetector instance (optional, creates new if None)
            gesture_mapping: Shared GestureMapping instance (optional, creates new if None)
        """
        self.pipe_path = pipe_path
        self.camera_index = camera_index
        
        # Initialize gesture detection components
        self.gesture_detector = gesture_detector
        self.gesture_mapping = gesture_mapping
        
        # Track active gesture states to send press/release only on state changes
        self.active_gestures: Set[str] = set()
        
        # Performance monitoring
        self.frame_count = 0
        self.start_time = time.time()
        self.last_fps_log = time.time()
        
        # Slow frame tracking (for aggregated warnings)
        self.slow_frame_count = 0
        self.slow_frame_times = []
        self.last_slow_frame_log = time.time()
        self.slow_frame_log_interval = 10.0  # Log summary every 10 seconds
        
        # Pipe file handle
        self.pipe = None
        
        # Pipe retry tracking (for periodic reconnection attempts)
        self.last_pipe_retry = time.time()
        self.pipe_retry_interval = 5.0  # Retry opening pipe every 5 seconds if not connected
        
        # Running state
        self.running = False
        
        # Camera availability flag
        self.camera_available = False
    
    def initialize(self):
        """Initialize gesture detector and mapping configuration with retry logic."""
        # If gesture_detector and gesture_mapping are already provided, use them
        if self.gesture_detector is not None and self.gesture_mapping is not None:
            logger.info("Using provided GestureDetector and GestureMapping...")
            # Verify camera is accessible
            if self.gesture_detector.is_active():
                logger.info("Vision Sensor initialized successfully (using shared instances)")
                logger.info(f"Active mappings: {self.gesture_mapping.get_active_mappings()}")
                thresholds = self.gesture_mapping.get_thresholds()
                logger.info(f"Thresholds: {thresholds}")
                self.camera_available = True
                return
            else:
                logger.warning("Provided GestureDetector camera is not active")
                self.camera_available = False
                return
        
        # Otherwise, create new instances (for standalone operation)
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
                self.camera_available = True
                return
                
            except RuntimeError as e:
                # Camera not found error
                logger.error(f"Camera initialization failed: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error("Failed to initialize camera after all retries")
                    logger.warning(
                        f"Camera not available at index {self.camera_index}. "
                        "Vision Sensor will continue running without gesture detection. "
                        "Please connect a camera and restart to enable gesture detection."
                    )
                    self.camera_available = False
                    # Still initialize gesture_mapping even without camera
                    if self.gesture_mapping is None:
                        logger.info("Loading GestureMapping configuration...")
                        self.gesture_mapping = GestureMapping()
                    return
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
    
    def open_pipe(self, verbose=True):
        """
        Open Named Pipe for writing with retry logic and non-blocking mode.
        
        Args:
            verbose: If False, reduce logging verbosity (for periodic retries)
        """
        max_retries = 5
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                if verbose or attempt == 0:
                    logger.info(f"Opening Named Pipe: {self.pipe_path} (attempt {attempt + 1}/{max_retries})")
                
                # Check if pipe exists
                if not os.path.exists(self.pipe_path):
                    raise FileNotFoundError(f"Named Pipe not found: {self.pipe_path}")
                
                # Open pipe in non-blocking mode to avoid hanging
                import fcntl
                fd = os.open(self.pipe_path, os.O_WRONLY | os.O_NONBLOCK)
                # Convert to blocking mode after successful open
                fcntl.fcntl(fd, fcntl.F_SETFL, fcntl.fcntl(fd, fcntl.F_GETFL) & ~os.O_NONBLOCK)
                self.pipe = os.fdopen(fd, 'w')
                
                logger.info("Named Pipe opened successfully")
                return
                
            except FileNotFoundError:
                logger.error(f"Named Pipe not found: {self.pipe_path}")
                if attempt < max_retries - 1:
                    logger.info(f"Waiting for pipe to be created... Retrying in {retry_delay} seconds")
                    time.sleep(retry_delay)
                else:
                    logger.warning("Named Pipe not found - Vision Sensor will continue without pipe output")
                    self.pipe = None
                    return
            except (OSError, BlockingIOError) as e:
                # Pipe reader not ready (EAGAIN/EWOULDBLOCK)
                if attempt < max_retries - 1:
                    logger.warning(f"Pipe reader not ready yet: {e}")
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.warning("Failed to connect to pipe reader - Vision Sensor will continue without pipe output")
                    self.pipe = None
                    return
            except Exception as e:
                logger.error(f"Failed to open Named Pipe: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.warning("Could not open Named Pipe - Vision Sensor will continue without pipe output")
                    self.pipe = None
                    return
    
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
            else:
                logger.info(f"Active gesture mappings: {mappings}")
                logger.info(f"Detection thresholds: {self.gesture_mapping.get_thresholds()}")
            
            # Main processing loop
            if self.camera_available:
                logger.info("Vision Sensor running - processing frames...")
            else:
                logger.info("Vision Sensor running - camera unavailable, gesture detection disabled")
            
            while self.running:
                loop_start = time.time()
                
                # Periodically retry opening pipe if not connected
                # This allows reconnection after Remote Play/PipeReader starts
                if self.pipe is None:
                    current_time = time.time()
                    if current_time - self.last_pipe_retry >= self.pipe_retry_interval:
                        # Use verbose=False to reduce log spam during periodic retries
                        # Only log on first retry attempt
                        if not hasattr(self, '_pipe_retry_count'):
                            self._pipe_retry_count = 0
                        self._pipe_retry_count += 1
                        
                        if self._pipe_retry_count == 1:
                            logger.info("Pipe not connected, attempting periodic reconnection...")
                        else:
                            logger.debug(f"Retrying pipe connection (attempt {self._pipe_retry_count})...")
                        
                        self.open_pipe(verbose=False)
                        self.last_pipe_retry = current_time
                        if self.pipe is not None:
                            logger.info("✓ Pipe reconnected successfully!")
                            self._pipe_retry_count = 0  # Reset counter on success
                
                # Only detect gestures if camera is available
                if self.camera_available and self.gesture_detector:
                    # Detect gestures in current frame
                    detected_events = self.gesture_detector.detect_gestures(mappings)
                    
                    # Log detection activity
                    if detected_events:
                        press_events = [e for e in detected_events if e[1] == 'press']
                        release_events = [e for e in detected_events if e[1] == 'release']
                        if press_events:
                            logger.info(f"✓ Gestures detected: {press_events}")
                        # Log releases less frequently to reduce spam
                        if release_events and hasattr(self, '_release_log_counter'):
                            self._release_log_counter += 1
                            if self._release_log_counter % 10 == 0:
                                logger.debug(f"Gesture releases: {release_events}")
                        elif release_events:
                            self._release_log_counter = 0
                    
                    # Process events and send state changes to pipe
                    self.process_gesture_events(detected_events)
                else:
                    # Camera not available - release any active gestures
                    if self.active_gestures:
                        for button_name in list(self.active_gestures):
                            self.write_button_event_with_retry(button_name, 'release')
                        self.active_gestures.clear()
                
                # Update frame count
                self.frame_count += 1
                
                # Log FPS periodically (only if camera available)
                if self.camera_available:
                    self.log_fps()
                
                # Calculate frame processing time
                loop_time = time.time() - loop_start
                
                # Target 30 FPS = 33.3ms per frame
                target_frame_time = 1.0 / 30.0
                sleep_time = target_frame_time - loop_time
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
                elif loop_time > target_frame_time * 1.5 and self.camera_available:
                    # Track slow frames instead of logging each one
                    self.slow_frame_count += 1
                    self.slow_frame_times.append(loop_time * 1000)  # Store in ms
                    
                    # Log aggregated summary periodically
                    current_time = time.time()
                    if current_time - self.last_slow_frame_log >= self.slow_frame_log_interval:
                        if self.slow_frame_count > 0:
                            avg_slow_time = sum(self.slow_frame_times) / len(self.slow_frame_times)
                            max_slow_time = max(self.slow_frame_times)
                            min_slow_time = min(self.slow_frame_times)
                            
                            logger.warning(
                                f"Performance: {self.slow_frame_count} slow frames in last "
                                f"{self.slow_frame_log_interval:.0f}s | "
                                f"Avg: {avg_slow_time:.1f}ms | "
                                f"Min: {min_slow_time:.1f}ms | "
                                f"Max: {max_slow_time:.1f}ms | "
                                f"Target: {target_frame_time*1000:.1f}ms"
                            )
                            
                            # Reset counters
                            self.slow_frame_count = 0
                            self.slow_frame_times = []
                            self.last_slow_frame_log = current_time
        
        except KeyboardInterrupt:
            logger.info("Vision Sensor interrupted by user")
        
        except Exception as e:
            logger.error(f"Vision Sensor error: {e}", exc_info=True)
            # Don't raise - continue running even if there's an error
            logger.warning("Vision Sensor will continue running despite error")
        
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
