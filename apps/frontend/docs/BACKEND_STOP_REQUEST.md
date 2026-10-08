# Minimal backend coordination request — not implemented here

Frontend changes do not touch backend or ROS. The public endpoints and payloads are unchanged.

## Existing evidence

`apps/backend/did_backend/main.py:execute` serializes operations under `operation_lock`; `RosRuntime.command/reset/start` also use `self.lock`. ROS service discovery and result waiting can each take 5 seconds; reset readiness up to 65 seconds, start coordinate verification adds its own waits. Stop is allowed when ROS telemetry is stale, but still follows the locks. Aborting fetch does not cancel the server operation or prove robot motion stopped.

## Frontend behaviour

- One request at a time. One Stop may occupy the next slot while another request is pending; duplicate Stop is ignored.
- 12-second command deadline; 90 seconds for Start/Reset to accommodate existing reset/coordinate gates. Body reads are also bounded.
- On timeout/network/5xx/invalid successful response, delivery is unknown. No automatic ordinary retry.
- Stop remains available for observed active states even if telemetry connection is stale. API may still reject it, which is shown.
- HTTP acceptance and fresh `stopped` telemetry are distinct. The UI confirms the state, not physical zero velocity.
- Fresh post-request telemetry is required for reconciliation. An unknown same-session Reset is intentionally not resolved by unchanged idle/terminal telemetry; backend correlation is absent. Ordinary commands remain blocked. Check server/runtime externally before reloading/recovering. Never infer cancellation from a client deadline.

## Request for backend owners

1. Provide a server-owned priority Stop intent in the existing serialized operation scheduler. It should supersede *queued, not yet executed* ordinary intents and be checked at safe boundaries in long Start/Reset operations. Define whether and where the current operation can safely yield; do not remove either lock or send overlapping ROS services. Ensure a delayed Start/Resume cannot reactivate after Stop. This requires backend/agent-owner review.
2. Return operation identity and completion/result state; include a public mission-generation identity in telemetry. This permits resolving an unknown same-configuration Reset and correlating acknowledgements without guessing from timestamps. Any public API extension requires agreement.
3. Verify integration cases: Start waiting for readiness + Stop; Pause service timeout + Stop; late Start response; disconnected UI; duplicate Stop; stop rejection; Stop requested during Reset. Measure ROS stopped state and motion independently if physical-stop guarantees are desired.

No proposed ROS, MissionManager or lock-bypass patch has been applied. This document is the precise boundary of the frontend fix.
