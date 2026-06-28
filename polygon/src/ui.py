"""
UI module for GestureCAD.
Handles rendering of the header bar, state info, instructions, FPS counter,
and virtual interactive buttons.
"""

from typing import List, Tuple, Dict, Optional, Callable
import cv2
import numpy as np

# Import Point
from geometry import Point


class VirtualButton:
    """Represents a virtual button rendered on the screen that can be triggered by mouse or hand gestures."""

    def __init__(
        self,
        name: str,
        label: str,
        x: int,
        y: int,
        w: int,
        h: int,
        color: Tuple[int, int, int] = (60, 60, 60),
        hover_color: Tuple[int, int, int] = (0, 165, 255),  # Orange-ish/Yellow
        text_color: Tuple[int, int, int] = (255, 255, 255),
    ) -> None:
        self.name: str = name
        self.label: str = label
        self.x: int = x
        self.y: int = y
        self.w: int = w
        self.h: int = h
        self.color: Tuple[int, int, int] = color
        self.hover_color: Tuple[int, int, int] = hover_color
        self.text_color: Tuple[int, int, int] = text_color
        self.is_hovered: bool = False

    def contains(self, pt: Point) -> bool:
        """Check if a point is inside the button bounding box."""
        return self.x <= pt.x <= self.x + self.w and self.y <= pt.y <= self.y + self.h

    def draw(self, frame: np.ndarray) -> None:
        """Draw the button on the frame."""
        bg_color = self.hover_color if self.is_hovered else self.color
        border_color = (255, 255, 255) if self.is_hovered else (180, 180, 180)
        
        # Semi-transparent button box
        overlay = frame.copy()
        cv2.rectangle(overlay, (self.x, self.y), (self.x + self.w, self.y + self.h), bg_color, -1)
        cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

        # Button border
        cv2.rectangle(frame, (self.x, self.y), (self.x + self.w, self.y + self.h), border_color, 1)

        # Center text
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        thickness = 1
        text_size = cv2.getTextSize(self.label, font, font_scale, thickness)[0]
        text_x = self.x + (self.w - text_size[0]) // 2
        text_y = self.y + (self.h + text_size[1]) // 2
        cv2.putText(frame, self.label, (text_x, text_y), font, font_scale, self.text_color, thickness, cv2.LINE_AA)


