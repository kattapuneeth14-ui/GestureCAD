"""
State machine module for GestureCAD.
Manages application states (IDLE, DRAWING, MOVING, ROTATING, SCALING)
and performs actions corresponding to gesture inputs.
Includes debouncing, One Euro Filter, EMA smoothing, stroke interpolation,
and spring-damper physics-based interpolation.
"""

from enum import Enum, auto
from typing import List, Optional, Tuple, Dict
from collections import Counter
import random
import time
import math

from geometry import Point, Polygon
from transform3d import estimate_hand_orientation, project_points_3d_to_2d


class OneEuroFilter:
    """Adaptive low-pass filter to reduce jitter in real-time coordinate streams."""

    def __init__(
        self,
        t0: float,
        x0: float,
        dx0: float = 0.0,
        min_cutoff: float = 0.8,
        beta: float = 0.02,
        d_cutoff: float = 1.0
    ) -> None:
        self.min_cutoff: float = min_cutoff
        self.beta: float = beta
        self.d_cutoff: float = d_cutoff
        self.x_prev: float = x0
        self.dx_prev: float = dx0
        self.t_prev: float = t0

    def __call__(self, t: float, x: float) -> float:
        dt = t - self.t_prev
        if dt <= 0:
            return self.x_prev
        
        # Calculate velocity cutoff
        a_d = 1.0 / (1.0 + dt / (2.0 * math.pi * self.d_cutoff))
        dx = (x - self.x_prev) / dt
        dx_hat = a_d * dx + (1.0 - a_d) * self.dx_prev
        
        # Calculate adaptive signal cutoff
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a_s = 1.0 / (1.0 + dt / (2.0 * math.pi * cutoff))
        x_hat = a_s * x + (1.0 - a_s) * self.x_prev
        
        self.x_prev = x_hat
        self.dx_prev = dx_hat
        self.t_prev = t
        return x_hat


class State(Enum):
    IDLE = auto()
    DRAWING = auto()
    MOVING = auto()
    ROTATING = auto()
    SCALING = auto()


