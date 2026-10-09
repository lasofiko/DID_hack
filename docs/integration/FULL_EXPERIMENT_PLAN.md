# Reproducible full experiment plan

Status: PLANNED, NOT EXECUTED. The matrix has 60 runs:
EASY/MEDIUM/HARD x Baseline/Adaptive x Algorithmic/LLM x seeds 1,2,3,4,5.
Manifest: `experiments/plans/final-matrix.json`.
Generator: `python3 scripts/prepare_experiment_matrix.py --output NEW_PLAN.json`.
The generator only writes a plan and refuses overwrite; it cannot start a mission.

## Conditions and pairing

Use scientific `configs/agent.json`, never agent-demo.json: translation 0.12 m/s,
rotation 0.4 rad/s, default approach gain 0.8, unchanged SafetyManager, watchdog,
freshness, energy reserve 8 and return_factor 1.5. The manifest records config,
map and runtime hashes. Same scenario/seed/planner makes a Baseline/Adaptive pair.
Both members must use identical maps, initial pose (-2,-0.5, yaw 0), battery 60,
sample generation seed, source image/config and provider settings. Reset all
mission, energy-learning, planner/history and judge state before each member;
do not transfer fitted EnergyModel between runs. Pair order alternates by seed.

Use one ROS domain 42, one simulator and one velocity publisher. Stop the current
demo safely and save its evidence before switching to the scientific profile.
Build an image from the final dev revision once before the campaign: the current
demo uses opt-in bind mounts, and merely removing the overlay can reveal older
image modules. Verify image source hashes and actual ROS config_file afterwards.
Do not change lidar rate, physics timestep, rendering/safety/config midway through
a pair. Record RTF; invalid sensor freshness or coordinate mismatch invalidates
the run. EASY uses the configured sample target, MEDIUM/HARD use 5/7; never compare
different scenarios as the same paired task.

## Execution protocol for the future runner

1. Inspect terminal state and save previous result; do not start a second mission.
2. POST `/api/missions/reset` using the manifest row's `session` JSON. Require idle,
   fresh sensors, clean energy state, initial battery/pose and matching config/map.
3. Subscribe to public ROS state, odometry, TwistStamped, events and knowledge,
   plus public backend WS. Record full per-run agent journal by run_id. Start via
   POST `/api/missions` with the same payload; match the returned UUID throughout.
4. Observe until terminal state. Native mission timeout remains 900 seconds;
   observer limit is 945 seconds, allowing native return/termination to complete.
   At external deadline issue штатный Stop; never silently reset/delete evidence.
5. Capture final counters, odometry path, wall and simulation elapsed times,
   battery used = initial minus final, all replan events from the full journal,
   reason, safety events, physical distance to base, and settled zero commands.
   Return succeeds only with finished and physical distance <= base_tolerance.
6. Write one fresh JSON for every run, including failed/blocked runs. Preserve
   raw journal and timestamps separately. Do not overwrite or silently rerun a
   failure. A rerun receives another campaign/attempt id and retains the failure.

Paths: `experiments/runs/full-matrix/<campaign>/<run_id>.json`; raw ROS/ML logs
beside each receipt. These directories are ignored, not committed. The manifest
does not constitute a running full-matrix harness: existing navigation_physical.py
only supports EASY/MEDIUM, seeds 1/2 and Algorithmic. Extend/validate its observer
for HARD, seeds 3-5 and real LLM before launching this campaign. No unsupported
command is presented here as a working 60-run executor.

## LLM and result interpretation

First resolve the recorded UI Start HTTP 503 and verify the updated provider
configuration separately. Use existing server-side .env via absolute --env-file;
never print/copy keys. Record public provider/model and timeout/token settings,
request counts, accepted validated provider subgoals, executed matching subgoals
and recorded outcomes. Algorithmic startup labels alone do not classify a run.

PROVIDER_EXECUTED requires actual provider exchange, accepted validated subgoal,
planner_source=LLM and matching real execution/result. Any actual offline or
Algorithmic fallback during decisions makes the row MIXED_FALLBACK or FALLBACK_ONLY,
not a successful pure LLM experiment. Provider failures/timeouts stay explicit.
Delivery/return outcome is a separate field: a real LLM reply alone is not mission
success, and an Algorithmic fallback delivery is not LLM success. Do not send
hidden judge coordinates/private events to the planner.

Each JSON must include run/campaign/source/config/map identifiers, complete
session, status/error/termination reason, initial/final battery, collected and
delivered, route/time/replans, return proof, zero-command proof, safety events,
planner source history and LLM classification. Unknown metrics stay null with
reason; absence of reported events does not prove absence of physical contacts.
Independent contacts are NOT VERIFIED unless separately instrumented. Compare
paired outcomes and energy per delivered sample only when delivered > 0.
