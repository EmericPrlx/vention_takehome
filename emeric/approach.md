Vision Palletizer: approach and assumptions

# Structure
Kept the template layout, even if the single-file packages looked odd to me at first. The API is the high-level interface. The robot connection and the state machine are created in main.py's lifespan and handed to the routes through a FastAPI dependency, since I prefer passing objects around over module-level globals. The state machine owns the MotionController and the palletizing context. /configure delegates to it because the IDLE-only rule lives there, and the place positions are computed once at configure time.

# Assumptions
- The README camera pose is the camera frame expressed in the robot base frame. Intrinsic Z->Y->X gives R = Rz(yaw) Ry(pitch) Rx(roll) and T = [R | t]. robot_to_camera uses the inverse [R^T | -R^T t].
- pallet_origin_mm is the pallet corner, not the first box center. Each place target is the top center of its box: columns along X (box width), rows along Y (box depth), z = origin z + box height, filled row by row. Spacing is the gap between boxes (10 mm default, configurable).
- The app works in mm (API, grid, transforms, state machine). Conversion to m happens only when moves are sent to the robot. The home position is kept in joint degrees, as PolyScope shows it, and converted to radians.
- Tool pointing straight down ([0, pi, 0]), approach 100 mm above pick and place targets. The gripper stays mocked.
- Detections are consumed in order: the ones posted to /vision/detect first, otherwise the JSON file. No detection left means FAULT.
- Targets are checked with ur_rtde's safety-limit functions before each move. A failed move sends the machine to FAULT, reset homes the robot, and /stop lets the current move finish before halting. Refused commands return success=false with a reason.

# Issues I had
- First time with the UR platform: URSim and PolyScope through noVNC, RTDE and the ur_rtde API, axis-angle orientations.
- First time with vention-state-machine. My first version fired the next trigger from inside the on_enter callbacks, which runs the whole cycle inside the /start request and blocks /status and /stop. Each step now runs its motion in the background.
- Keeping frames and units straight between the vision data (camera frame, mm) and the robot (base frame, m).
- Smaller things: Python relative imports across packages, FastAPI lifespan and dependency wiring.

# Other
- LLMs were allowed, but I tried to keep their use to a minimum, which probably gave me more work than needed. I used one mostly for code reviews, plus a few pieces: the rotation and homogeneous transform helpers, the route dependency wiring and some API response handling. Near the end, short on time, I let it do a correction pass on the state machine (background execution, unit conversion, fault/stop/reset handling). The conversation is in ref/transcript_llm.md.
- Not done: Bonus 11, 13; 12 only goes as far as ur_rtde's safety-limit checks.
- I changed the camera points in the video so it would actually do something interesting, they were not within the valid space I had assumed.