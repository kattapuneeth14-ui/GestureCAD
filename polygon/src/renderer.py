"""
Renderer module for GestureCAD.
Handles graphics drawing including:
- Hand landmarks and skeleton (styled dynamically based on current gesture)
- Completed polygons (transparent fills, outlines)
- Selected polygon highlights (bounding boxes, centroids)
- Active drawing preview (lines, vertices, dynamic pointer line to cursor)
"""

from typing import List, Tuple, Optional
import time
import math
import cv2
import numpy as np

# Import geometry classes
from geometry import Point, Polygon
from transform3d import get_extruded_prism_vertices, rotate_and_project_3d_points, get_rotation_matrix


class Renderer:
    """Renders all hand tracking and geometric overlays on the video frames."""

    # Joint connection indices for drawing hand skeleton
    SKELETON_CONNECTIONS = [
        # Thumb
        (0, 1), (1, 2), (2, 3), (3, 4),
        # Index
        (0, 5), (5, 6), (6, 7), (7, 8),
        # Middle
        (9, 10), (10, 11), (11, 12),
        # Ring
        (13, 14), (14, 15), (15, 16),
        # Pinky
        (0, 17), (17, 18), (18, 19), (19, 20),
        # Palm knuckle connections
        (5, 9), (9, 13), (13, 17)
    ]

    # Color palettes (BGR)
    COLOR_CYAN = (255, 255, 0)
    COLOR_WHITE = (255, 255, 255)
    COLOR_RED = (0, 0, 255)
    COLOR_YELLOW = (0, 255, 255)
    COLOR_GREEN = (0, 255, 0)
    COLOR_GRAY = (120, 120, 120)

    def __init__(self) -> None:
        # Caching structures to speed up rendering when state is unchanged
        self._prism_cache_key = None
        self._prism_cached_data = None
        self._axes_cache_key = None
        self._axes_cached_data = None

        # Rotation matrix cache
        self._cached_angles = None  # Tuple of (roll, pitch, yaw)
        self._cached_R = None       # Cached rotation matrix

        # Static polygons overlay cache
        self._static_polygons_hash = None
        self._static_overlay_fills = None
        self._static_overlay_mask = None

        # Static polygons bounding box cache
        self._static_xmin = 0
        self._static_ymin = 0
        self._static_xmax = 0
        self._static_ymax = 0

        # Shadow cache and update counter
        self._shadow_update_counter = 0
        self._cached_shadow_hull = None

        # Rate-limited profiling variables
        self._profile_counter = 0
        self._profile_time_prism = 0.0
        self._profile_time_poly = 0.0
        self._profile_time_axes = 0.0

        # Persistent rendering buffers to avoid allocation overhead in main loops
        self._overlay_fills = None
        self._alpha_mask = None
        self._mask_temp = None
        self._poly_alpha = None
        self._frame_float = None
        self._overlay_fills_uint8 = None

        # Pre-calculated constant light vector for 3D prism shading
        self._light = np.array([-0.3, -0.6, -0.7], dtype=np.float64)
        self._light /= np.linalg.norm(self._light)

    def draw_skeleton(self, frame: np.ndarray, landmarks: List[Point], gesture: str) -> None:
        """
        Draw the hand skeleton with colors indicating the active gesture.
        """
        if len(landmarks) < 21:
            return

        # Choose skeleton colors based on gesture
        if gesture == "ONE_FINGER":
            joint_color = self.COLOR_GREEN
            line_color = (180, 255, 180)  # Light Green
        elif gesture == "CLOSED_FIST":
            joint_color = (0, 100, 255)  # Orange
            line_color = (120, 180, 255)
        elif gesture == "OPEN_PALM":
            joint_color = (255, 0, 255)  # Magenta/Purple for 3D rotation
            line_color = (255, 180, 255)
        else:
            joint_color = self.COLOR_GRAY
            line_color = (200, 200, 200)

        # Draw connection lines first
        for p1_idx, p2_idx in self.SKELETON_CONNECTIONS:
            pt1 = landmarks[p1_idx].to_tuple()
            pt2 = landmarks[p2_idx].to_tuple()
            cv2.line(frame, pt1, pt2, line_color, 1, cv2.LINE_AA)

        # Draw joints
        for i, pt in enumerate(landmarks):
            center = pt.to_tuple()
            # Highlight important joints (tips)
            if i in [4, 8, 12, 16, 20]:
                cv2.circle(frame, center, 5, joint_color, -1, cv2.LINE_AA)
                cv2.circle(frame, center, 7, self.COLOR_WHITE, 1, cv2.LINE_AA)
            else:
                cv2.circle(frame, center, 3, joint_color, -1, cv2.LINE_AA)

    def draw_cursor(self, frame: np.ndarray, cursor_pos: Point, gesture: str) -> None:
        """Draw a custom interactive cursor indicator."""
        center = cursor_pos.to_tuple()
        if gesture == "ONE_FINGER":
            # Drawing a pen/hover pointer
            cv2.circle(frame, center, 4, self.COLOR_GREEN, -1, cv2.LINE_AA)
            cv2.circle(frame, center, 10, self.COLOR_GREEN, 1, cv2.LINE_AA)
        elif gesture == "CLOSED_FIST":
            # Grab cursor
            cv2.circle(frame, center, 6, (0, 165, 255), -1, cv2.LINE_AA)
            cv2.drawMarker(frame, center, (255, 255, 255), cv2.MARKER_CROSS, 12, 1)
        elif gesture == "OPEN_PALM":
            # Rotating/open hand indicator
            cv2.circle(frame, center, 6, (255, 0, 255), -1, cv2.LINE_AA)
            cv2.circle(frame, center, 14, (255, 0, 255), 1, cv2.LINE_AA)

    def draw_polygons(
        self,
        frame: np.ndarray,
        polygons: List[Polygon],
        selected_poly: Optional[Polygon] = None,
        grabbed_poly: Optional[Polygon] = None,
        state_name: str = "IDLE",
        rot_angles: Optional[List[float]] = None,
        original_vertices: Optional[List[Point]] = None,
        rotation_mode: bool = False
    ) -> None:
        """
        Draw all completed polygons with transparent fills and solid outlines.
        Switches to 3D Extruded rendering if the selected polygon is actively rotated.
        Optimized: uses a compiled, cached static overlay for non-selected/non-grabbed polygons.
        """
        start_t = time.perf_counter()

        # Separate static vs dynamic polygons
        static_polys = []
        dynamic_polys = []
        for poly in polygons:
            if poly is selected_poly or poly is grabbed_poly:
                dynamic_polys.append(poly)
            else:
                static_polys.append(poly)

        # 1. Handle Static Polygons Caching & Rendering
        static_key = tuple(
            (
                tuple((pt.x, pt.y) for pt in poly.vertices),
                poly.color,
                poly.line_thickness,
                poly.fill_alpha,
                poly.is_closed
            )
            for poly in static_polys
        )

        h, w = frame.shape[:2]
        if (static_key != self._static_polygons_hash or 
            self._static_overlay_fills is None or 
            self._static_overlay_fills.shape != (h, w, 3)):
            
            self._static_polygons_hash = static_key
            self._static_overlay_fills = np.zeros((h, w, 3), dtype=np.float32)
            self._static_overlay_mask = np.zeros((h, w), dtype=np.float32)
            
            # Temporary working arrays to avoid inner allocations
            poly_mask = np.zeros((h, w), dtype=np.uint8)
            poly_alpha_temp = np.zeros((h, w), dtype=np.float32)
            
            for poly in static_polys:
                if not poly.vertices:
                    continue
                pts = np.array([pt.to_tuple() for pt in poly.vertices], dtype=np.int32).reshape((-1, 1, 2))
                
                # Fill transparent poly
                poly_mask.fill(0)
                cv2.fillPoly(poly_mask, [pts], 255)
                np.copyto(poly_alpha_temp, poly_mask, casting='unsafe')
                poly_alpha_temp *= (poly.fill_alpha / 255.0)
                poly_alpha_3d = np.expand_dims(poly_alpha_temp, axis=2)
                
                self._static_overlay_fills *= (1.0 - poly_alpha_3d)
                self._static_overlay_fills += poly.color * poly_alpha_3d
                self._static_overlay_mask *= (1.0 - poly_alpha_temp)
                self._static_overlay_mask += poly_alpha_temp
                
                # Draw outline
                cv2.polylines(self._static_overlay_fills, [pts], True, poly.color, poly.line_thickness, cv2.LINE_AA)
                poly_mask.fill(0)
                cv2.polylines(poly_mask, [pts], True, 255, poly.line_thickness, cv2.LINE_AA)
                np.copyto(poly_alpha_temp, poly_mask, casting='unsafe')
                poly_alpha_temp *= (1.0 / 255.0)
                self._static_overlay_mask = np.maximum(self._static_overlay_mask, poly_alpha_temp)

            # Calculate combined bounding box of static polygons
            if static_polys:
                all_static_pts = []
                for poly in static_polys:
                    if poly.vertices:
                        all_static_pts.append(np.array([pt.to_tuple() for pt in poly.vertices], dtype=np.int32).reshape(-1, 2))
                if all_static_pts:
                    combined_static = np.vstack(all_static_pts)
                    self._static_xmin = max(0, int(np.min(combined_static[:, 0])) - 10)
                    self._static_ymin = max(0, int(np.min(combined_static[:, 1])) - 10)
                    self._static_xmax = min(w, int(np.max(combined_static[:, 0])) + 10)
                    self._static_ymax = min(h, int(np.max(combined_static[:, 1])) + 10)
                else:
                    self._static_xmin = self._static_ymin = self._static_xmax = self._static_ymax = 0
            else:
                self._static_xmin = self._static_ymin = self._static_xmax = self._static_ymax = 0

        # Blend static overlay onto frame (localized to the static bounding box)
        if self._static_overlay_fills is not None and self._static_polygons_hash and self._static_xmax > self._static_xmin and self._static_ymax > self._static_ymin:
            x1, y1, x2, y2 = self._static_xmin, self._static_ymin, self._static_xmax, self._static_ymax
            mask_3d = np.expand_dims(self._static_overlay_mask[y1:y2, x1:x2], axis=2)
            # Use pre-allocated float frame buffer or allocate if needed (only for static blending)
            if self._frame_float is None or self._frame_float.shape != (h, w, 3):
                self._frame_float = np.zeros((h, w, 3), dtype=np.float32)
            np.copyto(self._frame_float[y1:y2, x1:x2], frame[y1:y2, x1:x2], casting='unsafe')
            self._frame_float[y1:y2, x1:x2] *= (1.0 - mask_3d)
            self._frame_float[y1:y2, x1:x2] += self._static_overlay_fills[y1:y2, x1:x2]
            cv2.convertScaleAbs(self._frame_float[y1:y2, x1:x2], dst=frame[y1:y2, x1:x2])

        # 2. Render Dynamic Polygons
        for poly in dynamic_polys:
            if not poly.vertices:
                continue

            is_grabbed = (poly is grabbed_poly)
            is_selected = (poly is selected_poly)
            
            line_thickness = poly.line_thickness
            color = poly.color

            if is_grabbed:
                color = (0, 140, 255)  # Glowing orange when grabbed
                line_thickness = 3
            elif is_selected:
                color = (255, 120, 0) if rotation_mode else self.COLOR_YELLOW  # Glowing blue/cyan when rotation mode is active, yellow otherwise
                line_thickness = 3

            # --- Check if we should render this polygon in 3D rotation mode ---
            if is_selected and state_name == "ROTATING" and rot_angles is not None and original_vertices is not None:
                # Render premium 3D extruded prism instead of flat 2D shape
                self.draw_3d_prism(frame, original_vertices, rot_angles, poly.color, rotation_mode)
                # Render coordinates indicator
                self.draw_xyz_axes(frame, rot_angles)
                continue

            # --- 2D standard rendering for dynamic polygons ---
            pts = np.array([pt.to_tuple() for pt in poly.vertices], dtype=np.int32).reshape((-1, 1, 2))

            # Draw glowing highlight if selected/hovered (animated pulsing glow effect)
            if is_selected:
                pulse = math.sin(time.time() * 5.0)
                glow_thickness = max(4, min(14, int(8 + 3.5 * pulse)))
                glow_alpha = max(0.2, min(0.6, 0.4 + 0.15 * pulse))
                
                glow_overlay = frame.copy()
                cv2.polylines(glow_overlay, [pts], True, color, glow_thickness, cv2.LINE_AA)
                cv2.addWeighted(glow_overlay, glow_alpha, frame, 1.0 - glow_alpha, 0, frame)

            # Draw filled translucent polygon
            overlay = frame.copy()
            cv2.fillPoly(overlay, [pts], color)
            cv2.addWeighted(overlay, poly.fill_alpha, frame, 1 - poly.fill_alpha, 0, frame)

            # Draw outline
            cv2.polylines(frame, [pts], True, color, line_thickness, cv2.LINE_AA)

            # Highlight selected/grabbed polygon metadata (Centroid and Bounding Box)
            # Bounding box
            p_min, p_max = poly.get_bounding_box()
            col_bb = (200, 200, 200)
            pad = 5
            x1, y1 = int(p_min.x - pad), int(p_min.y - pad)
            x2, y2 = int(p_max.x + pad), int(p_max.y + pad)
            cv2.rectangle(frame, (x1, y1), (x2, y2), col_bb, 1, cv2.LINE_8)
            
            # Centroid
            centroid = poly.calculate_centroid()
            c_tup = centroid.to_tuple()
            # Draw small crosshair
            cv2.circle(frame, c_tup, 4, self.COLOR_WHITE, -1, cv2.LINE_AA)
            cv2.line(frame, (c_tup[0] - 8, c_tup[1]), (c_tup[0] + 8, c_tup[1]), self.COLOR_WHITE, 1)
            cv2.line(frame, (c_tup[0], c_tup[1] - 8), (c_tup[0], c_tup[1] + 8), self.COLOR_WHITE, 1)

        # Record profile times and print average every 60 frames
        self._profile_time_poly += (time.perf_counter() - start_t) * 1000.0
        self._profile_counter += 1
        if self._profile_counter >= 60:
            avg_poly = self._profile_time_poly / 60.0
            avg_prism = self._profile_time_prism / 60.0
            avg_axes = self._profile_time_axes / 60.0
            print(f"[Profiler] Avg execution times over 60 frames: draw_polygons: {avg_poly:.2f}ms, draw_3d_prism: {avg_prism:.2f}ms, draw_xyz_axes: {avg_axes:.2f}ms")
            self._profile_counter = 0
            self._profile_time_poly = 0.0
            self._profile_time_prism = 0.0
            self._profile_time_axes = 0.0

    def draw_3d_prism(
        self,
        frame: np.ndarray,
        original_vertices: List[Point],
        angles: List[float],
        color: Tuple[int, int, int],
        rotation_mode: bool = False
    ) -> None:
        """
        Extrude the 2D polygon to a 3D prism, rotate, project, and render
        with flat-shading, backface culling, and hidden edge opacities.
        Optimized: uses localized C++ blending via OpenCV,
        rotation matrix / geometry caching, shadow update throttling,
        and localized bounding box rendering to minimize CPU overhead.
        """
        start_t = time.perf_counter()
        n = len(original_vertices)
        if n < 3:
            return

        # Initialize/resize persistent buffers if size changed
        h, w = frame.shape[:2]
        if self._overlay_fills_uint8 is None or self._overlay_fills_uint8.shape != (h, w, 3):
            self._overlay_fills_uint8 = np.zeros((h, w, 3), dtype=np.uint8)
            self._mask_temp = np.zeros((h, w), dtype=np.uint8)
            self._poly_alpha = np.zeros((h, w), dtype=np.uint8)

        # 1. Check Angle Change & Rotation Matrix Cache
        is_rotating = True
        if self._cached_angles is not None:
            diff_roll = abs(angles[0] - self._cached_angles[0])
            diff_pitch = abs(angles[1] - self._cached_angles[1])
            diff_yaw = abs(angles[2] - self._cached_angles[2])
            if diff_roll < 0.008726646 and diff_pitch < 0.008726646 and diff_yaw < 0.008726646:
                is_rotating = False

        if is_rotating:
            self._cached_angles = tuple(angles)
            self._cached_R = get_rotation_matrix(angles[0], angles[1], angles[2])

        # 2. Check/Retrieve Geometry Cache
        vertices_tuple = tuple((pt.x, pt.y) for pt in original_vertices)
        cache_key = (vertices_tuple, self._cached_angles, color, rotation_mode)

        if cache_key == self._prism_cache_key:
            faces_to_render, shadow_hull, pts_front, pts_back = self._prism_cached_data
        else:
            # Recompute: perform fast vectorized NumPy operations
            thickness = 70.0
            half_t = thickness / 2.0
            
            # Original vertices as (N, 3) arrays
            pts_np = np.zeros((n, 3), dtype=np.float64)
            for idx, pt in enumerate(original_vertices):
                pts_np[idx, 0] = pt.x
                pts_np[idx, 1] = pt.y
                
            centroid_x = np.mean(pts_np[:, 0])
            centroid_y = np.mean(pts_np[:, 1])
            
            # Build 3D array of size (2*N, 3)
            V = np.zeros((2 * n, 3), dtype=np.float64)
            V[:n, :2] = pts_np[:, :2]
            V[:n, 2] = -half_t
            V[n:, :2] = pts_np[:, :2]
            V[n:, 2] = half_t
            
            # Rotate all 2*N points using the cached rotation matrix
            V_shifted = V.copy()
            V_shifted[:, 0] -= centroid_x
            V_shifted[:, 1] -= centroid_y
            
            V_rot_shifted = V_shifted @ self._cached_R.T
            
            V_rot = V_rot_shifted.copy()
            V_rot[:, 0] += centroid_x
            V_rot[:, 1] += centroid_y
            
            # Project rotated points using perspective
            focal_length = 600.0
            denom = focal_length + V_rot_shifted[:, 2]
            denom = np.where(np.abs(denom) < 1.0, np.where(denom >= 0, 1.0, -1.0), denom)
            proj = focal_length / denom
            
            proj_pts = np.zeros((2 * n, 2), dtype=np.int32)
            proj_pts[:, 0] = np.round(V_rot_shifted[:, 0] * proj + centroid_x)
            proj_pts[:, 1] = np.round(V_rot_shifted[:, 1] * proj + centroid_y)

            # Throttled shadow calculation
            if (not is_rotating) and (self._cached_shadow_hull is not None):
                shadow_hull = self._cached_shadow_hull
            else:
                self._shadow_update_counter += 1
                if (self._shadow_update_counter % 3 == 0) or (self._cached_shadow_hull is None):
                    y_ground = centroid_y + 120
                    heights = y_ground - V_rot[:, 1]
                    sxs = V_rot[:, 0] + heights * 0.18
                    szs = V_rot[:, 2] + heights * 0.12
                    
                    s_denom = focal_length + szs
                    s_denom = np.where(np.abs(s_denom) < 1.0, np.where(s_denom >= 0, 1.0, -1.0), s_denom)
                    s_proj = focal_length / s_denom
                    
                    spxs = (sxs - centroid_x) * s_proj + centroid_x
                    spys = (y_ground - centroid_y) * s_proj + centroid_y
                    
                    shadow_pts = np.stack((spxs, spys), axis=1).astype(np.int32)
                    shadow_hull = cv2.convexHull(shadow_pts)
                    self._cached_shadow_hull = shadow_hull
                else:
                    shadow_hull = self._cached_shadow_hull

            # Build list of 3D prism faces (Optimized float arithmetic, no inner NumPy allocations)
            faces = []
            light = self._light

            # 1. Front Face
            d1 = V_rot_shifted[1] - V_rot_shifted[0]
            d2 = V_rot_shifted[2] - V_rot_shifted[0]
            n_f = np.array([
                d1[1]*d2[2] - d1[2]*d2[1],
                d1[2]*d2[0] - d1[0]*d2[2],
                d1[0]*d2[1] - d1[1]*d2[0]
            ])
            norm = math.sqrt(n_f[0]**2 + n_f[1]**2 + n_f[2]**2)
            if norm > 1e-6:
                n_f /= norm
            avg_z_f = V_rot_shifted[:n, 2].mean()
            faces.append({'indices': list(range(n)), 'normal': n_f, 'avg_z': avg_z_f, 'type': 'front'})

            # 2. Back Face
            d1 = V_rot_shifted[n + 2] - V_rot_shifted[n]
            d2 = V_rot_shifted[n + 1] - V_rot_shifted[n]
            n_b = np.array([
                d1[1]*d2[2] - d1[2]*d2[1],
                d1[2]*d2[0] - d1[0]*d2[2],
                d1[0]*d2[1] - d1[1]*d2[0]
            ])
            norm = math.sqrt(n_b[0]**2 + n_b[1]**2 + n_b[2]**2)
            if norm > 1e-6:
                n_b /= norm
            avg_z_b = V_rot_shifted[n:, 2].mean()
            faces.append({'indices': list(range(n, 2 * n)), 'normal': n_b, 'avg_z': avg_z_b, 'type': 'back'})

            # 3. Side Faces
            for i in range(n):
                idx1 = i
                idx2 = (i + 1) % n
                idx3 = n + (i + 1) % n
                d1 = V_rot_shifted[idx2] - V_rot_shifted[idx1]
                d2 = V_rot_shifted[idx3] - V_rot_shifted[idx1]
                n_s = np.array([
                    d1[1]*d2[2] - d1[2]*d2[1],
                    d1[2]*d2[0] - d1[0]*d2[2],
                    d1[0]*d2[1] - d1[1]*d2[0]
                ])
                norm = math.sqrt(n_s[0]**2 + n_s[1]**2 + n_s[2]**2)
                if norm > 1e-6:
                    n_s /= norm
                avg_z_s = (V_rot_shifted[idx1, 2] + V_rot_shifted[idx2, 2] + V_rot_shifted[idx3, 2] + V_rot_shifted[n + i, 2]) * 0.25
                faces.append({'indices': [idx1, idx2, idx3, n + i], 'normal': n_s, 'avg_z': avg_z_s, 'type': 'side'})

            # Sort faces back-to-front (Painter's Algorithm)
            faces.sort(key=lambda f: f['avg_z'], reverse=True)

            faces_to_render = []
            view_origin = np.array([0.0, 0.0, -focal_length])
            
            for f in faces:
                f_indices = f['indices']
                normal = f['normal']
                avg_z = f['avg_z']

                # Calculate face center in shifted rotated space
                face_center = V_rot_shifted[f_indices].mean(axis=0)
                view_vector = face_center - view_origin
                view_norm = math.sqrt(view_vector[0]**2 + view_vector[1]**2 + view_vector[2]**2)
                if view_norm > 1e-6:
                    view_vector /= view_norm
                
                dot_view = normal[0]*view_vector[0] + normal[1]*view_vector[1] + normal[2]*view_vector[2]
                is_backface = dot_view > 0.0
                pts_2d = proj_pts[f_indices].reshape((-1, 1, 2))

                # Shading color
                dot_light = normal[0]*(-light[0]) + normal[1]*(-light[1]) + normal[2]*(-light[2])
                intensity = max(0.18, min(1.0, dot_light))
                shaded_color = (
                    int(color[0] * intensity),
                    int(color[1] * intensity),
                    int(color[2] * intensity)
                )

                # Line thickness based on depth
                line_w = max(1, min(3, int(2.5 - (avg_z / 120.0))))

                faces_to_render.append({
                    'pts_2d': pts_2d,
                    'is_backface': is_backface,
                    'shaded_color': shaded_color,
                    'line_w': line_w
                })

            # Outer glow coordinates
            pts_front = proj_pts[:n].reshape((-1, 1, 2))
            pts_back = proj_pts[n:].reshape((-1, 1, 2))

            # Cache the results
            self._prism_cache_key = cache_key
            self._prism_cached_data = (faces_to_render, shadow_hull, pts_front, pts_back)

        # 3. Draw Ground Plane Shadow (localized blend, alpha 0.28)
        if len(shadow_hull) > 0:
            x_coords = shadow_hull[:, 0, 0]
            y_coords = shadow_hull[:, 0, 1]
            x1 = max(0, np.min(x_coords))
            y1 = max(0, np.min(y_coords))
            x2 = min(w, np.max(x_coords) + 1)
            y2 = min(h, np.max(y_coords) + 1)
            
            if x2 > x1 and y2 > y1:
                local_frame = frame[y1:y2, x1:x2]
                local_mask = self._mask_temp[0:y2-y1, 0:x2-x1]
                local_mask.fill(0)
                pts_local = shadow_hull - [x1, y1]
                cv2.fillPoly(local_mask, [pts_local], 255)
                
                local_color = self._overlay_fills_uint8[0:y2-y1, 0:x2-x1]
                local_color[:] = (35, 35, 35)
                
                blended_local = cv2.addWeighted(local_color, 0.28, local_frame, 0.72, 0)
                np.copyto(local_frame, blended_local, where=(local_mask > 0)[:, :, np.newaxis])

        # 4. Render All Faces (localized blend)
        for f in faces_to_render:
            pts_2d = f['pts_2d']
            is_backface = f['is_backface']
            shaded_color = f['shaded_color']

            if len(pts_2d) < 3:
                continue

            x_coords = pts_2d[:, 0, 0]
            y_coords = pts_2d[:, 0, 1]
            x1 = max(0, np.min(x_coords))
            y1 = max(0, np.min(y_coords))
            x2 = min(w, np.max(x_coords) + 1)
            y2 = min(h, np.max(y_coords) + 1)

            if x2 > x1 and y2 > y1:
                local_frame = frame[y1:y2, x1:x2]
                local_mask = self._mask_temp[0:y2-y1, 0:x2-x1]
                local_mask.fill(0)
                pts_local = pts_2d - [x1, y1]
                cv2.fillPoly(local_mask, [pts_local], 255)
                
                local_color = self._overlay_fills_uint8[0:y2-y1, 0:x2-x1]
                local_color[:] = shaded_color
                
                alpha_val = 0.08 if is_backface else 0.5
                blended_local = cv2.addWeighted(local_color, alpha_val, local_frame, 1.0 - alpha_val, 0)
                np.copyto(local_frame, blended_local, where=(local_mask > 0)[:, :, np.newaxis])

                if is_backface:
                    # Draw hidden outline (localized blend, alpha 0.25)
                    local_mask.fill(0)
                    cv2.polylines(local_mask, [pts_local], True, 255, 1, cv2.LINE_AA)
                    
                    local_color[:] = (150, 150, 150)
                    blended_local = cv2.addWeighted(local_color, 0.25, local_frame, 0.75, 0)
                    np.copyto(local_frame, blended_local, where=(local_mask > 0)[:, :, np.newaxis])

        # 5. Draw Outer Glow Highlight (only if NOT actively rotating, localized blend)
        if not is_rotating:
            pulse = math.sin(time.time() * 5.0)
            glow_thickness = max(3, min(9, int(5 + 2 * pulse)))
            glow_alpha = max(0.25, min(0.55, 0.4 + 0.15 * pulse))
            glow_color = (255, 120, 0) if rotation_mode else self.COLOR_YELLOW
            pad = glow_thickness + 2

            # Front glow
            if len(pts_front) > 0:
                x_coords = pts_front[:, 0, 0]
                y_coords = pts_front[:, 0, 1]
                x1 = max(0, np.min(x_coords) - pad)
                y1 = max(0, np.min(y_coords) - pad)
                x2 = min(w, np.max(x_coords) + pad)
                y2 = min(h, np.max(y_coords) + pad)
                
                if x2 > x1 and y2 > y1:
                    local_frame = frame[y1:y2, x1:x2]
                    local_mask = self._mask_temp[0:y2-y1, 0:x2-x1]
                    local_mask.fill(0)
                    pts_local = pts_front - [x1, y1]
                    cv2.polylines(local_mask, [pts_local], True, 255, glow_thickness, cv2.LINE_AA)
                    
                    local_color = self._overlay_fills_uint8[0:y2-y1, 0:x2-x1]
                    local_color[:] = glow_color
                    
                    blended_local = cv2.addWeighted(local_color, glow_alpha, local_frame, 1.0 - glow_alpha, 0)
                    np.copyto(local_frame, blended_local, where=(local_mask > 0)[:, :, np.newaxis])

            # Back glow
            if len(pts_back) > 0:
                x_coords = pts_back[:, 0, 0]
                y_coords = pts_back[:, 0, 1]
                x1 = max(0, np.min(x_coords) - pad)
                y1 = max(0, np.min(y_coords) - pad)
                x2 = min(w, np.max(x_coords) + pad)
                y2 = min(h, np.max(y_coords) + pad)
                
                if x2 > x1 and y2 > y1:
                    local_frame = frame[y1:y2, x1:x2]
                    local_mask = self._mask_temp[0:y2-y1, 0:x2-x1]
                    local_mask.fill(0)
                    pts_local = pts_back - [x1, y1]
                    cv2.polylines(local_mask, [pts_local], True, 255, glow_thickness, cv2.LINE_AA)
                    
                    local_color = self._overlay_fills_uint8[0:y2-y1, 0:x2-x1]
                    local_color[:] = glow_color
                    
                    blended_local = cv2.addWeighted(local_color, glow_alpha, local_frame, 1.0 - glow_alpha, 0)
                    np.copyto(local_frame, blended_local, where=(local_mask > 0)[:, :, np.newaxis])

        # 7. Draw visible outlines directly on the frame (opaque outline overlay)
        for f in faces_to_render:
            if not f['is_backface']:
                cv2.polylines(frame, [f['pts_2d']], True, f['shaded_color'], f['line_w'], cv2.LINE_AA)

        self._profile_time_prism += (time.perf_counter() - start_t) * 1000.0

    def draw_ground_shadow(
        self,
        frame: np.ndarray,
        rotated_3d: List[Tuple[float, float, float]],
        centroid: Point,
        color: Tuple[int, int, int]
    ) -> None:
        """Retained for backward compatibility (no-op since shadow is inline-cached in draw_3d_prism)."""
        pass

    def draw_xyz_axes(
        self,
        frame: np.ndarray,
        angles: List[float]
    ) -> None:
        """
        Render a 3D coordinate axes indicator (Red-X, Green-Y, Blue-Z) in the
        bottom-right corner showing current object orientation.
        Optimized: uses trigonometric caching based on cached/quantized rotation angles and matrix.
        """
        start_t = time.perf_counter()
        height, width, _ = frame.shape
        use_angles = self._cached_angles if self._cached_angles is not None else tuple(angles)
        cache_key = (use_angles, width, height)
        
        if cache_key == self._axes_cache_key:
            pt_x, pt_y, pt_z, center_x, center_y = self._axes_cached_data
        else:
            center_x = width - 60
            center_y = height - 70
            size = 35.0

            # Reuse cached rotation matrix if available
            R = self._cached_R if self._cached_R is not None else get_rotation_matrix(angles[0], angles[1], angles[2])

            # Direction vectors for X, Y, Z axes
            u_x = np.array([size, 0.0, 0.0])
            u_y = np.array([0.0, size, 0.0])
            u_z = np.array([0.0, 0.0, size])

            # Rotate directional vectors using current Euler angle matrix
            rot_x = R @ u_x
            rot_y = R @ u_y
            rot_z = R @ u_z

            # Projects axes endpoints using orthographic mapping
            pt_x = (int(round(center_x + rot_x[0])), int(round(center_y + rot_x[1])))
            pt_y = (int(round(center_x + rot_y[0])), int(round(center_y + rot_y[1])))
            pt_z = (int(round(center_x + rot_z[0])), int(round(center_y + rot_z[1])))
            
            self._axes_cache_key = cache_key
            self._axes_cached_data = (pt_x, pt_y, pt_z, center_x, center_y)

        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.35

        # Draw Z Axis (Blue, BGR: (255, 0, 0))
        cv2.line(frame, (center_x, center_y), pt_z, (255, 0, 0), 2, cv2.LINE_AA)
        cv2.putText(frame, "Z", (pt_z[0] + 3, pt_z[1] + 3), font, font_scale, (255, 0, 0), 1, cv2.LINE_AA)

        # Draw Y Axis (Green, BGR: (0, 255, 0))
        cv2.line(frame, (center_x, center_y), pt_y, (0, 255, 0), 2, cv2.LINE_AA)
        cv2.putText(frame, "Y", (pt_y[0] + 3, pt_y[1] + 3), font, font_scale, (0, 255, 0), 1, cv2.LINE_AA)

        # Draw X Axis (Red, BGR: (0, 0, 255))
        cv2.line(frame, (center_x, center_y), pt_x, (0, 0, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, "X", (pt_x[0] + 3, pt_x[1] + 3), font, font_scale, (0, 0, 255), 1, cv2.LINE_AA)

        # Draw origin center point
        cv2.circle(frame, (center_x, center_y), 3, (240, 240, 240), -1, cv2.LINE_AA)

        self._profile_time_axes += (time.perf_counter() - start_t) * 1000.0

    def draw_active_preview(self, frame: np.ndarray, active_poly: Optional[Polygon], cursor_pos: Point) -> None:
        """
        Draw the polygon currently being drawn, along with a preview line leading to the cursor.
        """
        if active_poly is None or not active_poly.vertices:
            return

        # Draw existing vertices as orange dots
        for pt in active_poly.vertices:
            cv2.circle(frame, pt.to_tuple(), 5, (0, 165, 255), -1, cv2.LINE_AA)
            cv2.circle(frame, pt.to_tuple(), 7, self.COLOR_WHITE, 1, cv2.LINE_AA)

        # Draw lines between existing vertices
        n = len(active_poly.vertices)
        if n > 1:
            for i in range(n - 1):
                p1 = active_poly.vertices[i].to_tuple()
                p2 = active_poly.vertices[i + 1].to_tuple()
                cv2.line(frame, p1, p2, (0, 165, 255), 2, cv2.LINE_AA)

        # Draw tracking preview line from last vertex to current cursor position
        last_vertex = active_poly.vertices[-1].to_tuple()
        cursor = cursor_pos.to_tuple()
        # Dotted line approximation
        cv2.line(frame, last_vertex, cursor, (0, 200, 255), 1, cv2.LINE_AA)
        cv2.circle(frame, cursor, 3, (0, 200, 255), -1, cv2.LINE_AA)
