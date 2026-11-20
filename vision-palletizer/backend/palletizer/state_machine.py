"""
Palletizer State Machine

Manages the lifecycle of palletizing operations using vention-state-machine.
Documentation: https://docs.vention.io/docs/state-machine
"""
import asyncio
import json

from enum import Enum, auto
from pathlib import Path
from typing import Callable, Optional
from dataclasses import dataclass, field


from state_machine.core import StateMachine, BaseTriggers
from state_machine.defs import StateGroup, State, Trigger
from state_machine.decorators import on_enter_state, on_state_change

from .grid import calculate_place_positions
from robot.connection import RobotConnection
from robot.motion import MotionController, mm2m
from transforms.coordinate import camera_to_robot


# Mocked vision output (camera frame, mm). Resolved from this file so it does not depend on the working directory.
DETECTIONS_FILE = Path(__file__).resolve().parent.parent / "data" / "camera_detections.json"


def load_detections(path: Path = DETECTIONS_FILE) -> list[dict]:
    """Load camera-frame box detections (x_mm, y_mm, z_mm, yaw_deg) from a vision output JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return list(json.load(f)["detections"])


class PalletizerState(Enum):
    """Palletizer operation states."""
    IDLE = auto()
    HOMING = auto()
    PICKING = auto()
    PLACING = auto()
    FAULT = auto()


class Running(StateGroup):
    """Active operation states."""
    homing: State = State()
    picking: State = State()
    placing: State = State()


class States:
    running = Running()


class Triggers:
    """Named events that initiate transitions."""
    finished_homing = Trigger("finished_homing")
    finished_picking = Trigger("finished_picking")
    finished_placing = Trigger("finished_placing")
    cycle_complete = Trigger("cycle_complete")
    stop = Trigger("stop")


TRANSITIONS = [
    Trigger("start").transition("ready", States.running.homing),
    Triggers.finished_homing.transition(States.running.homing, States.running.picking),
    Triggers.finished_picking.transition(States.running.picking, States.running.placing),
    Triggers.finished_placing.transition(States.running.placing, States.running.picking),
    Triggers.cycle_complete.transition(States.running.placing, "ready"),
    Triggers.stop.transition(States.running.homing, "ready"),
    Triggers.stop.transition(States.running.picking, "ready"),
    Triggers.stop.transition(States.running.placing, "ready"),
]


@dataclass
class PalletizerContext:
    """Shared context for state machine operations."""
    rows: int = 2
    cols: int = 2
    box_size_mm: tuple[float, float, float] = (100.0, 100.0, 50.0)
    pallet_origin_mm: tuple[float, float, float] = (400.0, -200.0, 100.0)
    spacing_mm: float = 10.0
    current_box_index: int = 0
    total_boxes: int = 0
    pick_position: Optional[tuple[float, float, float]] = None  # current pick, robot frame (mm)
    place_positions: list[tuple[float, float, float]] = field(default_factory=list)  # robot frame (mm)
    detections: list[dict] = field(default_factory=list)  # pending vision detections, camera frame (mm)
    error_message: str = ""


class PalletizerStateMachine(StateMachine):
    """
    State machine for palletizing operations.

    Robot motions are blocking, so each running state spawns an async task that
    executes its motion in a worker thread and fires the next trigger when done.
    Triggers must therefore be fired from a running event loop (the API routes).

    Usage:
        machine = PalletizerStateMachine(robot_connection)
        machine.configure(2, 2, (100.0, 100.0, 50.0), (400.0, -200.0, 100.0))
        machine.begin()  # Transitions to HOMING, then runs the cycle in the background
    """

    def __init__(self, connection: RobotConnection):
        super().__init__(
            states=States,
            transitions=TRANSITIONS,
            enable_last_state_recovery=False,
        )
        self.context = PalletizerContext()
        self.motion = MotionController(connection)
        self._step_task: Optional[asyncio.Task] = None

    @property
    def current_state(self) -> PalletizerState:
        """Get current state. Note: library uses format 'Running_homing' not 'running.homing'."""
        state_str = self.state
        mapping = {
            "ready": PalletizerState.IDLE,
            "fault": PalletizerState.FAULT,
            "Running_homing": PalletizerState.HOMING,
            "Running_picking": PalletizerState.PICKING,
            "Running_placing": PalletizerState.PLACING,
        }
        return mapping.get(state_str, PalletizerState.IDLE)

    @property
    def progress(self) -> dict:
        """Get current progress: state, current_box, total_boxes, error."""
        return {
            "state": self.current_state.name,
            "current_box": self.context.current_box_index,
            "total_boxes": self.context.total_boxes,
            "error": self.context.error_message if self.context.error_message else None,
        }

    @property
    def start_blocker(self) -> Optional[str]:
        """Reason the sequence cannot start right now, or None if it can."""
        if self.current_state != PalletizerState.IDLE:
            return f"state is {self.current_state.name}"
        if not self.context.place_positions:
            return "palletizer is not configured"
        if self._step_task is not None and not self._step_task.done():
            return "previous robot motion is still finishing"
        return None

    def configure(
        self,
        rows: int,
        cols: int,
        box_size_mm: tuple[float, float, float],
        pallet_origin_mm: tuple[float, float, float],
        spacing_mm: float = 10.0,
    ) -> bool:
        """Configure palletizing parameters. Only valid in IDLE state."""
        if self.current_state != PalletizerState.IDLE:
            return False

        self.context.rows = rows
        self.context.cols = cols
        self.context.box_size_mm = box_size_mm
        self.context.pallet_origin_mm = pallet_origin_mm
        self.context.spacing_mm = spacing_mm
        self.context.total_boxes = rows * cols
        self.context.current_box_index = 0
        self.context.place_positions = calculate_place_positions(
            rows, cols, box_size_mm, pallet_origin_mm, spacing_mm
        )
        return True

    def begin(self) -> bool:
        """Start the palletizing sequence."""
        blocker = self.start_blocker
        if blocker is not None:
            print(f"[PALLETIZER] Cannot start: {blocker}")
            return False
        try:
            # Use detections queued through the API, otherwise fall back to the vision output file
            if not self.context.detections:
                self.context.detections = load_detections()
            self.context.current_box_index = 0
            self.context.pick_position = None
            self.context.error_message = ""
            self.trigger("start")
            return True
        except Exception as e:
            print(f"[PALLETIZER] Start failed: {e}")
            return False

    def stop(self) -> bool:
        """
        Stop the palletizing sequence and return to IDLE.

        Graceful: the motion in progress completes, then the sequence halts
        because the machine is no longer in the state that started it.
        """
        if self.current_state == PalletizerState.IDLE:
            return True
        try:
            self.trigger("stop")
            return True
        except Exception as e:
            print(f"[PALLETIZER] Stop failed: {e}")
            return False

    def reset(self) -> bool:
        """Reset from FAULT state to IDLE, then move the robot home."""
        try:
            self.trigger(BaseTriggers.RESET.value)
        except Exception as e:
            print(f"[PALLETIZER] Reset refused: {e}")
            return False
        self.context.error_message = ""
        self._step_task = self.spawn(self._run_step(self._home_after_reset, self.state))
        return True

    def fault(self, message: str) -> bool:
        """Transition to FAULT state with an error message."""
        self.context.error_message = message
        try:
            self.trigger(BaseTriggers.TO_FAULT.value)
            return True
        except Exception as e:
            print(f"[PALLETIZER] Fault transition failed: {e}")
            return False

    # State Entry Callbacks: each one runs its robot step in the background

    @on_enter_state(States.running.homing)
    def on_enter_homing(self, _):
        """Move the robot home, then continue to picking."""
        self._step_task = self.spawn(self._run_step(self._home, self.state))

    @on_enter_state(States.running.picking)
    def on_enter_picking(self, _):
        """Pick the next detected box, then continue to placing."""
        self._step_task = self.spawn(self._run_step(self._pick, self.state))

    @on_enter_state(States.running.placing)
    def on_enter_placing(self, _):
        """Place the box on the next grid position, then pick again or complete the cycle."""
        self._step_task = self.spawn(self._run_step(self._place, self.state))

    @on_state_change
    def on_any_state_change(self, old_state: str, new_state: str, trigger: str):
        """Called on every state transition. Useful for logging."""
        print(f"[PALLETIZER] {old_state} -> {new_state} ({trigger})")

    # Background step execution

    async def _run_step(self, step: Callable[[], Optional[str]], state_name: str) -> None:
        """
        Run a blocking robot step in a worker thread so the API stays responsive,
        then fire the trigger it returns (None: nothing to fire).

        A failed step sends the machine to FAULT. If the machine left `state_name`
        while the robot was moving (stop or fault), the sequence halts there.
        """
        try:
            next_trigger = await asyncio.to_thread(step)
            if self.state != state_name:
                print(f"[PALLETIZER] Left {state_name} during motion (now {self.state}), sequence halted")
                return
            if next_trigger is not None:
                self.trigger(next_trigger)
        except Exception as e:
            print(f"[PALLETIZER] {state_name} failed: {e}")
            self.fault(str(e))

    def _home(self) -> Optional[str]:
        if not self.motion.move_to_home():
            raise RuntimeError("Homing motion failed")
        return "finished_homing"

    def _home_after_reset(self) -> Optional[str]:
        if not self.motion.move_to_home():
            raise RuntimeError("Homing after reset failed")
        return None

    def _pick(self) -> Optional[str]:
        """Take the next detection, transform it to the robot frame and pick the box there."""
        box = self.context.current_box_index + 1
        if not self.context.detections:
            raise RuntimeError(f"No vision detection available for box {box}")
        detection = self.context.detections.pop(0)
        point_mm = camera_to_robot([detection["x_mm"], detection["y_mm"], detection["z_mm"]])
        self.context.pick_position = tuple(float(v) for v in point_mm)
        if not self.motion.move_to_pick(mm2m(point_mm)):
            raise RuntimeError(f"Pick motion failed for box {box} at {self.context.pick_position} mm")
        return "finished_picking"

    def _place(self) -> Optional[str]:
        """Place the held box on the current grid position and advance the box index."""
        index = self.context.current_box_index
        target_mm = self.context.place_positions[index]
        if not self.motion.move_to_place(mm2m(target_mm)):
            raise RuntimeError(f"Place motion failed for box {index + 1} at {target_mm} mm")
        self.context.current_box_index = index + 1
        if self.context.current_box_index < self.context.total_boxes:
            return "finished_placing"
        return "cycle_complete"
