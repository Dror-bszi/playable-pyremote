"""Pipe Reader for consuming Named Pipe messages and forwarding to Controller."""
import logging
import os
import threading
import time
from typing import Optional

_LOGGER = logging.getLogger(__name__)


class PipeReader:
    """Reads from Named Pipe and forwards commands to Controller."""

    def __init__(self, controller, pipe_path: str = '/tmp/my_pipe'):
        """Initialize PipeReader.
        
        Args:
            controller: The Controller instance to forward commands to
            pipe_path: Path to the Named Pipe (default: /tmp/my_pipe)
        """
        self.controller = controller
        self.pipe_path = pipe_path
        self.running = False
        self.thread: Optional[threading.Thread] = None
        _LOGGER.info(f"PipeReader initialized with pipe: {pipe_path}")

    def start(self):
        """Start pipe reader thread."""
        if self.thread is not None:
            _LOGGER.warning("PipeReader is already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()
        _LOGGER.info("PipeReader thread started")

    def stop(self):
        """Stop pipe reader thread gracefully."""
        if not self.running:
            return
        
        _LOGGER.info("Stopping PipeReader...")
        self.running = False
        
        if self.thread:
            self.thread.join(timeout=2)
            if self.thread.is_alive():
                _LOGGER.warning("PipeReader thread did not stop gracefully")
            else:
                _LOGGER.info("PipeReader thread stopped")
            self.thread = None

    def _read_loop(self):
        """Continuously read from pipe and forward messages to controller with error recovery."""
        _LOGGER.info("PipeReader loop started")
        consecutive_errors = 0
        max_consecutive_errors = 10
        
        while self.running:
            try:
                # Open pipe for reading (blocks until writer opens)
                with open(self.pipe_path, 'r') as pipe:
                    _LOGGER.info("Pipe opened for reading")
                    consecutive_errors = 0  # Reset error counter on successful open
                    
                    while self.running:
                        try:
                            message = self._parse_message(pipe)
                            if message:
                                self._forward_to_controller(message)
                                consecutive_errors = 0  # Reset on successful message
                        except Exception as msg_error:
                            consecutive_errors += 1
                            _LOGGER.error(f"Message processing error: {msg_error}")
                            
                            if consecutive_errors >= max_consecutive_errors:
                                _LOGGER.error(
                                    f"Too many consecutive errors ({consecutive_errors}), "
                                    "reopening pipe..."
                                )
                                break  # Break inner loop to reopen pipe
                            
                            time.sleep(0.1)  # Brief delay before next message
                        
            except FileNotFoundError:
                _LOGGER.error(f"Pipe not found: {self.pipe_path}")
                _LOGGER.info("Waiting for pipe to be created...")
                time.sleep(2)  # Wait before retry
            except BrokenPipeError:
                _LOGGER.warning("Pipe broken - writer may have disconnected")
                _LOGGER.info("Attempting to reopen pipe...")
                time.sleep(1)  # Wait before retry
            except IOError as io_error:
                _LOGGER.error(f"IO error reading from pipe: {io_error}")
                _LOGGER.info("Attempting to reopen pipe...")
                time.sleep(1)  # Wait before retry
            except Exception as error:
                _LOGGER.error(f"Pipe read error: {error}", exc_info=True)
                time.sleep(1)  # Wait before retry
        
        _LOGGER.info("PipeReader loop ended")

    def _parse_message(self, pipe) -> Optional[dict]:
        """Parse pipe message into structured data with validation.
        
        Protocol:
        - Button message: BUTTON_NAME\npress|release\n\n
        - Analog message: LEFT|RIGHT\nx|y\nfloat_value\n
        
        Args:
            pipe: Open file handle to the pipe
            
        Returns:
            Dictionary with message data or None if parsing fails
        """
        try:
            # Read first line (button name or stick name)
            line1 = pipe.readline().strip()
            if not line1:
                return None
            
            # Read second line (action or axis)
            line2 = pipe.readline().strip()
            if not line2:
                _LOGGER.warning("Incomplete message: missing line 2")
                return None
            
            # Read third line (empty for buttons, value for analog)
            line3 = pipe.readline().strip()
            
            # Determine message type based on line2
            if line2 in ['press', 'release']:
                # Button message - validate button name
                valid_buttons = [
                    'UP', 'DOWN', 'LEFT', 'RIGHT',
                    'CROSS', 'CIRCLE', 'SQUARE', 'TRIANGLE',
                    'L1', 'R1', 'L2', 'R2', 'L3', 'R3',
                    'OPTIONS', 'PS'
                ]
                
                if line1 not in valid_buttons:
                    _LOGGER.warning(f"Invalid button name: {line1}")
                    return None
                
                return {
                    'type': 'button',
                    'button': line1,
                    'action': line2
                }
            elif line2 in ['x', 'y']:
                # Analog message - validate stick name and value
                if line1 not in ['LEFT', 'RIGHT']:
                    _LOGGER.warning(f"Invalid stick name: {line1}")
                    return None
                
                try:
                    value = float(line3)
                    # Validate value range (-1.0 to 1.0)
                    if not (-1.0 <= value <= 1.0):
                        _LOGGER.warning(f"Analog value out of range: {value}")
                        value = max(-1.0, min(1.0, value))  # Clamp to valid range
                    
                    return {
                        'type': 'analog',
                        'stick': line1,
                        'axis': line2,
                        'value': value
                    }
                except ValueError:
                    _LOGGER.warning(f"Invalid analog value: {line3}")
                    return None
            else:
                _LOGGER.warning(f"Unknown message format. Line2: {line2}")
                return None
                
        except EOFError:
            _LOGGER.debug("End of pipe reached")
            return None
        except Exception as error:
            _LOGGER.error(f"Parse error: {error}", exc_info=True)
            return None

    def _forward_to_controller(self, message: dict):
        """Send command to PS5 via Controller with error handling.
        
        Args:
            message: Parsed message dictionary
        """
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                if message['type'] == 'button':
                    self.controller.button(
                        message['button'],
                        message['action']
                    )
                    _LOGGER.debug(f"Button: {message['button']} {message['action']}")
                    return  # Success
                    
                elif message['type'] == 'analog':
                    self.controller.stick(
                        message['stick'],
                        message['axis'],
                        message['value']
                    )
                    # Update sticks to send state to PS5
                    self.controller.update_sticks()
                    _LOGGER.debug(
                        f"Stick: {message['stick']} {message['axis']} = {message['value']}"
                    )
                    return  # Success
                    
            except AttributeError as attr_error:
                _LOGGER.error(f"Controller API error - method not found: {attr_error}")
                return  # Don't retry for API errors
            except ConnectionError as conn_error:
                _LOGGER.error(f"Connection error forwarding to controller: {conn_error}")
                if attempt < max_retries - 1:
                    _LOGGER.info(f"Retrying... (attempt {attempt + 2}/{max_retries})")
                    time.sleep(0.1)
                else:
                    _LOGGER.error("Failed to forward command after all retries")
            except Exception as error:
                _LOGGER.error(f"Controller forwarding error: {error}", exc_info=True)
                if attempt < max_retries - 1:
                    _LOGGER.info(f"Retrying... (attempt {attempt + 2}/{max_retries})")
                    time.sleep(0.1)
                else:
                    _LOGGER.error("Failed to forward command after all retries")
