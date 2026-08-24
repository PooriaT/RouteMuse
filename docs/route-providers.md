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
novelty. It is never sent directly to a provider. Future orchestration translates
only relevant values into a bounded `RouteDiscoveryRequest` and a narrow
`RoutingRequest`.

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

HTTP adapters, candidate generation, deduplication, scoring, and ranking are
intentionally deferred to issues #26 through #29.
