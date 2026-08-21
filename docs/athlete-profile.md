# Athlete profile metrics

RouteMuse builds activity-kind summaries from canonical historical activity facts.
The calculation is deterministic, provider-neutral, and does not involve an LLM.

## Included data

Callers select an inclusive local calendar-date period and an IANA timezone. The
period is converted to a half-open UTC timestamp range (`start <= timestamp <
end`) using local midnights, including daylight-saving transitions. Only records
whose timestamps fall in that range are considered. Host-dependent timezone keys
such as `localtime`, `posixrules`, and the `posix/` and `right/` namespaces are
rejected so identical inputs have identical calendar boundaries across deployments.

Activities are grouped by their normalized RouteMuse `ActivityKind`. The result
contains one `ActivityKindSummary` for each represented supported kind; it does
not create zero-filled summaries for absent kinds. A null normalized kind is
unsupported, is excluded from every supported summary, and increments
`unsupported_activities_excluded` when it falls within the selected period.

## Summary fields and units

For each represented activity kind:

- `activity_count` is the number of supported activities.
- `total_distance_meters` is the sum of activity distances, in meters.
- `total_moving_time_seconds` is the sum of moving times, in seconds.
- `total_elevation_gain_meters` is the sum of known elevation-gain samples, in
  meters, or `null` when there are no known samples.
- `elevation_sample_count` reports how many activities supplied elevation data.
- `active_weeks` is the number of distinct Monday-based local calendar weeks
  containing at least one activity of that kind.
- `median_distance_meters`, `median_moving_time_seconds`, and
  `median_elevation_gain_meters` describe the representative per-activity effort.

Activity timestamps are converted into the supplied analysis timezone before
their local week is selected. Server-local time is never used.

## Medians and missing elevation

Medians use Python's standard statistical definition. One sample is its own
median; for an even sample count, the two middle values are averaged. Zero
distance, moving time, or recorded elevation values remain valid samples.

Null elevation means unknown and is excluded from both the elevation median and
the known-elevation total. It is never converted to zero. If every elevation is
unknown, both elevation aggregates are `null`; `elevation_sample_count` is zero.
For partially known data, the total and median use only known values, and the
sample count makes that incomplete coverage explicit.

## Sparse histories

An empty period or a period containing only unsupported activities returns no
activity-kind summaries and reports zero analyzed activities. A single activity
and two-activity histories use the same formulas without special fallback
values. Sparse data remains visible through activity and elevation sample counts.

Dominant-activity selection, capability percentiles, consistency and recency
scores, route matching, and user-facing profile explanations are intentionally
defined by later athlete-profile issues.
