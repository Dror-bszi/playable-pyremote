"""
Gesture-to-button mapping configuration management.
"""

import json
import os
from typing import Dict, Optional


class GestureMapping:
    """Manages gesture-to-button mappings and configuration persistence."""
    
    def __init__(self, config_file: str = 'config/mappings.json'):
        """
        Initialize gesture mapping manager.
        
        Args:
            config_file: Path to JSON configuration file
        """
        self.config_file = config_file
        self.mappings = {}
        self.thresholds = {
            'delta_threshold': 0.05,
            'raise_minimum': 0.1
        }
        
        # Load existing configuration
        self.load_mappings(config_file)
    
    def load_mappings(self, file_path: str) -> Dict[str, str]:
        """
        Load gesture mappings from JSON configuration file.
        
        Args:
            file_path: Path to configuration file
            
        Returns:
            Dictionary of gesture_name -> button_name mappings
        """
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    config = json.load(f)
                    
                # Load mappings
                self.mappings = config.get('mappings', {})
                
                # Load thresholds
                if 'thresholds' in config:
                    self.thresholds.update(config['thresholds'])
                
                return self.mappings
            else:
                # Create default configuration if file doesn't exist
                self._create_default_config(file_path)
                return self.mappings
                
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to load mappings: {e}")
    
    def save_mappings(self, file_path: Optional[str] = None):
        """
        Persist current mappings and thresholds to JSON file.
        
        Args:
            file_path: Path to save configuration (uses default if None)
        """
        if file_path is None:
            file_path = self.config_file
        
        config = {
            'thresholds': self.thresholds,
            'mappings': self.mappings
        }
        
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Write configuration
            with open(file_path, 'w') as f:
                json.dump(config, f, indent=2)
                
        except Exception as e:
            raise RuntimeError(f"Failed to save mappings: {e}")
    
    def add_mapping(self, gesture_name: str, button: str):
        """
        Add or update a gesture-to-button mapping.
        
        Args:
            gesture_name: Name of the gesture (e.g., 'left_elbow_raise')
            button: PlayStation button name (e.g., 'SQUARE', 'CIRCLE')
        """
        # Validate gesture name
        valid_gestures = [
            'left_elbow_raise',
            'right_elbow_raise',
            'left_arm_forward',
            'right_arm_forward'
        ]
        
        if gesture_name not in valid_gestures:
            raise ValueError(
                f"Invalid gesture name: {gesture_name}. "
                f"Valid gestures: {', '.join(valid_gestures)}"
            )
        
        # Validate button name
        valid_buttons = [
            'CROSS', 'CIRCLE', 'SQUARE', 'TRIANGLE',
            'L1', 'L2', 'R1', 'R2',
            'L3', 'R3',
            'UP', 'DOWN', 'LEFT', 'RIGHT',
            'OPTIONS', 'PS'
        ]
        
        if button not in valid_buttons:
            raise ValueError(
                f"Invalid button name: {button}. "
                f"Valid buttons: {', '.join(valid_buttons)}"
            )
        
        # Add mapping
        self.mappings[gesture_name] = button
        
        # Auto-save
        self.save_mappings()
    
    def remove_mapping(self, gesture_name: str):
        """
        Remove a gesture mapping.
        
        Args:
            gesture_name: Name of the gesture to remove
        """
        if gesture_name in self.mappings:
            del self.mappings[gesture_name]
            # Auto-save
            self.save_mappings()
        else:
            raise KeyError(f"Gesture mapping not found: {gesture_name}")
    
    def get_active_mappings(self) -> Dict[str, str]:
        """
        Get currently active gesture mappings.
        
        Returns:
            Dictionary of gesture_name -> button_name mappings
        """
        return self.mappings.copy()
    
    def get_thresholds(self) -> Dict[str, float]:
        """
        Get current detection thresholds.
        
        Returns:
            Dictionary of threshold values
        """
        return self.thresholds.copy()
    
    def update_thresholds(self, delta_threshold: Optional[float] = None, 
                         raise_minimum: Optional[float] = None):
        """
        Update detection thresholds.
        
        Args:
            delta_threshold: Speed of movement threshold (0.1 - 2.0)
            raise_minimum: Range of movement threshold (0.0 - 1.0)
        """
        if delta_threshold is not None:
            if not 0.01 <= delta_threshold <= 2.0:
                raise ValueError("delta_threshold must be between 0.01 and 2.0")
            self.thresholds['delta_threshold'] = delta_threshold
        
        if raise_minimum is not None:
            if not 0.0 <= raise_minimum <= 1.0:
                raise ValueError("raise_minimum must be between 0.0 and 1.0")
            self.thresholds['raise_minimum'] = raise_minimum
        
        # Auto-save
        self.save_mappings()
    
    def _create_default_config(self, file_path: str):
        """
        Create default configuration file.
        
        Args:
            file_path: Path to create configuration file
        """
        default_config = {
            'thresholds': {
                'delta_threshold': 0.05,
                'raise_minimum': 0.1
            },
            'mappings': {
                'left_elbow_raise': 'SQUARE',
                'right_elbow_raise': 'CIRCLE',
                'left_arm_forward': 'L1',
                'right_arm_forward': 'R1'
            }
        }
        
        self.thresholds = default_config['thresholds']
        self.mappings = default_config['mappings']
        
        # Save default configuration
        self.save_mappings(file_path)
