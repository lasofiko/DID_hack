# DID LAB — Graphite / Electric Violet

## Direction
Three considered worlds: graphite/violet (precise, strong separation of controls from data), midnight/ice (calm but route and controls compete), aubergine/amber (warm, but warning hierarchy becomes harder). Selected graphite/violet with ice trajectory and amber robot. Design decisions and code-first implementation are delegated in the user's brief; no direction approval round is required.

Grounded graphic systems considered: scientific atlas, research publication, transport wayfinding, exhibition captioning, spectral notation, engineering drawings, archival index. The seed assigned fifth: spectral notation. Its transferable discipline is consistent colour semantics and an ordered low-to-high energy spectrum, never instrument decoration. Challenger service was unavailable; no catalog comparison claimed.

## Surface — Operate
Compact persistent top bar with connection, mission status and energy. Persistent command strip above map. Map owns the first screen; current decision appears alongside. Progress is tied to actual current session. Research timeline, energy inspection, diagnostics and next-session configuration follow. Presentation uses the same data with larger explanations and an observation/decision/action/result sequence.

## Tokens
CSS custom properties define surfaces, text, border, accent, success, warning, danger, information, map series, type, spacing, radii, elevation and motion. Canvas palette is authored in palette.ts and mirrored as CSS map tokens. System sans for multilingual operational UI; tabular numerals for physical data. Body 14–16px; labels 12–13px; decision 24px; projector explanation 18px. No decorative slogan or numbered cards.

## Behaviour
Stop is always visible and may queue behind a pending frontend request. No overlapping frontend dispatches. Backend operation_lock continues to serialize ROS operations. Deadlines bound frontend waiting; abort never means server cancellation. HTTP acceptance is distinct from fresh stopped telemetry. Uncertain results lock ordinary commands until telemetry demonstrates changed state or terminal state; Stop remains available.

## Map
No interpolated or extrapolated robot movement. Robot amber with explicit heading; route violet dashed; trajectory ice solid; confirmed collections amber hollow rings. Fixed display energy domain 0–12 energy units/m, explicit clamping above 12; an optional relative scale labels changing range. This is a display reference, not a terrain bound. Touch reading defaults to vertical page scrolling; explicit pan mode enables capture. Tools 44px. Text summary supplies pose, heading, route count and map availability.

## Motion
150–200ms control feedback and an authored research timeline reveal on user expansion. Critical telemetry updates immediate. No decorative loops; reduced motion disables transitions.
