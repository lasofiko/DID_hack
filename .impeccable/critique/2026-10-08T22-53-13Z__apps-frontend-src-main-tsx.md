---
target: existing DID LAB interface
total_score: 30
max_score: 40
na_heuristics:
p0_count: 0
p1_count: 0
target_identity: "file:/Users/kirito/.codex/worktrees/7d7a/DID_hack/apps/frontend/src/main.tsx"
target_fingerprint: "sha256:53c7dd3945ad5d53edf01662e9f7bade4f8be1ed2c1b9544c3d01de6566afa38"
target_path: /Users/kirito/.codex/worktrees/7d7a/DID_hack/apps/frontend/src/main.tsx
timestamp: 2026-10-08T22-53-13Z
slug: apps-frontend-src-main-tsx
---
Method: dual-agent (A: /root/design_review · B: /root/technical_evidence)

# DID LAB — short post-transformation review

Previous heuristic score: 22/40. Independent Assessment A after implementation: 30/40, provisional expert judgement, not measured certification. No new full pre-implementation audit was performed.

| Nielsen heuristic | Score /4 |
|---|---:|
| Visibility of status | 3 |
| Match to real world | 3 |
| Control and freedom | 3 |
| Consistency | 3 |
| Error prevention | 3 |
| Recognition over recall | 3 |
| Flexibility and efficiency | 3 |
| Minimalism and hierarchy | 3 |
| Diagnosis and recovery | 3 |
| Help and documentation | 3 |
| Total | 30/40 |

Product specificity: map, confirmed collections, route/trajectory and measured energy model make the work recognizably DID LAB; the new command-first hierarchy follows operator tasks. Violet controls, ice trajectory and amber robot are semantically distinct.

Strengths: persistent Stop and state strip; truthful distinction between API acceptance and telemetry; current/next/history separation and scientifically explicit energy scale. Mobile defaults to page scrolling with 44px map tools; spatial text summary supplements the canvas. Presentation exposes four actual-data stages without invented causality.

A identified mobile overlay density (P2) and accepted Start→failed recovery lock (P2). B identified unknown Reset reconciled from old idle/terminal telemetry (P1). Final fixes: collapsed layers/extended legend; reconcileCommand requires post-request telemetry and releases changed terminal state; unknown Reset requires successful completion plus fresh matching session, never an old idle frame. Dedicated regression tests pass. No remaining implementation P0/P1 from this bounded pass; backend serial-stop latency is an explicit integration limitation.

Detector: one warning, overused-font, style.css:1 (Inter). It is a weak stylistic signal, not a compliance or UX failure. Unused Inter name was removed; operational type uses the platform multilingual sans. Detector was not rerun.

Personas: operator benefits from Stop at y≈88 desktop and fixed mobile; jury receives 18px causal explanation; mobile user sees a less obstructed map; screen-reader users get live pose/heading/path summary, but full flow is unverified. Cognitive load reduced by removing slogan/repetition and disclosing layers, legend and journal categories. Error journey clearly distinguishes waiting, queued Stop, delivered API response, observed stopped state and unknown delivery.

Remaining limitations: queued Stop cannot interrupt backend lock; unknown same-session Reset cannot prove a new generation without backend correlation. Physical ROS motion, physical touch, keyboard/VoiceOver flow and production performance not verified. Tatar terms require native review. Long projector text may still require scrolling. These need integration/user validation rather than another decorative polish pass.

Validation: production TypeScript/Vite build, strict localization type tests and 22 Node tests pass. Synthetic browser checks cover commands/configuration, API error, delayed Stop queue, terminal and stale states, RU/TT persistence, map tools, energy inspection and journal empty state. No final browser console warnings/errors. CSS viewports 1920×1080, 1440×900, 1280×800, 390×844 fit horizontally. Actual JPEG dimensions checked; evidence in apps/frontend/docs/VISUAL_VERIFICATION.md.
