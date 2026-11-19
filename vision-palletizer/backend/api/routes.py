from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from palletizer.grid import calculate_place_positions
from palletizer.state_machine import PalletizerStateMachine, PalletizerState
from transforms.coordinate import camera_to_robot


router = APIRouter()
palletizer = PalletizerStateMachine()

class PalletConfig(BaseModel):
    """Configuration for palletizing operation."""
    rows: int = Field(..., ge=1, le=10, description="Number of rows in the grid")
    cols: int = Field(..., ge=1, le=10, description="Number of columns in the grid")
    box_width_mm: float = Field(..., gt=0, description="Box width in mm (X direction)")
    box_depth_mm: float = Field(..., gt=0, description="Box depth in mm (Y direction)")
    box_height_mm: float = Field(..., gt=0, description="Box height in mm (Z direction)")
    pallet_origin_x_mm: float = Field(..., description="Pallet origin X in mm")
    pallet_origin_y_mm: float = Field(..., description="Pallet origin Y in mm")
    pallet_origin_z_mm: float = Field(..., description="Pallet origin Z in mm")
    
    class Config:
        json_schema_extra = {
            "example": {
                "rows": 2,
                "cols": 2,
                "box_width_mm": 100.0,
                "box_depth_mm": 100.0,
                "box_height_mm": 50.0,
                "pallet_origin_x_mm": 400.0,
                "pallet_origin_y_mm": -200.0,
                "pallet_origin_z_mm": 100.0,
            }
        }


class VisionDetection(BaseModel):
    """Simulated vision detection of a box."""
    
    x_mm: float = Field(..., description="Box X position in camera frame (mm)")
    y_mm: float = Field(..., description="Box Y position in camera frame (mm)")
    z_mm: float = Field(..., description="Box Z position in camera frame (mm)")
    yaw_deg: Optional[float] = Field(0.0, description="Box rotation about Z (degrees)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "x_mm": 50.0,
                "y_mm": -30.0,
                "z_mm": 0.0,
                "yaw_deg": 15.0,
            }
        }


class StatusResponse(BaseModel):
    """Palletizer status response."""
    
    state: str = Field(..., description="Current state machine state")
    current_box: int = Field(..., description="Current box index (0-based)")
    total_boxes: int = Field(..., description="Total boxes to palletize")
    error: Optional[str] = Field(None, description="Error message if in FAULT state")


class ConfigResponse(BaseModel):
    """Configuration response."""
    
    success: bool
    message: str
    grid_size: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Palletizer configured: 2x2 grid, 4 boxes",
                "grid_size": "2x2",
            }
        }


class CommandResponse(BaseModel):
    """Generic command response."""
    
    success: bool
    message: str


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/configure", response_model=ConfigResponse)
async def configure_palletizer(config: PalletConfig):
    """
    Configure the palletizing operation.
    
    Sets up the grid dimensions, box size, and pallet origin.
    Can only be called when the palletizer is in IDLE state.
    """

    _grid_points = calculate_place_positions(
        config.rows,
        config.cols,
        (config.box_width_mm, config.box_depth_mm, config.box_height_mm),
        (config.pallet_origin_x_mm, config.pallet_origin_y_mm, config.pallet_origin_z_mm)
    )
    return ConfigResponse(success=True, message=f"Palletizer configured: {config.rows}x{config.cols} grid, 4 boxes", grid_size=str(len(_grid_points)))


@router.post("/start", response_model=CommandResponse)
async def start_palletizer():
    """
    Start the palletizing sequence.
    
    Begins the pick-and-place cycle. The palletizer must be configured first.
    """
    palletizer.begin()
    return CommandResponse(success=True, message="start")


@router.post("/stop", response_model=CommandResponse)
async def stop_palletizer():
    """
    Stop the palletizing sequence.
    
    Gracefully stops the operation and returns to IDLE state.
    """
    palletizer.stop()
    return CommandResponse(success=True, message="stop")


@router.post("/reset", response_model=CommandResponse)
async def reset_palletizer():
    """
    Reset from FAULT state.
    Clears the fault and returns to IDLE state.
    """
    palletizer.reset()
    return CommandResponse(success=True, message="reset")


@router.get("/status", response_model=StatusResponse)
async def get_status():
    """
    Get current palletizer status.
    
    Returns the current state, progress, and any error messages.
    """
    return StatusResponse(**palletizer.progress)


@router.post("/vision/detect", response_model=CommandResponse)
async def simulate_vision_detection(detection: VisionDetection):
    """
    Simulate a vision detection event.
    
    In a real system, this would come from the vision system.
    For this exercise, use this endpoint to simulate box detections.
    
    The coordinates are in the camera frame and must be transformed
    to the robot frame before use.
    """
    robot_point = camera_to_robot([detection.x_mm, detection.y_mm, detection.z_mm])
    palletizer.context.pick_position = tuple(float(v) for v in robot_point)
    return CommandResponse(success=True, message=f"Position={palletizer.context.pick_position}")


# ============================================================================
# Helper/Debug Endpoints (Optional)
# ============================================================================

@router.get("/debug/positions")
async def get_calculated_positions():
    """
    Debug endpoint: Get all calculated place positions.
    
    Useful for verifying grid calculations without running the full sequence.
    """
    ctx = palletizer.context
    positions = calculate_place_positions(ctx.rows, ctx.cols, ctx.box_size_mm, ctx.pallet_origin_mm)
    return {
        "rows": ctx.rows,
        "cols": ctx.cols,
        "positions_mm": [{"index": i, "x_mm": x, "y_mm": y, "z_mm": z} for i, (x, y, z) in enumerate(positions)],
    }


@router.post("/debug/transform")
async def test_transform(detection: VisionDetection):
    """
    Debug endpoint: Test coordinate transformation.
    
    Transforms the input coordinates and returns both camera and robot frame values.
    Useful for verifying transformation math.
    """
    x, y, z = camera_to_robot([detection.x_mm, detection.y_mm, detection.z_mm])
    return {
        "camera_frame": {
            "x_mm": detection.x_mm,
            "y_mm": detection.y_mm,
            "z_mm": detection.z_mm,
            "yaw_deg": detection.yaw_deg,
        },
        "robot_frame": {
            "x_mm": float(x),
            "y_mm": float(y),
            "z_mm": float(z),
        },
    }