class UI:
    """Manages HUD rendering, buttons layout, and gesture interaction with buttons."""

    def __init__(self, frame_width: int = 640) -> None:
        self.frame_width: int = frame_width
        self.toolbar_height: int = 40
        self.buttons: List[VirtualButton] = []
        self._init_buttons()

    def _init_buttons(self) -> None:
        """Initialize the virtual buttons positions relative to frame width."""
        self.buttons.clear()
        
        btn_w = 80
        btn_h = 24
        y_pos = (self.toolbar_height - btn_h) // 2
        
        # Layout buttons from right to left
        margin = 10
        x_save = self.frame_width - btn_w - margin
        x_reset = x_save - btn_w - margin
        x_clear = x_reset - btn_w - margin

        self.buttons.append(VirtualButton("clear", "CLEAR (C)", x_clear, y_pos, btn_w, btn_h, color=(30, 30, 120)))
        self.buttons.append(VirtualButton("reset", "RESET (R)", x_reset, y_pos, btn_w, btn_h, color=(30, 80, 30)))
        self.buttons.append(VirtualButton("save", "SAVE (S)", x_save, y_pos, btn_w, btn_h, color=(80, 30, 80)))

    def update_resolution(self, width: int) -> None:
        """Update button placement when resolution changes."""
        if width != self.frame_width:
            self.frame_width = width
            self._init_buttons()

    def draw_toolbar(self, frame: np.ndarray, state_name: str, fps: float, instruction: str, selected_status: str = "None", gesture_name: str = "UNKNOWN", rotation_mode: bool = False) -> None:
        """Draw the thin responsive transparent status bar at the top with metadata."""
        height, width, _ = frame.shape
        
        # 1. Top status bar translucent background
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (self.frame_width, self.toolbar_height), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.88, frame, 0.12, 0, frame)
        
        # Border separation line
        cv2.line(frame, (0, self.toolbar_height), (self.frame_width, self.toolbar_height), (60, 60, 60), 1)

        # Style colors
        font = cv2.FONT_HERSHEY_SIMPLEX
        
        # Calculate horizontal positions dynamically to fit between left edge and buttons
        left_limit = 10
        right_limit = self.frame_width - 280
        available_w = right_limit - left_limit

        if available_w > 400:
            x_fps = 10
            x_mode = 110
            x_rot = 260
            x_sel = 390
        else:
            # Compact spacing for smaller window widths
            x_fps = 10
            x_mode = 80
            x_rot = 190
            x_sel = 295

        # Draw FPS (centered vertically at y=25)
        fps_text = f"FPS: {fps:.1f}"
        cv2.putText(frame, fps_text, (x_fps, 25), font, 0.38, (140, 140, 140), 1, cv2.LINE_AA)

        # Draw Mode Info
        cv2.putText(frame, "MODE:", (x_mode, 25), font, 0.38, (160, 160, 160), 1, cv2.LINE_AA)
        state_color = (0, 255, 0) if state_name == "DRAWING" else (0, 165, 255) if state_name == "MOVING" else (255, 0, 255) if state_name == "ROTATING" else (0, 255, 255) if state_name == "SCALING" else (240, 240, 240)
        cv2.putText(frame, state_name, (x_mode + 42, 25), font, 0.42, state_color, 2, cv2.LINE_AA)

        # Draw Rotation Mode ON/OFF
        cv2.putText(frame, "ROTATION:", (x_rot, 25), font, 0.38, (160, 160, 160), 1, cv2.LINE_AA)
        rot_text = "ON" if rotation_mode else "OFF"
        rot_color = (255, 120, 0) if rotation_mode else (120, 120, 120)
        cv2.putText(frame, rot_text, (x_rot + 68, 25), font, 0.42, rot_color, 2, cv2.LINE_AA)

        # Draw Selected Object Status
        cv2.putText(frame, "SELECTED:", (x_sel, 25), font, 0.38, (160, 160, 160), 1, cv2.LINE_AA)
        status_color = (0, 255, 255) if selected_status != "None" else (120, 120, 120)
        cv2.putText(frame, selected_status, (x_sel + 68, 25), font, 0.42, status_color, 2, cv2.LINE_AA)

        # Draw virtual buttons
        for btn in self.buttons:
            btn.draw(frame)

        # 2. Draw Bottom-Right Translucent Instructions Card
        card_w = 260
        card_h = 135
        card_x1 = width - card_w - 15
        card_y1 = height - card_h - 15
        card_x2 = width - 15
        card_y2 = height - 15

        # Translucent background for card
        card_overlay = frame.copy()
        cv2.rectangle(card_overlay, (card_x1, card_y1), (card_x2, card_y2), (15, 15, 15), -1)
        cv2.addWeighted(card_overlay, 0.8, frame, 0.2, 0, frame)
        # Border
        cv2.rectangle(frame, (card_x1, card_y1), (card_x2, card_y2), (80, 80, 80), 1)

        # Card Title
        cv2.putText(frame, "GESTURE CONTROLS", (card_x1 + 12, card_y1 + 20), font, 0.4, (0, 255, 255), 1, cv2.LINE_AA)
        
        # Compact list of controls
        items = [
            "1. Index Finger -> DRAW shape",
            "2. Closed Fist   -> MOVE shape",
            "3. Thumbs Up     -> ROTATE ON",
            "4. Thumbs Down   -> ROTATE OFF",
            "5. Three Fingers -> SCALE shape",
            "6. Open Palm     -> IDLE / Deselect",
            "C: Clear | R: Reset | ESC: Exit"
        ]
        
        y_offset = card_y1 + 34
        for item in items:
            cv2.putText(frame, item, (card_x1 + 12, y_offset), font, 0.33, (210, 210, 210), 1, cv2.LINE_AA)
            y_offset += 13

    def handle_cursor(self, cursor_pos: Point, is_pinch_clicked: bool) -> Optional[str]:
        """
        Check hover and click interactions with virtual buttons.
        Returns the action name if a button is clicked/triggered, else None.
        """
        action_triggered: Optional[str] = None

        for btn in self.buttons:
            if btn.contains(cursor_pos):
                btn.is_hovered = True
                if is_pinch_clicked:
                    action_triggered = btn.name
            else:
                btn.is_hovered = False

        return action_triggered
