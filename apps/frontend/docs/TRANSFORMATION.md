# DID LAB — product design transformation

## Direction

Considered graphite/electric violet, midnight/ice blue and aubergine/warm amber. Selected graphite/violet: controls and planned route use violet, actual trajectory ice blue, robot and confirmed collections amber, danger red. The dark use scene remains; mint no longer drives the identity. Tokens cover surfaces, text, states, map colours, type, radii, spacing and motion. Native React/CSS/SVG only; no third-party components, copied assets or new dependencies.

## Before → after

| Prior audit issue | Implemented change |
|---|---|
| Stop below fold; busy blocks it | Sticky desktop strip, fixed mobile command bar; serial next-slot Stop and deduplication |
| Decorative slogan precedes work | Compact status, energy and mission strip above map |
| Current/next/history mixed | Backend session label separate from next launch; terminal reason and plan labelled historical; terminal goal marker removed |
| Mobile canvas captures scrolling | Default pan-y, explicit pan mode; 44px tools; layers/extended legend disclosed on request |
| Relative heat colour shifts silently | Default fixed 0–12 display reference; explicit relative option and explanations, clamped outliers |
| Projector explanation too small | 18px explanation and four factual observation/decision/action/result columns |
| Errors have no next step | Unknown delivery states, original diagnostics and recovery guidance |
| Canvas lacks spatial text | Actual pose, heading, map availability and path-point counts in text |

No coordinates, public API payloads, physical data, planner, EnergyModel or backend sources are changed. No robot extrapolation/interpolation is used; position changes only with telemetry. An observed judge event is displayed as the latest result, not invented causality for the current decision.

## Verification

22 Node tests and strict localization type tests pass. Production TypeScript/Vite build passes. Tests include public command payloads, seed validation, RU/TT coverage and placeholder parity, coordinate transforms/yaw/occupancy row direction, long trajectories, LLM fallback identity, errors, body/fetch deadlines, serial Stop/deduplication, fixed heat scale, post-request acknowledgement and unknown Reset, accepted Start followed immediately by failure.

Browser checks use `tests/fixture-server.mjs`, **synthetic public telemetry only**. Start, Pause, Resume, Return, Stop, Reset dialog/confirm, scenario/seed, Baseline/Adaptive and Algorithmic/LLM selections were exercised. A 3-second delayed Pause permits exactly one queued Stop; API 503 preserves original error. Failed and finished packets were inspected. Zoom/fit and explicit pan toggle work; TT persisted after reload. Fresh browser's initial connection state was observed. Offline/stale and final viewport/console measurements are recorded in VISUAL_VERIFICATION.md.

## Boundaries

Real ROS/Gazebo command delivery, physical motion stopping, physical touch/pinch, screen-reader flow, keyboard action automation and production performance profiling are not verified. Browser DOM access/focus and source keyboard handlers are inspected. A repeated browser-key automation failure was not worked around with another automation technology. Tatar terminology and extended copy require native-speaker review; all keys/placeholders are covered, technical originals remain unchanged.

Backend can still delay Stop behind an operation; genuine priority/preemption and reset-generation correlation are requested in BACKEND_STOP_REQUEST.md. No merge or backend modifications.
