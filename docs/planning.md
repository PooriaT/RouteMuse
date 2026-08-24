# Canonical route-planning request

`RoutePlanningRequest` is RouteMuse's stable, provider-independent boundary between
planner inputs and future route discovery, generation, and ranking.

## Contract

The required fields are:

- `planning_area`: a normalized `PlanningArea`, including validated WGS84 coordinates
  and optional validated bounds;
- `activity_kind`: a RouteMuse `ActivityKind`.

The optional, nullable overrides are:

- `target_distance_meters`: a finite number greater than zero;
- `target_duration_seconds`: an integer greater than zero;
- `desired_challenge`: `easy`, `moderate`, or `hard`;
- `route_shape`: `loop`, `out_and_back`, or `point_to_point`;
- `novelty_preference`: `familiar`, `balanced`, or `novel`.

Distance is always expressed in meters and duration in seconds. An omitted or `null`
override asks a future planning service to infer an appropriate value. RouteMuse does
not perform that inference yet. Challenge and novelty express athlete preferences;
they are not calculated route difficulty or novelty scores.

The contract deliberately applies no guessed athletic limits and does not reject an
unusual implied pace when both distance and duration are supplied. It rejects only
objective schema errors such as invalid coordinates, bounds, enum values, non-positive
targets, non-finite distance, boolean numeric targets, and unknown request fields.

`POST /api/v1/planning/validate` validates and returns the normalized contract. It
does not call a routing, geocoding, activity, or LLM provider and does not persist the
request. Provider adapters will eventually translate this canonical model into their
own inputs; provider payloads and options must not be added to this model.

Profile-based inference, routing, candidate generation, scoring, and persistence are
future work.

## Current planner workflow

The workflow is: (1) import history, (2) build the athlete profile, (3) select a
normalized planning area, (4) choose or override the activity type, (5) optionally
provide effort, shape, and novelty preferences, and (6) validate the canonical
request. The frontend converts kilometers and minutes in one normalization step.
Empty overrides become `null`; they do not silently insert profile percentiles or a
moderate/balanced default. Successful validation only confirms that inputs are ready.
Route generation and recommendations remain future work.
