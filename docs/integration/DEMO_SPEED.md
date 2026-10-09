# Opt-in TurtleBot3 demo profile

Scientific `configs/agent.json` remains unchanged: 0.12 m/s, 0.4 rad/s.
Demo `configs/agent-demo.json`: 0.18 m/s, 0.8 rad/s; linear approach gain 1.6
instead of the scientific default 0.8. These are command limits, not a measured
50% improvement of total mission duration.

The controller preserves turn/move hysteresis, zero commands at phase changes,
goal/base tolerances and A* straight-segment compression/segment collision checks.
Translation is bounded to leave half the target tolerance over two control ticks.
SafetyManager, watchdog, sensor freshness and energy/return gates remain enabled.

After ensuring no active mission, use the existing built Jazzy/Python 3.12 image:

```sh
docker compose --env-file /Users/kirito/Desktop/DID_hack/.env -f compose.yaml -f compose.demo.yaml -p did-final-integration up -d --no-build --force-recreate
```

The overlay mounts only the demo JSON, controller/config modules and backend
config selection. Backend passes DID_AGENT_CONFIG as ROS launch config_file and
uses the same file for its coordinate gate. No frontend, LLM or EnergyModel edits.
Future clean builds include these modules normally. The overlay paths target the
verified Jazzy image's installed Python 3.12 package layout.

To restore scientific configuration, first Stop and preserve measurements, then
recreate with only compose.yaml, without compose.demo.yaml.

Fast checks: core/navigation reliability/energy/backend 66/66 PASS; demo profile
regressions 3/3 PASS. Initial test import/bootstrap errors were fixed before these
final results. Gazebo idle RTF measured from /clock over 4 seconds: 0.993935.
The existing headless llvmpipe setup needs no simulation acceleration adjustment;
sensor rates/physics stepping were not changed.

Short real ROS/Gazebo result is stored locally in
`experiments/runs/docker/demo-speed-proof.json`, with command/odometry maxima,
actual ROS config_file, measured RTF, return status, collision events and Stop
proof. Its scope is a short motion test with mock judge, not a full delivery
mission or independent contact instrumentation. See the final measured result
below; raw evidence remains excluded from Git.

Measured short run: PASS, 46.619 s including reset and verification. ROS agent
config_file was /workspace/DID_hack/configs/agent-demo.json. Actual maximum
odometry translation was 0.180000 m/s; command maxima 0.18 m/s and 0.8 rad/s.
Motion RTF 0.990195. Measured path 1.13038 m, rotation 7.88024 rad. Return
finished at physical base distance 0.157318 m (tolerance 0.18 m). Afterwards:
75 zero TwistStamped, physical stop slip 0.0 m, zero reported collision events.
No independent contact instrumentation was added. This run checked zero commands
after finished/return; operator Stop while moving at demo speed was not separately
tested before the user's request to start the demonstration immediately.
Compared with scientific limits, translation cap increases 50%, rotation cap
100%. Total mission speedup was not measured with a paired run.
