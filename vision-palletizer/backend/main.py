"""
Vision Palletizer Backend
========================

FastAPI application for coordinating UR5e robot palletizing operations.
"""

from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

from robot.connection import RobotConnection
from palletizer.state_machine import PalletizerStateMachine
from api.routes import router as palletizer_router




@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle.

    Creates the robot connection and the palletizer state machine, and stores
    them on app.state so route callbacks receive them through dependencies.
    """
    # Startup: Initialize robot connection (will auto-reconnect later if needed)
    robot_connection = RobotConnection()
    connected = robot_connection.connect()

    if connected:
        print("✓ Robot connection established")
    else:
        print("⚠ Robot not available yet - will auto-reconnect when robot is powered on")
        print("  → Power on the robot in PolyScope, then call /health to connect")

    # app.state.robot_connection = robot_connection
    app.state.palletizer = PalletizerStateMachine(robot_connection)

    yield

    # Shutdown: Clean up robot connection
    robot_connection.disconnect()
    print("✓ Robot connection closed")


app = FastAPI(
    title="Vision Palletizer API",
    description="API for controlling UR5e palletizing operations with vision-based picking",
    version="1.0.0",
    lifespan=lifespan,
)


# Include palletizer routes
app.include_router(palletizer_router, prefix="/palletizer", tags=["Palletizer"])


@app.get("/health")
async def health_check(request: Request):
    """
    Check API and robot connection health.

    This endpoint also attempts to reconnect to the robot if disconnected,
    so you can use it to verify when the robot becomes available after
    powering it on in PolyScope.
    """
    robot_connection: RobotConnection = request.app.state.palletizer.motion.connection
    robot_status = "connected" if robot_connection.check_and_reconnect() else "disconnected"
    return {
        "status": "healthy",
        "robot": robot_status,
    }


@app.get("/")
async def root():
    """API root - redirect to docs."""
    return {
        "message": "Vision Palletizer API",
        "docs": "/docs",
        "health": "/health",
    }
