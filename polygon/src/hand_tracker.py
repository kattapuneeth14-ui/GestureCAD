"""
Hand tracker module for GestureCAD.
Uses MediaPipe Hands to track 21 hand landmarks and compute hand scale.
"""

import sys
from unittest.mock import MagicMock
# Prevent TensorFlow dependency conflicts in MediaPipe tasks module on import
sys.modules['tensorflow'] = MagicMock()

from typing import List, Tuple, Optional
import cv2
import mediapipe as mp
import numpy as np


# Import geometry classes
from geometry import Point


class HandTracker:
    """Wrapper around MediaPipe Hands to process video frames and extract landmarks."""

    def __init__(
        self,
        max_num_hands: int = 1,
        min_detection_confidence: float = 0.7,
        min_tracking_confidence: float = 0.7,
    ) -> None:
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=max_num_hands,
            model_complexity=1,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self.mp_draw = mp.solutions.drawing_utils
        self.results = None

    def process_frame(self, frame: np.ndarray) -> Tuple[List[Point], List[Point], List[Tuple[float, float, float]]]:
        """
        Process an image frame to find hand landmarks.
        Returns:
            - A list of 21 Points in pixel coordinates.
            - A list of 21 Points in normalized (0.0 to 1.0) coordinates.
            - A list of 21 3D coordinates (x, y, z) as float tuples.
            All lists are empty if no hand is detected.
        """
        # MediaPipe requires RGB images
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self.results = self.hands.process(rgb_frame)

        pixel_landmarks: List[Point] = []
        norm_landmarks: List[Point] = []
        landmarks_3d: List[Tuple[float, float, float]] = []

        if self.results.multi_hand_landmarks:
            # We track only the first hand
            hand_lms = self.results.multi_hand_landmarks[0]
            height, width, _ = frame.shape

            for lm in hand_lms.landmark:
                # Store normalized coordinates
                norm_landmarks.append(Point(lm.x, lm.y))
                # Map to pixel space coordinates
                pixel_landmarks.append(Point(lm.x * width, lm.y * height))
                # Store relative 3D coordinate
                landmarks_3d.append((lm.x, lm.y, lm.z))

        return pixel_landmarks, norm_landmarks, landmarks_3d

    def get_hand_scale_norm(self, norm_landmarks: List[Point]) -> float:
        """
        Compute normalized hand scale (distance from wrist 0 to middle finger MCP 9).
        Used to normalize gesture thresholds.
        """
        if len(norm_landmarks) < 21:
            return 1.0  # Return default scale if hand is not fully tracked
        
        wrist = norm_landmarks[0]
        middle_mcp = norm_landmarks[9]
        return wrist.distance(middle_mcp)

    def get_hand_scale_pixel(self, pixel_landmarks: List[Point]) -> float:
        """Compute hand scale in pixel units."""
        if len(pixel_landmarks) < 21:
            return 100.0  # Default pixel scale
        
        wrist = pixel_landmarks[0]
        middle_mcp = pixel_landmarks[9]
        return wrist.distance(middle_mcp)

    def close(self) -> None:
        """Release MediaPipe resources."""
        self.hands.close()
