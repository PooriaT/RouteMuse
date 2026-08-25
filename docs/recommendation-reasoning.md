# Recommendation reasoning

RouteMuse owns the bounded output schema **`reasoning-v1`** and the separate,
provider-neutral input schema **`reasoning-context-v1`**. Reasoning is textual
enrichment of an already scored and ranked recommendation, never a source of facts
or an input to scoring.

## Output schema

All fields are required and unknown fields are forbidden. `summary` is a non-blank
string of at most 600 characters. `reasons`, `cautions`, and `highlights` each hold
at most eight non-blank 300-character strings. `qualitative_tags` holds at most
eight values from `close_to_target`, `strong_athlete_fit`, `high_climbing`,
`mixed_surface`, `technical_terrain`, `novel`, `familiar`, and
`limited_evidence`. The output has no numeric or geometry fields.

## Input schema and unknowns

`RecommendationReasoningContext` has typed `recommendation`,
`planning_preferences`, `athlete`, `route_facts`, `scorecard`, and
`evidence_limitations` sections.

* Recommendation contains authoritative `rank`, `final_score`, and
  `ranking_version` only.
* Planning preferences contain activity, normalized distance/duration targets,
  challenge, shape, novelty preference, and planning-area display name.
* Athlete contains only the requested activity kind: matching sample count;
  `p25`, `median`, `p75`, and `p90` distance, moving-time, elevation, and climbing
  density distributions; and aggregate consistency/recency signals when present.
* Route facts contain name, activity, distance, duration, elevation gain/loss,
  shape, data confidence, normalized breakdowns, and useful clipped provenance.
* Scorecard contains the existing difficulty, athlete-fit, novelty, excitement,
  preference-alignment, confidence, and final values plus component evidence.
  Novelty retains status, nullable score, confidence, and geometry coverage ratio.
* Evidence limitations contain existing deterministic/provider warnings and
  explicit truncation flags.

The pure builder never recalculates a score. Missing information remains JSON
`null`, accompanied where applicable by status/availability. Missing elevation is
not zero, unavailable novelty is not one, and omitted confidence remains unknown.

## Bounds

V1 allows at most 8 surfaces, 8 way types, 12 technical entries, 8 provenance
entries, 24 score components, and 16 warnings. Breakdown distances and proportions
are first normalized to comparable route shares, then sorted by decreasing share
and stable labels before truncation; provenance and warnings also sort stably.
Externally influenced strings are clipped at 300 characters with
`…[truncated]`, and flags expose clipping/truncation. A final 32,000-character
serialized JSON ceiling raises `ReasoningContextConstructionError` rather than
sending oversized input. No tokenizer is involved.

## Provider and prompt-injection boundary

Ollama receives the context JSON in a user message and the Pydantic-generated
output JSON Schema. A separate system message says rank is authoritative and
immutable; prohibits reranking, score calculation, changed numbers, geometry, and
invented facts; preserves unknowns; grounds cautions in supplied limitations; and
forbids unsupported safety, access, weather, popularity, and scenery claims.
Route/area/provider names and warnings are untrusted structured data and are never
concatenated into the privileged system message.

Ollama never receives candidate geometry, GeoJSON references, coordinates,
waypoints, planning-area coordinates/bounds, individual activities, activity IDs,
raw timestamps, OAuth data, HTTP headers, provider request/source IDs, API URLs,
credentials, raw ORS/Overpass payloads, generation provenance, or blindly dumped
planning/profile/candidate objects. Assistant content is strictly validated as
JSON against `RecommendationReasoning`; malformed results become a controlled
error without exposing generated content. Schema-valid output is then checked
against deterministic grounding: every returned statement must exactly match a
projected component evidence summary or warning, and every qualitative tag must be
supported by the corresponding score, availability, or route fact. Unsupported
safety prose and tags such as `high_climbing` with unknown elevation are rejected.


## Recommendation integration and fallback

Reasoning runs after factual generation, deterministic scoring and ranking, and diversity selection. Every selected `RankedRecommendation` receives an envelope with `source`, the strict `reasoning-v1` value, `schema_version`, `context_version`, and an optional model name. Sources are `ollama` and `deterministic_fallback`; connection URLs are never exposed.

Unconfigured Ollama skips networking. Controlled timeout, connectivity, model, HTTP, malformed-response, and schema-validation failures add one safe result warning and use fallback. Calls are sequential and bounded by the selected count. Any failure, including invalid structured output, disables Ollama for the remainder of that request to avoid repeated expensive failures.

The pure fallback formats known rank, activity, distance, elevation, and athlete fit; selects bounded reasons in athlete-fit, preference, challenge, novelty, excitement, and confidence order; carries known warnings into cautions; and highlights only known route facts. Qualitative tags use centralized explicit thresholds. It performs no I/O and reads no clock or random state.

Reasoning never feeds back into scores, ranks, assessments, or diversity. Optional reasoning degradation therefore cannot change successful API status. Routing, history, generation, scoring, and database errors keep their existing behavior.
