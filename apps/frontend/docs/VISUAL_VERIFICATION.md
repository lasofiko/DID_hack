# Browser verification — 2026-10-09

All images use the local **synthetic public-API fixture**. They are not Gazebo evidence.

## Viewports and command access

| CSS viewport | Horizontal overflow | Stop placement |
|---|---|---|
| 1920×1080 | 0 | Persistent top strip |
| 1440×900 | 0 | y≈88 px, height≈44 px |
| 1280×800 | 0 | y≈88 px |
| 390×844 | 0 | y≈785 px, height≈48 px; fixed bottom bar |

Map tools measure approximately 44×44px. Default canvas touch-action is pan-y; explicit pan switches to none and switching back restores page scrolling. Physical finger interactions were not emulated. Browser keyboard automation failed; source key handlers and coordinate tests are covered, but manual keyboard flow remains unverified.

Presentation explanations are 18px. At 1920×1080 the four-part cycle ends at y≈1053; at 1440×900 its text fits, with the bottom border at y≈903. Long future reasons can require scrolling, so this is not a guarantee for every message. Stop remains accessible.

## Interaction evidence

Start → running, Pause → paused, Resume → running, Return → returning and Stop → stopped were observed. Stop confirmation text appeared after fresh telemetry. Reset's native dialog initially focused Cancel; confirming applied scenario/seed/strategy/planner to the fixture. Scenario Hard, seed 27, Adaptive and LLM selections were exercised. Actual source remained Algorithmic and was correctly labelled fallback. Three-second delayed Pause accepted one queued Stop. Synthetic API 503 retained original diagnostics and did not claim success.

Failed and finished telemetry showed historical mission/plan rather than current goal. Stopping the fixture stream caused offline/stale messaging, frozen robot position and disabled normal commands, while Stop remained available. TT selection persisted after reload. RU was restored after testing. Energy-cell inspection, relative/fixed selection and an empty journal filter were exercised. Zoom/fit and pan mode toggles were exercised; no manual drag/physical pinch or end-to-end screen-reader session was performed.

Final browser console warnings/errors: none. Vite proxy EPIPE during test fixture restart/tab closure is cleanup noise, not an application console failure.

## Contrast samples

Computed foreground/background pairs: primary text on panel 15.05:1, secondary text on background 9.16:1, enabled Stop 7.26:1, violet source on panel 7.65:1. This is a sample, not exhaustive accessibility certification.

## Screenshots

Directory: `apps/frontend/docs/screenshots/transformation/`.

- `desktop-1920.jpg` — 1920×1080.
- `desktop-1440.jpg` — 1440×900.
- `desktop-1280.jpg` — 1280×800.
- `mobile-390.jpg`, `mobile-tt.jpg` — 390×844.
- `presentation-1920.jpg` — 1920×1080.
- `presentation-1440.jpg` — 1440×900.
- `desktop-full.jpg` — full-page auxiliary capture, 1309×1736.
- `failed-mobile.jpg`, `stale-mobile-tt.jpg` — synthetic state checks, 390×844.

JPEG dimensions were checked on disk. The original visible tab had 110% zoom, so CSS dimensions were measured rather than assumed; final large exports used a fresh 100% tab and explicit viewport bounds. Temporary tabs, viewport overrides and both test servers were cleaned up. No browser overlay injection, external UI library or hidden data was used.

## Remaining boundaries

Real ROS commands and physical stopped motion, full keyboard/VoiceOver flow, physical mobile gestures, exhaustive contrast and production performance are unverified. See BACKEND_STOP_REQUEST.md for serial-stop latency and unknown-reset recovery limitations. TT terminology needs native-speaker review.
