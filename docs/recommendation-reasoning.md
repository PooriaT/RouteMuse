# Recommendation reasoning

RouteMuse owns recommendation reasoning schema **`reasoning-v1`**. It is textual
enrichment of an already scored and ranked recommendation, not a source of route
facts and not an input to scoring or ranking.

## Schema

All five fields are required and unknown fields are forbidden:

| Field | Type and bound | Meaning |
| --- | --- | --- |
| `summary` | non-blank string, at most 600 characters | Concise grounded overview. |
| `reasons` | list of at most 8 non-blank strings, each at most 300 characters | Why the existing rank is appropriate, using supplied fit, target, difficulty, novelty, excitement, or confidence evidence. |
| `cautions` | list of at most 8 non-blank strings, each at most 300 characters | Supplied warnings, missing evidence, and uncertainty or coverage limits. |
| `highlights` | list of at most 8 non-blank strings, each at most 300 characters | Concise characteristics backed by supplied route evidence. |
| `qualitative_tags` | list of at most 8 enum values | Evidence-derived labels from the vocabulary below. |

The v1 qualitative vocabulary is `close_to_target`, `strong_athlete_fit`,
`high_climbing`, `mixed_surface`, `technical_terrain`, `novel`, `familiar`, and
`limited_evidence`. It intentionally excludes unsupported claims such as scenic,
popular, safe, and hidden-gem labels.

## Provider and validation boundary

The Ollama chat request is non-streaming, uses temperature zero, and passes
`RecommendationReasoning.model_json_schema()` in Ollama's `format` field. The
prompt prohibits reranking, hidden scores, changed numbers, coordinates, geometry,
and unsupported facts. Its input contains the `RankedRecommendation`, including
rank, final score, scorecard evidence, and aggregated warnings, but explicitly
omits candidate geometry and provider provenance. Trusted application code also
supplies bounded allowlists of statements and tags; final construction of those
allowlists belongs to the recommendation-enrichment wiring.

Assistant content is validated directly with Pydantic's JSON validation. RouteMuse
does not repair output, strip unknown properties, or accept Markdown wrappers.
Non-JSON, missing or extra fields, wrong types, invalid tags, blank strings, and
bound violations become `LlmMalformedResponseError`. The controlled error does not
expose generated content. After shape validation, every returned string and tag
must exactly match its field's supplied allowlist. This second validation rejects
schema-valid inventions—including unsupported safety, scenery, coordinate, or
score claims—rather than relying on prompt wording to establish trust.

The schema has no scores, rank, coordinates, waypoints, or geometry. Reasoning
therefore cannot alter deterministic scorecards or ordering and is not stored as a
factual property of `RouteCandidate`. A future schema semantic change requires a
new explicit version.
