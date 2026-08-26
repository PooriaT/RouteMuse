# Route provider contracts

```text
RoutePlanningRequest
        |
        v
RouteMuse orchestration
   /             \
Trail discovery   Routing
   \             /
     RouteCandidate
          |
          v
future deterministic scoring
```

`RoutePlanningRequest` contains product preferences such as desired challenge and
novelty. It is never sent directly to a provider. Current RouteMuse orchestration
translates only the area, activity, resolved target, and loop shape into narrow
`RoutingRequest` values; discovery remains a separate factual boundary.

Discovery returns `TrailFeature` facts. Routing returns routed candidates and
supports either two-or-more waypoints or a start plus provider-neutral round-trip
parameters (target meters, point count, and deterministic seed). These contracts
contain no Overpass queries, OSM DTOs, or openrouteservice profiles.

Both features and candidates require attributed `ProviderProvenance`. Candidate
facts may carry multiple provenance entries, typed surface/way/technical
breakdowns, warnings, and provider-data confidence. Recommendation scores remain
unset until future deterministic RouteMuse scoring. Provider failures use fixed,
safe routing error types; raw response bodies and credentials must never appear in
their messages.

The OpenRouteService Directions HTTP adapter uses this explicit translation table:

| RouteMuse `ActivityKind` | ORS Directions profile |
| --- | --- |
| `WALKING` | `foot-walking` |
| `HIKING` | `foot-hiking` |
| `ROAD_CYCLING` | `cycling-road` |
| `MOUNTAIN_BIKING` | `cycling-mountain` |
| `GRAVEL_CYCLING` | `cycling-regular` |

Gravel is initially routed with `cycling-regular`. This is a RouteMuse strategy,
not a provider-native gravel mode: ORS does not document a gravel profile. The
adapter never fabricates `cycling-gravel`, filters surfaces, or decides that a
route is gravel-suitable. Running, trail running, and skiing remain explicitly
unsupported rather than silently approximated.

It translates both waypoint and provider-neutral seeded round-trip requests
entirely within the adapter.

ORS GeoJSON FeatureCollections are validated and reduced to the canonical typed
LineString. Actual summary distance and duration remain authoritative; elevation
gain/loss remain nullable when absent. Surface, way-type, steepness, and
trail-difficulty numeric values become descriptive typed breakdowns. Provider
warnings, request identity, and response attribution (including any OpenStreetMap
contributor attribution) are retained as OpenRouteService provenance, not
represented as if Overpass supplied them.

Surface, way type, steepness, and trail difficulty are factual ORS route extras.
Unknown surface values remain unknown, and the requested round-trip distance is a
target rather than a guarantee. Provider limits are reported as controlled errors;
requests are not silently clamped. OSM `tracktype` grades (for example `grade1`)
are deliberately absent from this adapter: richer track-grade facts belong to
Overpass-discovered `TrailFeature` data and may be combined later with clear
provenance.

RouteMuse candidate orchestration is implemented outside the adapter. It requests
four candidates in at most eight sequential attempts. SHA-256 over the algorithm
version, normalized start, activity, and requested distance supplies stable per-index
32-bit seeds. Attempts use four round-trip points and repeat target factors `1.00`,
`0.90`, `1.10`, `0.95`, and `1.05`; values above the 100 km hosted ORS request bound
are not sent.

Geometry is locally projected using its latitude and an antimeridian-safe shared
longitude origin, resampled at 50-metre intervals, assigned to 40-metre cells plus
a one-cell tolerance halo, and compared as direction-independent cell sets. Jaccard
overlap at or above `0.80` is a duplicate. No-route and duplicate attempts continue
within the bound, including ORS no-route codes returned with an HTTP 500 status.
Isolated temporary failures also advance to the next bounded variant; an entirely
unavailable provider remains a controlled provider error. A nonempty shortfall
returns candidates with a controlled warning;
a zero result is a controlled error. Rate limits, authentication/configuration, and
malformed responses stop immediately. Generation provenance records algorithm
version, requested and effective distance, seed, point count, and attempt index,
while provider attribution remains separate. Scoring and ranking remain deferred,
and all recommendation fields stay unset.
