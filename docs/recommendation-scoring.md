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
