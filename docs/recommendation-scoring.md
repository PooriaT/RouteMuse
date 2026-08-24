# Recommendation scoring

## Intrinsic route difficulty (`difficulty-v1`)

RouteMuse difficulty is a deterministic **product heuristic** describing the
factual challenge presented by a route. It is normalized to `0..1`, is not an
official hiking/cycling grade or safety assessment, and does not use an athlete
profile, Strava history, modeled duration, an LLM, or the other candidates in a
result set. Identical candidate facts and scoring version produce an identical
assessment.

The versioned calibration table supports walking, hiking, road cycling, gravel
cycling, and mountain biking. Other activity kinds return a controlled unsupported
scoring error until their calibrations have been reviewed. All thresholds, weights,
surface interpretations, and technical severity mappings are centralized with the
implementation so a future behavior change can introduce a new scoring version.

### Components and weights

| Component | Walking | Hiking | Road | Gravel | MTB | Meaning |
|---|---:|---:|---:|---:|---:|---|
| Distance | 35% | 25% | 35% | 30% | 20% | Route meters, piecewise-linear activity anchors |
| Elevation gain | 25% | 20% | 25% | 25% | Total meters climbed |
| Climbing density | 20% | 15% | 15% | 15% | Meters climbed per route kilometer |
| Surface | 10% | 10% | 15% | 20% | Activity-specific severity weighted by route share |
| Steepness | 10% | 10% | 10% | 10% | Climb and descent severity weighted by route share |
| Trail difficulty | — | 20% | — | — | 20% | Hiking/MTB scale severity weighted by route share |

Scalar components use bounded monotonic piecewise-linear interpolation against
fixed activity-specific anchors. Surface categories have activity-specific
severity: for example, unpaved terrain is substantially more difficult for road
cycling than gravel cycling. Severe ascent and descent labels both contribute.
Trail difficulty is used only for hiking and mountain biking, where the supplied
facts have a defensible activity-specific interpretation. Distribution scoring
uses proportions, or measured distance divided by route distance, rather than the
worst category alone.

### Missing evidence

Missing data never becomes zero. Each component reports its score (or `null`),
configured weight, evidence availability, and a factual evidence summary. Overall
difficulty renormalizes the weights of only available components. The separate
`evidence_coverage` reports how much configured weighted evidence was known;
unknown surface labels reduce coverage and are not treated as difficult. Warnings
identify missing or partial evidence. Thus a distance-only route can receive a
difficulty score without appearing as well understood as a fully described route.

`RouteCandidate.difficulty_score` is populated by the RouteMuse scoring service on
a copied candidate. Routing and discovery provider adapters continue to return
facts with all downstream recommendation scores unset.

## Athlete fit (`athlete-fit-v1`)

Athlete fit asks whether candidate facts suit the requested activity, the athlete's
representative history, current consistency, and explicit preferences. It is not
intrinsic difficulty, medical readiness, fatigue, or a technical-skill inference.
Only the profile summary and consistency signals whose `ActivityKind` exactly
matches the request and candidate are used.

### Targets and challenge anchors

The centralized v1 capability anchors are: **easy → p25**, **moderate → median**,
**hard → p90**, and **no challenge → median**. No challenge therefore means “use
my profile,” not hard and not disabled scoring. An explicit requested distance or
duration takes precedence over its challenge-derived anchor. The reusable pure
distance resolver applies exactly this precedence. Explicit targets control
target alignment but do not suppress comparison with demonstrated p90 capability.

Distance, duration (when estimated), elevation (when both sides have it), and
climbing density (when supported by the existing profile range) are separate,
explainable components. Missing evidence is omitted rather than converted to zero.
The implementation reuses profile percentiles and never calculates percentiles or
uses a historical maximum.

### Asymmetric overshoot behavior

Below a target, fit degrades gently and linearly, losing at most 35%. Above the
target it loses 35% per target multiple. Above the historical p90, a second smooth
penalty loses 90% per p90 multiple with a small floor. Consequently, one unit over
p90 does not cause a discontinuity, while a candidate far beyond representative
history is strongly penalized. When challenge is explicit and a difficulty
assessment is available, difficulty alignment to centralized targets (easy 0.25,
moderate 0.50, hard 0.80) is a small, separate preference signal; difficulty is
never inverted and treated as capability.

### Consistency, confidence, and unavailable fit

Current consistency remains separate from historical capability. Its evidence
reports active-week ratio, days since last matching activity, recent weekly moving
time, and recent-to-baseline moving-time ratio when available. Weak recent support
matters progressively more for candidates near the high end of p90; it never
changes the historical ranges and makes no injury, fatigue, or medical claim.

Confidence is RouteMuse **evidence coverage**, not scientific statistical
confidence: 45% capability sample-size support (full at ten samples per used
range), 30% usable capability dimensions, 15% matching consistency availability,
and 10% recent/baseline moving-time comparison availability. Missing duration or
elevation therefore lowers confidence. If no matching activity summary exists,
status is `insufficient_history`, score is `null`, and confidence is zero—unknown
fit is never represented as bad fit. Candidate/request activity mismatch uses
`unsupported_activity`. Only a scored assessment populates
`RouteCandidate.athlete_fit_score`; `confidence_score` remains untouched for final
recommendation orchestration.
