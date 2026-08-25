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

## Geographic novelty (`novelty-v1`)

Novelty asks what fraction of a candidate route the connected athlete apparently
has not travelled. It is independent of difficulty and fitness and compares all
available geographic history regardless of activity kind. A prior hike can make
the same cycling corridor geographically familiar without evidencing cycling fit.

Strava summary polylines are decoded to canonical GeoJSON before scoring. Candidate
and history share an antimeridian-safe local metric projection, are sampled every
**50 metres**, and are assigned to **40 metre cells** with a one-cell halo. This
route-scale tolerance accommodates simplified polylines and small GPS drift; it is
not metre-perfect visit detection.

```text
visited_fraction = |candidate_cells ∩ union(history_cells)| / |candidate_cells|
novelty_score = 1 - visited_fraction
```

Zero is almost entirely familiar and one almost entirely new. This asymmetric
candidate-coverage formula prevents a large history from diluting the denominator.
Evidence reports eligible, usable-geometry, and missing/unusable-geometry activity
counts and the geometry coverage ratio. With no usable geometry the status is
`insufficient_history`, score is `null`, and confidence is zero—missing history is
never automatically novel. Available-result confidence multiplies coverage by an
evidence-amount factor that reaches full support at ten geometry activities.
Scoring copies only `RouteCandidate.novelty_score`; difficulty, athlete fit, and
final `confidence_score` remain untouched.

## Explainable excitement (`excitement-v1`)

Excitement is a deterministic product heuristic, not an objective enjoyment
claim and not difficulty. It combines optional geographic novelty, surface and
way-type variety, technical/terrain variety, materially overlapping named
content, and a deliberately small route-shape heuristic. Every component exposes
its score, base weight, availability, and evidence summary; the assessment also
exposes the scoring version, warnings, and weighted evidence coverage.

| Component | Walking | Hiking | Road | Gravel | MTB |
|---|---:|---:|---:|---:|---:|
| Novelty | 25% | 24% | 25% | 24% | 22% |
| Surface variety | 17% | 15% | 10% | 21% | 16% |
| Way-type variety | 18% | 13% | 22% | 16% | 13% |
| Terrain variety | 12% | 20% | 15% | 15% | 23% |
| Named content | 20% | 20% | 20% | 16% | 18% |
| Route shape | 8% | 8% | 8% | 8% | 8% |

### Variety and named-feature matching

Variety uses route proportions (or distance divided by route distance), combines
duplicate normalized labels, excludes `unknown`-like labels, and calculates
Shannon entropy normalized against four meaningful categories. Capping the
normalizer at four keeps the scale reviewable, while proportion-aware entropy
ensures a microscopic category adds only a microscopic amount. A single category
scores zero; two balanced categories score 0.5; four balanced categories score
one. Technical variety averages independently available `steepness` and
`trail_difficulty` diversity. It never rewards the severity of a dangerous grade.

The scorer makes no Overpass request. Its optional `TrailFeature` input is matched
to the candidate with the shared 50-metre sampling/40-metre cell geometry
utilities. A named way or named-route relation must cover at least 2% of candidate
cells to be material. Evidence reports unique named features, unique route
relations, and approximate union coverage. Merely appearing in the planning box,
or being an unnamed feature without a relation, contributes nothing. A supplied
empty discovery result is factual zero named content; absent discovery context is
unavailable evidence.

### Missing evidence and non-goals

Only available components are combined, with their configured weights
renormalized. Partial distribution coverage and novelty confidence proportionally
lower `evidence_coverage`. A numeric score is withheld and
`insufficient_excitement_evidence` is emitted below the documented **0.35**
weighted coverage threshold. Missing novelty is never treated as perfect novelty,
and missing discovery is never treated as no named trails. Only a scored
assessment populates a copied `RouteCandidate.excitement_score`; final
`confidence_score` remains unset.

No component infers popularity, ratings, scenery, viewpoint quality, crowds, or
“hidden gem” status. Names and relation memberships are factual geographic
content only. The shape component does not inspect the user's requested shape;
preference alignment and final ranking remain separate concerns.
