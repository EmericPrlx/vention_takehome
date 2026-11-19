"""
Coordinate Transformations
=========================

Transform coordinates between camera frame and robot base frame.

Refer to the README for camera mounting specifications.
"""

import numpy as np



CAM_POS = np.array([500.0, 300.0, 800.0])
CAM_ROT = (15.0, -10.0, 45.0)

def camera_to_robot(point_camera: np.ndarray) -> np.ndarray:
    """
    Transform a point from camera frame to robot base frame.
    Args:
        point_camera: [x, y, z] coordinates in camera frame (mm)
    Returns:
        [x, y, z] coordinates in robot base frame (mm)
    """
    p = np.asarray(point_camera).reshape(-1)
    rotm = build_rotation_matrix(*np.radians(CAM_ROT))
    mat4 = build_homogeneous_transform(rotm, CAM_POS)
    return (mat4 @ np.append(p, 1.0))[:3]


def robot_to_camera(point_robot: np.ndarray) -> np.ndarray:
    """
    Transform a point from robot base frame to camera frame.
    Args:
        point_robot: [x, y, z] coordinates in robot base frame (mm)
    Returns:
        [x, y, z] coordinates in camera frame (mm)
    """
    p = np.asarray(point_robot).reshape(-1)
    rotm = build_rotation_matrix(*np.radians(CAM_ROT))
    mat4 = build_homogeneous_transform(rotm.T, -rotm.T @ CAM_POS)
    return (mat4 @ np.append(p, 1.0))[:3]



def build_rotation_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """
    Build a 3x3 rotation matrix from Roll-Pitch-Yaw (Euler) angles.

    Args:
        roll: Rotation about X-axis in radians
        pitch: Rotation about Y-axis in radians
        yaw: Rotation about Z-axis in radians

    Returns:
        3x3 rotation matrix

    Notes:
        Uses the intrinsic Z -> Y -> X convention (yaw, then pitch about the
        new Y, then roll about the newest X), which composes as
        R = Rz(yaw) @ Ry(pitch) @ Rx(roll).
    """
    cr, sr = np.cos(roll), np.sin(roll)
    cp, sp = np.cos(pitch), np.sin(pitch)
    cy, sy = np.cos(yaw), np.sin(yaw)

    rx = np.array([
        [1.0, 0.0, 0.0],
        [0.0, cr, -sr],
        [0.0, sr, cr],
    ])
    ry = np.array([
        [cp, 0.0, sp],
        [0.0, 1.0, 0.0],
        [-sp, 0.0, cp],
    ])
    rz = np.array([
        [cy, -sy, 0.0],
        [sy, cy, 0.0],
        [0.0, 0.0, 1.0],
    ])

    return rz @ ry @ rx


def build_homogeneous_transform(
    rotation: np.ndarray,
    translation: np.ndarray,
) -> np.ndarray:
    """
    Build a 4x4 homogeneous transformation matrix.
    
    Args:
        rotation: 3x3 rotation matrix
        translation: 3x1 or (3,) translation vector
    
    Returns:
        4x4 homogeneous transformation matrix
    """
    rotation = np.asarray(rotation, dtype=float)
    translation = np.asarray(translation, dtype=float).reshape(-1)

    if rotation.shape != (3, 3):
        raise ValueError(f"rotation must be 3x3, got shape {rotation.shape}")
    if translation.shape != (3,):
        raise ValueError(f"translation must have 3 elements, got shape {translation.shape}")

    transform = np.eye(4)
    transform[:3, :3] = rotation
    transform[:3, 3] = translation
    return transform
