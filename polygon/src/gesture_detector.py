"""
Gesture detector module for GestureCAD.
Analyzes hand landmarks to detect:
- Pinch (Thumb and Index tips close, edge-triggered for single-point addition)
- Open Palm (All fingers extended)
- Closed Fist (All fingers curled)
- Index Finger (Index extended, others curled)
"""

from typing import List, Tuple, Dict
import math
import numpy as np

# Import geometry Point
from geometry import Point


class GestureDetector:
    """Detects and registers hand gestures from hand landmarks."""

    def __init__(self, pinch_threshold_ratio: float = 0.16) -> None:
        """
        Initialize the gesture detector.
        Args:
            pinch_threshold_ratio: Pinch distance normalized by hand scale.
        """
        self.pinch_threshold_ratio: float = pinch_threshold_ratio
        
        # State tracking for edge-trigger pinch
        self.is_pinching_active: bool = False
        
        # Hand scale caching
        self.hand_scale: float = 1.0

    def detect_extended_fingers(self, landmarks: List[Point]) -> Dict[str, bool]:
        """
        Determine which fingers are extended using rotation-invariant distance metrics.
        Fingers: 'thumb', 'index', 'middle', 'ring', 'pinky'.
        """
        finger_states = {
            "thumb": False,
            "index": False,
            "middle": False,
            "ring": False,
            "pinky": False,
        }

        if len(landmarks) < 21:
            return finger_states

        wrist = landmarks[0]

        # Standard fingers: Index (8), Middle (12), Ring (16), Pinky (20)
        # We compare the distance of the tip and PIP to the wrist
        # Index: Tip=8, PIP=6, MCP=5
        # Middle: Tip=12, PIP=10, MCP=9
        # Ring: Tip=16, PIP=14, MCP=13
        # Pinky: Tip=20, PIP=18, MCP=17
        
        # Helper lambda to check standard finger extension
        def check_finger(tip_idx: int, pip_idx: int, mcp_idx: int) -> bool:
            tip = landmarks[tip_idx]
            pip = landmarks[pip_idx]
            mcp = landmarks[mcp_idx]
            d_tip = wrist.distance(tip)
            d_pip = wrist.distance(pip)
            d_mcp = wrist.distance(mcp)
            # Standard extended fingers should have their tip further from wrist than PIP/MCP
            # We also check y-coordinates as a fallback/reinforcement for upright hand posture
            upright_extended = tip.y < pip.y
            dist_extended = d_tip > d_pip and d_tip > d_mcp
            
            # Use distance-based as primary, reinforced by knuckle spacing
            return dist_extended or (upright_extended and d_tip > d_mcp * 0.9)

        finger_states["index"] = check_finger(8, 6, 5)
        finger_states["middle"] = check_finger(12, 10, 9)
        finger_states["ring"] = check_finger(16, 14, 13)
        finger_states["pinky"] = check_finger(20, 18, 17)

        # Thumb: Tip=4, IP=3, MCP=2.
        # Thumb moves sideways. We measure tip distance to pinky knuckle (MCP 17) or index MCP (5).
        # Extended thumb tip is far from index MCP (5) and wrist (0).
        thumb_tip = landmarks[4]
        thumb_ip = landmarks[3]
        index_mcp = landmarks[5]
        
        d_thumb_wrist = wrist.distance(thumb_tip)
        d_ip_wrist = wrist.distance(thumb_ip)
        
        d_thumb_index = thumb_tip.distance(index_mcp)
        d_ip_index = thumb_ip.distance(index_mcp)

        # Thumb is extended if its tip is further from wrist than its IP joint,
        # and it's splayed outward away from index MCP.
        finger_states["thumb"] = (d_thumb_wrist > d_ip_wrist) and (d_thumb_index > d_ip_index * 1.05)

        return finger_states

    def get_gesture(self, landmarks_pixel: List[Point], landmarks_norm: List[Point]) -> Tuple[str, bool, Point]:
        """
        Analyze landmarks and return the current gesture, pinch click trigger (always False),
        and cursor position.
        
        Returns:
            Tuple: (gesture_name: str, pinch_triggered: bool, cursor_point: Point)
            gesture_name can be: "UNKNOWN", "ONE_FINGER", "TWO_FINGERS", "THREE_FINGERS", "CLOSED_FIST", "OPEN_PALM"
            pinch_triggered: always False
            cursor_point: A Point representing the index finger tip or hand center.
        """
        if len(landmarks_pixel) < 21:
            return "UNKNOWN", False, Point(0, 0)

        # Calculate hand scale
        self.hand_scale = landmarks_norm[0].distance(landmarks_norm[9])

        # Get finger extension states
        fingers = self.detect_extended_fingers(landmarks_pixel)
        
        # Cursor is positioned at the Index Finger Tip (8)
        cursor = landmarks_pixel[8]

        # 1. Closed Fist (All fingers curled)
        if not any(fingers.values()):
            return "CLOSED_FIST", False, landmarks_pixel[9]  # Use middle MCP as cursor

        # 2. Open Palm (All standard fingers extended)
        if fingers["index"] and fingers["middle"] and fingers["ring"] and fingers["pinky"]:
            return "OPEN_PALM", False, cursor

        # 3. Three Fingers (Index, Middle, Ring extended; Pinky curled)
        if fingers["index"] and fingers["middle"] and fingers["ring"] and not fingers["pinky"]:
            return "THREE_FINGERS", False, cursor

        # 4. Thumbs Up / Thumbs Down (Thumb extended, all other fingers curled)
        if fingers["thumb"] and not fingers["index"] and not fingers["middle"] and not fingers["ring"] and not fingers["pinky"]:
            thumb_tip = landmarks_pixel[4]
            thumb_mcp = landmarks_pixel[2]
            if thumb_tip.y < thumb_mcp.y:
                return "THUMBS_UP", False, cursor
            else:
                return "THUMBS_DOWN", False, cursor

        # 5. Two Fingers (Index, Middle extended; Ring, Pinky curled)
        if fingers["index"] and fingers["middle"] and not fingers["ring"] and not fingers["pinky"]:
            return "TWO_FINGERS", False, cursor

        # 6. One Finger (Index extended; Middle, Ring, Pinky curled)
        if fingers["index"] and not fingers["middle"] and not fingers["ring"] and not fingers["pinky"]:
            return "ONE_FINGER", False, cursor

        return "UNKNOWN", False, cursor