class StateMachine:
    """Manages the current mode of the application and handles gesture-based transitions."""

    def __init__(self) -> None:
        self.state: State = State.IDLE
        self.polygons: List[Polygon] = []  # List of all completed polygons
        self.active_polygon: Optional[Polygon] = None  # Polygon currently being drawn
        self.selected_polygon: Optional[Polygon] = None  # Polygon highlighted/selected
        self.grabbed_polygon: Optional[Polygon] = None  # Polygon being translated
        
        # Tracking references
        self.prev_cursor_pos: Optional[Point] = None
        
        # Temporal smoothing for drawing coordinates (EMA)
        self.ema_cursor: Optional[Point] = None
        self.ema_alpha: float = 0.25  # Smoothing factor (lower = smoother but slower)

        # One Euro Filters for drawing
        self.filter_x: Optional[OneEuroFilter] = None
        self.filter_y: Optional[OneEuroFilter] = None

        # Gesture debouncing history
        self.gesture_history: List[str] = []
        self.debounce_window: int = 5  # Number of frames to buffer gestures
        
        # 3D Rotation State Variables
        self.rotation_mode: bool = False
        self.last_raw_gesture: str = "UNKNOWN"
        self.gesture_duration_start: float = 0.0
        
        self.start_hand_rot: Optional[Tuple[float, float, float]] = None  # (roll, pitch, yaw)
        self.original_vertices: Optional[List[Point]] = None
        self.original_centroid: Optional[Point] = None
        self.rot_angles: List[float] = [0.0, 0.0, 0.0]      # roll (Z), pitch (X), yaw (Y)
        self.rot_velocity: List[float] = [0.0, 0.0, 0.0]    # angular velocities
        
        # Scaling State Variables
        self.start_hand_pos: Optional[Point] = None  # Tracks starting cursor position for rotate/scale
        self.start_scale_factor: float = 1.0
        self.scale_factor: float = 1.0

    def reset(self) -> None:
        """Reset the state machine and clear all graphics."""
        self.state = State.IDLE
        self.polygons.clear()
        self.active_polygon = None
        self.selected_polygon = None
        self.grabbed_polygon = None
        self.prev_cursor_pos = None
        self.ema_cursor = None
        self.filter_x = None
        self.filter_y = None
        self.gesture_history.clear()
        self.rotation_mode = False
        self.last_raw_gesture = "UNKNOWN"
        self.gesture_duration_start = 0.0
        self._clear_rotation_cache()
        self._clear_scale_cache()
        self.scale_factor = 1.0

    def clear_active(self) -> None:
        """Clear only the active polygon being drawn."""
        if self.state == State.DRAWING:
            self.active_polygon = None
            self.state = State.IDLE
            self.ema_cursor = None
            self.filter_x = None
            self.filter_y = None

    def _clear_rotation_cache(self) -> None:
        """Clear cached geometry used during active 3D rotation."""
        self.start_hand_rot = None
        self.original_vertices = None
        self.original_centroid = None
        self.rot_angles = [0.0, 0.0, 0.0]
        self.rot_velocity = [0.0, 0.0, 0.0]
        self.start_hand_pos = None

    def _clear_scale_cache(self) -> None:
        """Clear cached geometry used during active scaling."""
        self.start_hand_pos = None
        self.original_vertices = None
        self.original_centroid = None
        self.start_scale_factor = 1.0

    def _debounce_gesture(self, raw_gesture: str) -> str:
        """Buffer raw gestures and return the most common one to prevent flickering."""
        self.gesture_history.append(raw_gesture)
        if len(self.gesture_history) > self.debounce_window:
            self.gesture_history.pop(0)
        
        # Count frequencies
        counter = Counter(self.gesture_history)
        most_common = counter.most_common(1)[0][0]
        return most_common

    def update(
        self,
        raw_gesture: str,
        pinch_triggered: bool,
        cursor_pos: Point,
        landmarks_3d: List[Tuple[float, float, float]] = None,
        pixel_lms: List[Point] = None
    ) -> None:
        """
        Update the state machine according to the current hand gesture and coordinates.
        
        Args:
            raw_gesture: The raw detected gesture from the detector.
            pinch_triggered: Retained for backward compatibility (unused).
            cursor_pos: The coordinates of the cursor (index tip or palm center).
            landmarks_3d: 3D coordinates for hand orientation estimation.
            pixel_lms: Optional list of 2D screen coordinate Points for wrist-based tracking.
        """
        # Apply gesture debouncing
        gesture = self._debounce_gesture(raw_gesture)

        # Track gesture duration for Thumbs Up / Thumbs Down stability (300 ms threshold)
        t_now = time.time()
        if raw_gesture != self.last_raw_gesture:
            self.last_raw_gesture = raw_gesture
            self.gesture_duration_start = t_now
        gesture_duration = t_now - self.gesture_duration_start

        # --- Rotation Mode Toggle Controls (stable for 300ms) ---
        if raw_gesture == "THUMBS_UP" and gesture_duration >= 0.300 and not self.rotation_mode:
            self.rotation_mode = True
            print("Rotation Mode ON")
            # Automatically select the nearest completed polygon if none is selected
            if self.selected_polygon is None and self.polygons:
                nearest_poly = None
                min_dist = float("inf")
                for poly in self.polygons:
                    centroid = poly.calculate_centroid()
                    dist = cursor_pos.distance(centroid)
                    if dist < min_dist:
                        min_dist = dist
                        nearest_poly = poly
                if nearest_poly is not None and min_dist < 300.0:
                    self.selected_polygon = nearest_poly
            self._clear_rotation_cache()
            self.state = State.ROTATING

        elif raw_gesture == "THUMBS_DOWN" and gesture_duration >= 0.300 and self.rotation_mode:
            self.rotation_mode = False
            print("Rotation Mode OFF")
            if self.state == State.ROTATING:
                if self.selected_polygon is not None and self.original_vertices is not None and self.original_centroid is not None:
                    # Final project and bake
                    projected_vertices = project_points_3d_to_2d(
                        self.original_vertices,
                        self.rot_angles[0],
                        self.rot_angles[1],
                        self.rot_angles[2],
                        self.original_centroid
                    )
                    if projected_vertices:
                        self.selected_polygon.vertices = projected_vertices
                self._clear_rotation_cache()
                self.state = State.IDLE

        # Enforce ROTATING state if Rotation Mode is active
        if self.rotation_mode:
            self.state = State.ROTATING

        # --- State independent Selection Hover (except when drawing, moving, rotating, or scaling) ---
        if self.state not in [State.DRAWING, State.MOVING, State.ROTATING, State.SCALING]:
            # Detect which completed polygon is hovered
            self.selected_polygon = None
            # Search in reverse order so the top-most (most recently drawn) polygon is selected
            for poly in reversed(self.polygons):
                if poly.hit_test(cursor_pos):
                    self.selected_polygon = poly
                    break

        # --- State-specific execution & transitions ---

        # 1. State: IDLE
        if self.state == State.IDLE:
            # Transition IDLE -> DRAWING: User extends exactly one index finger
            if gesture == "ONE_FINGER":
                self.active_polygon = Polygon()
                t_now = time.time()
                self.filter_x = OneEuroFilter(t_now, cursor_pos.x, min_cutoff=0.8, beta=0.02)
                self.filter_y = OneEuroFilter(t_now, cursor_pos.y, min_cutoff=0.8, beta=0.02)
                self.ema_cursor = cursor_pos.copy()
                self.active_polygon.add_vertex(self.ema_cursor.copy())
                self.state = State.DRAWING
            
            # Transition IDLE -> MOVING: User closes fist. Select nearest polygon if near
            elif gesture == "CLOSED_FIST":
                nearest_poly = None
                min_dist = float("inf")
                
                # Find nearest completed polygon
                for poly in self.polygons:
                    centroid = poly.calculate_centroid()
                    dist = cursor_pos.distance(centroid)
                    if dist < min_dist:
                        min_dist = dist
                        nearest_poly = poly
                
                # Check proximity threshold (200 pixels) to avoid accidental grabs
                if nearest_poly is not None and min_dist < 200.0:
                    self.selected_polygon = nearest_poly
                    self.grabbed_polygon = nearest_poly
                    self.prev_cursor_pos = cursor_pos.copy()
                    self.state = State.MOVING

            # Transition IDLE -> SCALING: User shows Three Fingers with a selected polygon
            elif gesture == "THREE_FINGERS" and self.selected_polygon is not None:
                self._clear_scale_cache()
                self.state = State.SCALING

            # Interaction Finish: Open Palm deselects object and returns fully to idle
            elif gesture == "OPEN_PALM":
                self.selected_polygon = None
                self.grabbed_polygon = None

        # 2. State: DRAWING
        elif self.state == State.DRAWING:
            if gesture == "ONE_FINGER":
                t_now = time.time()
                # Initialize filters if missing
                if self.filter_x is None or self.filter_y is None:
                    self.filter_x = OneEuroFilter(t_now, cursor_pos.x, min_cutoff=0.8, beta=0.02)
                    self.filter_y = OneEuroFilter(t_now, cursor_pos.y, min_cutoff=0.8, beta=0.02)

                # 1. Apply One Euro Filter
                smooth_x = self.filter_x(t_now, cursor_pos.x)
                smooth_y = self.filter_y(t_now, cursor_pos.y)

                # 2. Apply Exponential Moving Average (EMA) to coordinate stream
                if self.ema_cursor is None:
                    self.ema_cursor = Point(smooth_x, smooth_y)
                else:
                    self.ema_cursor.x = self.ema_alpha * smooth_x + (1.0 - self.ema_alpha) * self.ema_cursor.x
                    self.ema_cursor.y = self.ema_alpha * smooth_y + (1.0 - self.ema_alpha) * self.ema_cursor.y
                
                # 3. Add point with minimum threshold & stroke interpolation
                if self.active_polygon is not None:
                    if not self.active_polygon.vertices:
                        self.active_polygon.add_vertex(self.ema_cursor.copy())
                    else:
                        last_pt = self.active_polygon.vertices[-1]
                        dist = self.ema_cursor.distance(last_pt)
                        
                        # Minimum movement threshold of 6 pixels to filter small tremors
                        if dist > 6.0:
                            # Stroke interpolation: insert intermediate points if gap is too large
                            if dist > 12.0:
                                steps = int(dist / 8.0)
                                for step in range(1, steps):
                                    t_factor = step / steps
                                    ix = last_pt.x + (self.ema_cursor.x - last_pt.x) * t_factor
                                    iy = last_pt.y + (self.ema_cursor.y - last_pt.y) * t_factor
                                    self.active_polygon.add_vertex(Point(ix, iy))
                            
                            self.active_polygon.add_vertex(self.ema_cursor.copy())
            
            # Transition DRAWING -> IDLE: Stop drawing immediately when index is no longer the only finger extended
            else:
                if self.active_polygon is not None:
                    # Automatically close the polygon if it has enough vertices
                    if len(self.active_polygon.vertices) >= 3:
                        self.active_polygon.close()
                        
                        # Set a clean random BGR color
                        b = random.randint(100, 255)
                        g = random.randint(100, 255)
                        r = random.randint(100, 255)
                        self.active_polygon.color = (b, g, r)
                        
                        self.polygons.append(self.active_polygon)
                    
                    self.active_polygon = None
                self.ema_cursor = None
                self.filter_x = None
                self.filter_y = None
                self.state = State.IDLE

        # 3. State: MOVING
        elif self.state == State.MOVING:
            # Keep translating as long as fist is closed
            if gesture == "CLOSED_FIST" and self.grabbed_polygon is not None and self.prev_cursor_pos is not None:
                # Interpolate coordinate delta to prevent snapping
                dx = (cursor_pos.x - self.prev_cursor_pos.x) * 0.8
                dy = (cursor_pos.y - self.prev_cursor_pos.y) * 0.8
                self.grabbed_polygon.translate(dx, dy)
                self.prev_cursor_pos.x += dx
                self.prev_cursor_pos.y += dy
            # Transition MOVING -> IDLE: Fist released
            else:
                self.grabbed_polygon = None
                self.prev_cursor_pos = None
                self.state = State.IDLE

        # 4. State: ROTATING
        elif self.state == State.ROTATING:
            # Continue rotating if Rotation Mode is active and selected polygon is not None
            if self.rotation_mode and self.selected_polygon is not None:
                # We track the hand if raw_gesture is not "UNKNOWN"
                if raw_gesture != "UNKNOWN":
                    # Use wrist joint (0) for highly stable translation tracking, fall back to cursor_pos
                    track_pos = pixel_lms[0].copy() if (pixel_lms and len(pixel_lms) > 0) else cursor_pos.copy()

                    if self.start_hand_pos is None:
                        self.start_hand_pos = track_pos.copy()
                        self.original_vertices = [pt.copy() for pt in self.selected_polygon.vertices]
                        self.original_centroid = self.selected_polygon.calculate_centroid()
                        self.rot_angles = [0.0, 0.0, 0.0]
                        self.rot_velocity = [0.0, 0.0, 0.0]

                    # Map horizontal/vertical translation deltas to yaw/pitch rotation angles
                    # Move Hand Left/Right -> Y-axis (Yaw)
                    # Move Hand Up/Down -> X-axis (Pitch)
                    dx = track_pos.x - self.start_hand_pos.x
                    dy = track_pos.y - self.start_hand_pos.y

                    target_yaw = dx * 0.012     # Yaw target
                    target_pitch = -dy * 0.012   # Pitch target
                    target_roll = 0.0
                else:
                    # Hand is lost. Keep current angles and decelerate.
                    # Clear start_hand_pos so it re-anchors when hand is detected again,
                    # and bake the current orientation into original_vertices so there's no snap!
                    target_yaw = self.rot_angles[2]
                    target_pitch = self.rot_angles[1]
                    target_roll = 0.0

                    if self.start_hand_pos is not None:
                        self.original_vertices = [pt.copy() for pt in self.selected_polygon.vertices]
                        self.original_centroid = self.selected_polygon.calculate_centroid()
                        self.rot_angles = [0.0, 0.0, 0.0]
                        self.start_hand_pos = None

                # Spring-damper physics equations (inertial deceleration)
                damping = 0.85
                speed = 0.15
                self.rot_velocity[0] = self.rot_velocity[0] * damping + (target_roll - self.rot_angles[0]) * speed
                self.rot_velocity[1] = self.rot_velocity[1] * damping + (target_pitch - self.rot_angles[1]) * speed
                self.rot_velocity[2] = self.rot_velocity[2] * damping + (target_yaw - self.rot_angles[2]) * speed

                self.rot_angles[0] += self.rot_velocity[0]
                self.rot_angles[1] += self.rot_velocity[1]
                self.rot_angles[2] += self.rot_velocity[2]

                # Project rotated points using perspective projection
                if self.original_vertices is not None and self.original_centroid is not None:
                    projected_vertices = project_points_3d_to_2d(
                        self.original_vertices,
                        self.rot_angles[0],
                        self.rot_angles[1],
                        self.rot_angles[2],
                        self.original_centroid
                    )
                    if projected_vertices:
                        self.selected_polygon.vertices = projected_vertices

        # 5. State: SCALING
        elif self.state == State.SCALING:
            if gesture == "THREE_FINGERS" and self.selected_polygon is not None:
                # Initialize scaling references
                if self.start_hand_pos is None:
                    self.start_hand_pos = cursor_pos.copy()
                    self.original_vertices = [pt.copy() for pt in self.selected_polygon.vertices]
                    self.original_centroid = self.selected_polygon.calculate_centroid()
                    self.start_scale_factor = self.scale_factor

                # Vertical hand delta: moving hand UP decreases y, which increases scale
                dy = cursor_pos.y - self.start_hand_pos.y
                target_scale = self.start_scale_factor - dy * 0.008
                
                # Clamping scale factor
                target_scale = max(0.2, min(4.0, target_scale))

                # Smooth scale transitions using Exponential Moving Average
                self.scale_factor = self.scale_factor * 0.88 + target_scale * 0.12

                # Apply scaling transformation relative to object centroid
                scaled_vertices = []
                for pt in self.original_vertices:
                    sx = self.original_centroid.x + (pt.x - self.original_centroid.x) * self.scale_factor
                    sy = self.original_centroid.y + (pt.y - self.original_centroid.y) * self.scale_factor
                    scaled_vertices.append(Point(sx, sy))
                
                self.selected_polygon.vertices = scaled_vertices
            
            # Transition SCALING -> IDLE: Gesture changed (Bakes scale)
            else:
                if self.selected_polygon is not None and self.original_vertices is not None and self.original_centroid is not None:
                    # Bake final scaled coordinates
                    scaled_vertices = []
                    for pt in self.original_vertices:
                        sx = self.original_centroid.x + (pt.x - self.original_centroid.x) * self.scale_factor
                        sy = self.original_centroid.y + (pt.y - self.original_centroid.y) * self.scale_factor
                        scaled_vertices.append(Point(sx, sy))
                    self.selected_polygon.vertices = scaled_vertices
                
                self._clear_scale_cache()
                self.state = State.IDLE
