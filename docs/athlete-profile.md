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
- `capability_ranges` contains typed per-metric percentile distributions for
  that activity kind. Every range contains `sample_size`, `p25`, `median`,
  `p75`, and `p90` rather than an untyped metric dictionary.

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

## Representative capability ranges

Capability ranges are calculated independently for every represented
`ActivityKind`. Hiking observations cannot affect cycling ranges, running
observations cannot affect walking pace, and the three cycling kinds remain
separate. RouteMuse does not create ranges for an activity kind absent from the
selected history.

Each range uses a deterministic linear-interpolation percentile method. The
observations are sorted and percentile `q` is located at zero-based position
`(sample_size - 1) * q`. When that position is fractional, RouteMuse linearly
interpolates between its two adjacent observations. This is a small
standard-library implementation and does not depend on NumPy, SciPy, database
percentile functions, or their defaults.

The percentiles have the following statistical interpretation:

- `median` is the athlete's typical historical per-activity effort.
- For metrics where a higher value represents more capability, such as
  distance, duration, elevation gain, climbing density, and moving speed,
  `p75` is comfortably above typical and `p90` is a strong historical
  upper-range effort, not an absolute maximum.
- `pace_seconds_per_km` has the opposite direction: fewer seconds per kilometer
  means a faster pace. Its `p25` is faster than the median, while `p75` and
  `p90` are progressively slower historical paces and must not be interpreted
  as stronger capability.

The ranges describe history only. In particular, `p90` is neither a safety
guarantee nor a route recommendation target. A maximum is not exposed as the
representative capability, so one exceptional activity can contribute to the
distribution without automatically defining the athlete's normal capability.

### Capability metrics and units

Every represented activity kind has these core ranges:

- `distance_meters`, in meters
- `moving_time_seconds`, in seconds

The following range is present when at least one activity has known elevation:

- `elevation_gain_meters`, in meters

Climbing density is exposed as `elevation_gain_meters_per_km`, in meters of
climbing per kilometer, using:

```text
elevation_gain_meters / (distance_meters / 1000)
```

Only activities with positive distance and known elevation contribute to this
range.

RouteMuse derives one activity-appropriate movement characteristic from the
canonical distance and moving-time facts:

- Walking, running, trail running, and hiking use `pace_seconds_per_km`,
  calculated as `moving_time_seconds / (distance_meters / 1000)`.
- Road cycling, gravel cycling, mountain biking, alpine skiing, backcountry
  skiing, and nordic skiing use
  `average_moving_speed_meters_per_second`, calculated as
  `distance_meters / moving_time_seconds`.

Pace and speed have distinct semantic names. Backend values remain in canonical
units; presentation conversions belong in the frontend. No power, heart rate,
technical grade, VO2 max, perceived exertion, trail difficulty, or other
physiological characteristic is inferred from these facts.

### Metric-specific missing and sparse data

Each range's `sample_size` counts only observations valid for that metric. Null
elevation is unknown rather than zero, so it contributes to neither elevation
nor climbing-density ranges. Zero distance cannot contribute to climbing
density, pace, or speed. Zero moving time remains a valid core duration sample
but cannot contribute to pace or speed.

A metric with no valid observations is `null`. With one valid observation, all
four percentile values equal that observation. With two or more observations,
the same interpolation rule applies without fallback or fabricated values. One
valid derived-metric sample is enough to return a range; its `sample_size = 1`
makes the sparsity explicit for downstream consumers.

## Sparse histories

An empty period or a period containing only unsupported activities returns no
activity-kind summaries and reports zero analyzed activities. A single activity
and two-activity histories use the same formulas without special fallback
values. Sparse data remains visible through activity and elevation sample counts.

## Dominant activity

Dominant activity is selected only from the represented supported
`ActivityKindSummary` values above. RouteMuse compares summaries
lexicographically in exactly this order:

1. `total_moving_time_seconds`, descending
2. `activity_count`, descending
3. `total_distance_meters`, descending
4. `ActivityKind.value`, ascending, as a stable technical fallback

The fourth comparison is not a product signal. It only makes an exact tie in all
three product metrics independent of input, dictionary, or database order. No
weighted or blended score is used.

`dominant_activity` contains the selected activity kind and its moving-time,
count, and distance totals copied from its summary. It also contains
`moving_time_share`, calculated as the selected kind's moving time divided by
the total moving time across represented supported summaries. When every
represented summary has zero moving time, the share is `0.0` rather than an
invented proportion.

An empty period or a period containing only unsupported activities has
`dominant_activity = null`. Unsupported activities cannot affect selection or
the moving-time denominator because they do not produce activity-kind summaries.

Consistency and recency scores, route matching, and user-facing profile
explanations are intentionally defined by later athlete-profile issues.
