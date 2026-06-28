"""
Main application module for GestureCAD.
Initializes the video capture feed, handles the main loop, processes mouse clicks,
processes keyboard shortcuts, and saves files.
"""

import os
import sys
import time
import json
from datetime import datetime
from typing import Optional, Tuple
import cv2
import numpy as np

# Ensure src path is accessible
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from geometry import Point, Polygon
from hand_tracker import HandTracker
from gesture_detector import GestureDetector
from state_machine import State, StateMachine
from ui import UI
from renderer import Renderer


class GestureCADApp:
    """The central application coordinator driving the main OpenCV processing loop."""

    def __init__(self, camera_index: int = 0) -> None:
        self.camera_index: int = camera_index
        self.cap: Optional[cv2.VideoCapture] = None
        self.window_name: str = "GestureCAD - Real-Time 2D Graphics Editor"
        
        # Modules setup
        self.tracker: HandTracker = HandTracker()
        self.detector: GestureDetector = GestureDetector()
        self.state_machine: StateMachine = StateMachine()
        self.renderer: Renderer = Renderer()
        self.ui: UI = UI()

        # FPS performance calculations
        self.prev_time: float = time.time()
        self.fps: float = 30.0
        self.fps_alpha: float = 0.1  # EMA smoothing factor
        
        # Interaction coordinates tracking
        self.mouse_cursor: Optional[Point] = None
        self.mouse_clicked: bool = False

        # Resolution configuration
        self.win_w: int = 1280
        self.win_h: int = 720
        self.render_w: int = 1280
        self.render_h: int = 720
        self.offset_x: int = 0
        self.offset_y: int = 0

    def setup_capture(self) -> bool:
        """Initialize the OpenCV VideoCapture camera feed."""
        self.cap = cv2.VideoCapture(self.camera_index)
        if not self.cap.isOpened():
            print(f"Error: Could not open camera at index {self.camera_index}.")
            return False

        # Request high-definition resolution (preferably 1280x720) for crisp visual overlays
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        
        # Bind OpenCV window mouse events with WINDOW_NORMAL (making it resizable)
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, 1280, 720)
        cv2.setMouseCallback(self.window_name, self._mouse_event_callback)
        
        # Display initial black placeholder frame to instantiate window in OS window manager
        placeholder = np.zeros((720, 1280, 3), dtype=np.uint8)
        cv2.imshow(self.window_name, placeholder)
        cv2.waitKey(1)  # Process events to register window handle
        
        return True

    def _mouse_event_callback(self, event: int, x: int, y: int, flags: int, param) -> None:
        """OpenCV mouse callback handler for secondary mouse controls."""
        # Map raw window coordinates back to the centered render frame coordinates
        mapped_x = max(0, min(self.render_w - 1, x - self.offset_x))
        mapped_y = max(0, min(self.render_h - 1, y - self.offset_y))

        if event == cv2.EVENT_MOUSEMOVE:
            self.mouse_cursor = Point(mapped_x, mapped_y)
        elif event == cv2.EVENT_LBUTTONDOWN:
            self.mouse_cursor = Point(mapped_x, mapped_y)
            self.mouse_clicked = True

    def get_state_instruction(self, state: State) -> str:
        """Return user instruction text based on the active mode state."""
        if state == State.IDLE:
            return "1 Finger -> DRAW | Fist -> SELECT/MOVE | Thumbs Up -> ROTATE"
        elif state == State.DRAWING:
            return "Drawing... Change gesture to STOP"
        elif state == State.MOVING:
            return "Hold Fist to DRAG | Release Fist to DROP"
        elif state == State.ROTATING:
            return "Rotation Mode ON: Move hand to ROTATE | Thumbs Down -> EXIT"
        elif state == State.SCALING:
            return "3 Fingers -> Move hand up/down to SCALE"
        return "No Hand Detected"

    def execute_ui_action(self, action: str, frame: np.ndarray) -> None:
        """Process triggered menu buttons or keyboard shortcuts."""
        if action == "clear":
            print("Clearing current drawing...")
            self.state_machine.clear_active()
        elif action == "reset":
            print("Resetting canvas...")
            self.state_machine.reset()
        elif action == "save":
            print("Saving files...")
            self.save_session(frame)

    def save_session(self, frame: np.ndarray) -> None:
        """Export completed polygon coordinates as JSON and save a screenshot."""
        os.makedirs("assets", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save screenshot
        screenshot_filename = f"assets/screenshot_{timestamp}.png"
        cv2.imwrite(screenshot_filename, frame)
        print(f"Screenshot saved to: {screenshot_filename}")

        # Save coordinates to JSON
        json_filename = f"assets/polygons_{timestamp}.json"
        polygons_data = []
        for poly in self.state_machine.polygons:
            poly_data = {
                "vertices": [[pt.x, pt.y] for pt in poly.vertices],
                "color": poly.color,
                "is_closed": poly.is_closed
            }
            polygons_data.append(poly_data)

        with open(json_filename, "w") as f:
            json.dump(polygons_data, f, indent=4)
        print(f"Coordinates saved to: {json_filename}")

    def run(self) -> None:
        """The main application rendering and updating loop."""
        if not self.setup_capture():
            return

        print("\n=== GestureCAD is running ===")
        print("Use hand gestures in front of the camera to draw and move polygons.")
        print("Controls:")
        print("  - One Finger Extended  -> Draw Shape")
        print("  - Closed Fist           -> Select & Move")
        print("  - Open Palm / Tilt Hand -> Rotate Object 3D")
        print("Keyboard shortcuts:")
        print("  C   - Clear active drawing")
        print("  R   - Reset canvas")
        print("  S   - Save screenshot & polygon coordinates")
        print("  ESC - Exit application\n")

        while True:
            success, raw_frame = self.cap.read()
            if not success:
                print("Error: Could not read frame from webcam.")
                break

            # Mirror view (flip horizontally)
            raw_frame = cv2.flip(raw_frame, 1)

            # Ensure capture resolution is not higher than 1280x720
            cap_h, cap_w = raw_frame.shape[:2]
            if cap_w > 1280 or cap_h > 720:
                scale = min(1280 / cap_w, 720 / cap_h)
                new_w = int(cap_w * scale)
                new_h = int(cap_h * scale)
                raw_frame = cv2.resize(raw_frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
            
            # Get current window client dimensions
            win_w, win_h = 1280, 720
            try:
                rect = cv2.getWindowImageRect(self.window_name)
                if rect is not None and rect[2] > 0 and rect[3] > 0:
                    win_w, win_h = rect[2], rect[3]
                else:
                    break  # Window was closed
            except cv2.error:
                break  # Window was destroyed/closed

            # Determine rendering resolution and centering offsets
            self.win_w = win_w
            self.win_h = win_h
            self.render_w = min(win_w, 1280)
            self.render_h = min(win_h, 720)
            self.offset_x = (win_w - self.render_w) // 2
            self.offset_y = (win_h - self.render_h) // 2

            # Aspect-ratio preserving center crop and scale to fill the rendering resolution area
            h, w = raw_frame.shape[:2]
            img_aspect = w / h
            target_aspect = self.render_w / self.render_h

            if img_aspect > target_aspect:
                # Camera frame is wider than target: crop sides
                new_w = int(h * target_aspect)
                start_x = (w - new_w) // 2
                cropped = raw_frame[:, start_x:start_x + new_w]
            else:
                # Camera frame is taller than target: crop top and bottom
                new_h = int(w / target_aspect)
                start_y = (h - new_h) // 2
                cropped = raw_frame[start_y:start_y + new_h, :]

            frame = cv2.resize(cropped, (self.render_w, self.render_h), interpolation=cv2.INTER_LINEAR)
            
            # Synchronize resolution in UI module
            self.ui.update_resolution(self.render_w)

            # Calculate FPS using Exponential Moving Average
            curr_time = time.time()
            dt = curr_time - self.prev_time
            if dt > 0:
                self.fps = (1.0 - self.fps_alpha) * self.fps + self.fps_alpha * (1.0 / dt)
            self.prev_time = curr_time

            # 1. Process hand landmarks (includes relative 3D coordinate)
            pixel_lms, norm_lms, lms_3d = self.tracker.process_frame(frame)

            # 2. Run Gesture recognition
            gesture = "UNKNOWN"
            cursor_pos = Point(0, 0)

            # If hand is detected, use hand controls
            if pixel_lms:
                _, _, cursor_pos = self.detector.get_gesture(pixel_lms, norm_lms)
                gesture, _, cursor_pos = self.detector.get_gesture(pixel_lms, norm_lms)
            # Fallback to mouse cursor if no hand is detected
            elif self.mouse_cursor is not None:
                # Search if mouse hovers over any completed polygon
                hovered_poly = None
                for poly in reversed(self.state_machine.polygons):
                    if poly.hit_test(self.mouse_cursor):
                        hovered_poly = poly
                        break

                # Toggle mouse behavior: click to start/stop action
                if self.mouse_clicked:
                    self.mouse_clicked = False
                    if self.state_machine.state == State.IDLE:
                        if hovered_poly:
                            gesture = "CLOSED_FIST"
                        else:
                            gesture = "ONE_FINGER"
                    else:
                        gesture = "UNKNOWN"  # Returns to IDLE
                else:
                    # Maintain current state's gesture
                    if self.state_machine.state == State.DRAWING:
                        gesture = "ONE_FINGER"
                    elif self.state_machine.state == State.MOVING:
                        gesture = "CLOSED_FIST"
                    else:
                        gesture = "UNKNOWN"
                
                cursor_pos = self.mouse_cursor

            # 3. Update state machine transitions (passing pixel landmarks for wrist-based rotation)
            self.state_machine.update(gesture, False, cursor_pos, lms_3d, pixel_lms)

            # 4. Handle UI button triggers (exclusively from physical mouse click in this mode)
            is_clicked = False
            if self.mouse_clicked and self.mouse_cursor is not None:
                is_clicked = True
                cursor_pos = self.mouse_cursor
                self.mouse_clicked = False
                
            ui_action = self.ui.handle_cursor(cursor_pos, is_clicked)
            if ui_action:
                self.execute_ui_action(ui_action, frame)

            # 5. Render graphics overlays
            # Draw polygons (updates to 3D representation during active rotation)
            self.renderer.draw_polygons(
                frame, 
                self.state_machine.polygons, 
                selected_poly=self.state_machine.selected_polygon,
                grabbed_poly=self.state_machine.grabbed_polygon,
                state_name=self.state_machine.state.name,
                rot_angles=self.state_machine.rot_angles if self.state_machine.state == State.ROTATING else None,
                original_vertices=self.state_machine.original_vertices if self.state_machine.state == State.ROTATING else None,
                rotation_mode=self.state_machine.rotation_mode
            )

            # Draw current active drawing preview
            self.renderer.draw_active_preview(frame, self.state_machine.active_polygon, cursor_pos)

            # Draw hand skeleton (only if hand is detected)
            if pixel_lms:
                # Use the state machine's debounced gesture to color the skeleton
                debounced = self.state_machine._debounce_gesture(gesture)
                self.renderer.draw_skeleton(frame, pixel_lms, debounced)
                self.renderer.draw_cursor(frame, cursor_pos, debounced)

            # Draw top toolbar overlay
            inst_text = self.get_state_instruction(self.state_machine.state)
            
            # Compute selected status string
            selected_status = "None"
            if self.state_machine.selected_polygon is not None:
                try:
                    idx = self.state_machine.polygons.index(self.state_machine.selected_polygon)
                    selected_status = f"Poly #{idx+1}"
                except ValueError:
                    selected_status = "Active"

            # Get the debounced gesture name to pass to the HUD toolbar
            debounced_gesture = self.state_machine._debounce_gesture(gesture)
            self.ui.draw_toolbar(frame, self.state_machine.state.name, self.fps, inst_text, selected_status, debounced_gesture, self.state_machine.rotation_mode)

            # Center the rendered frame on a black canvas if window is larger than rendering resolution
            if win_w > self.render_w or win_h > self.render_h:
                display_frame = np.zeros((win_h, win_w, 3), dtype=np.uint8)
                display_frame[self.offset_y:self.offset_y + self.render_h, self.offset_x:self.offset_x + self.render_w] = frame
            else:
                display_frame = frame

            # 6. Render Frame
            cv2.imshow(self.window_name, display_frame)

            # 7. Listen for Keyboard shortcuts
            key = cv2.waitKey(1) & 0xFF
            if key == 27:  # ESC
                break
            elif key in [ord("c"), ord("C")]:
                self.execute_ui_action("clear", frame)
            elif key in [ord("r"), ord("R")]:
                self.execute_ui_action("reset", frame)
            elif key in [ord("s"), ord("S")]:
                self.execute_ui_action("save", frame)
        # Cleanup resources
        self.cleanup()

    def cleanup(self) -> None:
        """Release webcams, windows, and hand tracker."""
        if self.cap:
            self.cap.release()
        self.tracker.close()
        cv2.destroyAllWindows()
        print("Application exited cleanly.")


if __name__ == "__main__":
    # Start app on camera index 0
    app = GestureCADApp(camera_index=0)
    app.run()
