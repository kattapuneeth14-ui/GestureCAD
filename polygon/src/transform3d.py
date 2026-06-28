"""
transform3d module for GestureCAD.
Handles 3D hand orientation estimation, 3D rotation, extrusion, and perspective projection.
"""

from typing import List, Tuple
import math
import numpy as np
from geometry import Point


def estimate_hand_orientation(landmarks_3d: List[Tuple[float, float, float]]) -> Tuple[float, float, float]:
    """
    Estimate hand orientation (roll, pitch, yaw) from 3D hand landmarks.
    
    Landmarks indices used:
    - 0: Wrist
    - 5: Index finger MCP
    - 17: Pinky finger MCP
    - 9: Middle finger MCP
    
    Returns:
        Tuple[float, float, float]: (roll, pitch, yaw) in radians.
    """
    if len(landmarks_3d) < 21:
        return 0.0, 0.0, 0.0

    # Convert landmarks to numpy arrays
    p0 = np.array(landmarks_3d[0])   # Wrist
    p5 = np.array(landmarks_3d[5])   # Index MCP
    p9 = np.array(landmarks_3d[9])   # Middle MCP
    p17 = np.array(landmarks_3d[17]) # Pinky MCP

    # Vector pointing along the hand (wrist to middle MCP)
    v_dir = p9 - p0
    v_dir_len = np.linalg.norm(v_dir)
    if v_dir_len < 1e-6:
        v_dir_len = 1.0
    v_dir = v_dir / v_dir_len

    # Vector pointing across the hand (index MCP to pinky MCP)
    v_cross = p17 - p5
    v_cross_len = np.linalg.norm(v_cross)
    if v_cross_len < 1e-6:
        v_cross_len = 1.0
    v_cross = v_cross / v_cross_len

    # Normal vector to the palm plane (Z-axis of hand)
    v_normal = np.cross(v_cross, v_dir)
    v_normal_len = np.linalg.norm(v_normal)
    if v_normal_len < 1e-6:
        v_normal_len = 1.0
    v_normal = v_normal / v_normal_len

    # Re-orthogonalize across-hand vector to ensure orthonormality
    v_cross = np.cross(v_dir, v_normal)

    # Construct the rotation matrix of the hand relative to the camera
    # Hand coordinates: X = across, Y = along, Z = normal
    R = np.column_stack((v_cross, v_dir, v_normal))

    # Extract Euler angles (roll, pitch, yaw) from rotation matrix R
    sy = math.sqrt(R[0, 0] * R[0, 0] + R[1, 0] * R[1, 0])
    singular = sy < 1e-6

    if not singular:
        pitch = math.atan2(R[2, 1], R[2, 2])
        yaw = math.atan2(-R[2, 0], sy)
        roll = math.atan2(R[1, 0], R[0, 0])
    else:
        pitch = math.atan2(-R[1, 2], R[1, 1])
        yaw = math.atan2(-R[2, 0], 0.0)
        roll = 0.0

    return roll, pitch, yaw


def get_rotation_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """
    Generate a 3D rotation matrix from roll, pitch, and yaw angles (in radians).
    Uses combined rotation: R = Rz * Ry * Rx (Euler angles / Yaw-Pitch-Roll representation)
    To avoid Gimbal Lock, calculations are matrix-multiplied as a single rotation operator.
    Optimized: constructed analytically to avoid multiple matrix allocations and multiplications.
    """
    cr = math.cos(roll)
    sr = math.sin(roll)
    cp = math.cos(pitch)
    sp = math.sin(pitch)
    cy = math.cos(yaw)
    sy = math.sin(yaw)

    # Precomputed analytical matrix multiplication R = Rz @ Ry @ Rx
    return np.array([
        [cr * cy, cr * sy * sp - sr * cp, cr * sy * cp + sr * sp],
        [sr * cy, sr * sy * sp + cr * cp, sr * sy * cp - cr * sp],
        [-sy,     cy * sp,               cy * cp]
    ], dtype=np.float64)


def get_extruded_prism_vertices(vertices_2d: List[Point], thickness: float = 60.0) -> List[Tuple[float, float, float]]:
    """
    Extrude 2D vertices along the Z-axis (thickness/depth) to form a 3D prism.
    Returns:
        List[Tuple[float, float, float]]: A list of 2*N 3D coordinates.
        The first N are on the front face (z = -thickness/2),
        the next N are on the back face (z = +thickness/2).
    """
    front_vertices = [(pt.x, pt.y, -thickness / 2.0) for pt in vertices_2d]
    back_vertices = [(pt.x, pt.y, thickness / 2.0) for pt in vertices_2d]
    return front_vertices + back_vertices


def rotate_and_project_3d_points(
    vertices_3d: List[Tuple[float, float, float]],
    roll: float,
    pitch: float,
    yaw: float,
    centroid: Point,
    focal_length: float = 600.0
) -> Tuple[List[Point], List[Tuple[float, float, float]]]:
    """
    Rotate 3D points around a centroid in 3D space, and project them to 2D screen coordinates.
    Optimized: fully vectorized using bulk NumPy matrix operations to avoid Python loop overhead.
    
    Returns:
        Tuple: (projected_2d_points: List[Point], rotated_3d_points: List[Tuple[float, float, float]])
    """
    R = get_rotation_matrix(roll, pitch, yaw)
    
    # Convert input to a single NumPy array (2N, 3)
    V = np.array(vertices_3d, dtype=np.float64)
    
    # Translate relative to centroid
    V[:, 0] -= centroid.x
    V[:, 1] -= centroid.y
    
    # Rotate all points at once: V_rot = V @ R.T
    V_rot = V @ R.T
    
    # Translate back rotated coordinates (X and Y only)
    rx = V_rot[:, 0]
    ry = V_rot[:, 1]
    rz = V_rot[:, 2]
    
    # Vectorized perspective projection
    denom = focal_length + rz
    # Avoid division by zero by setting denom to 1 or -1 if absolute value is < 1.0
    denom = np.where(np.abs(denom) < 1.0, np.where(denom >= 0, 1.0, -1.0), denom)
    
    proj_factor = focal_length / denom
    px = rx * proj_factor + centroid.x
    py = ry * proj_factor + centroid.y
    
    # Reconstruct lists for output
    projected = [Point(x, y) for x, y in zip(px, py)]
    rotated_3d = [(float(x) + centroid.x, float(y) + centroid.y, float(z)) for x, y, z in zip(rx, ry, rz)]
    
    return projected, rotated_3d


def project_points_3d_to_2d(
    vertices_2d: List[Point],
    roll: float,
    pitch: float,
    yaw: float,
    centroid: Point,
    focal_length: float = 600.0
) -> List[Point]:
    """
    Retained for backward compatibility. Projects flat 2D points rotated in 3D.
    """
    vertices_3d = [(pt.x, pt.y, 0.0) for pt in vertices_2d]
    projected, _ = rotate_and_project_3d_points(vertices_3d, roll, pitch, yaw, centroid, focal_length)
    return projected
