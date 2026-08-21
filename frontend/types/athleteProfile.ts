export type ActivityKind =
  | "walking"
  | "running"
  | "trail_running"
  | "hiking"
  | "road_cycling"
  | "gravel_cycling"
  | "mountain_biking"
  | "alpine_skiing"
  | "backcountry_skiing"
  | "nordic_skiing";

export type AthleteProfileRequest = {
  start_date: string;
  end_date: string;
  timezone: string;
};

export type RepresentativeRange = {
  sample_size: number;
  p25: number;
  median: number;
  p75: number;
  p90: number;
};

export type ActivityCapabilityRanges = {
  distance_meters: RepresentativeRange;
  moving_time_seconds: RepresentativeRange;
  elevation_gain_meters: RepresentativeRange | null;
  elevation_gain_meters_per_km: RepresentativeRange | null;
  pace_seconds_per_km: RepresentativeRange | null;
  average_moving_speed_meters_per_second: RepresentativeRange | null;
};

export type ActivityKindSummary = {
  activity_kind: ActivityKind;
  activity_count: number;
  total_distance_meters: number;
  total_moving_time_seconds: number;
  total_elevation_gain_meters: number | null;
  elevation_sample_count: number;
  active_weeks: number;
  median_distance_meters: number;
  median_moving_time_seconds: number;
  median_elevation_gain_meters: number | null;
  capability_ranges: ActivityCapabilityRanges;
};

export type DominantActivity = {
  activity_kind: ActivityKind;
  total_moving_time_seconds: number;
  activity_count: number;
  total_distance_meters: number;
  moving_time_share: number;
};

export type ActivityVolume = {
  activity_count: number;
  moving_time_seconds: number;
  distance_meters: number;
  active_weeks: number;
};

export type WeeklyActivityVolume = {
  activities_per_week: number;
  moving_time_seconds_per_week: number;
  distance_meters_per_week: number;
};

export type HistoricalBaselineSignals = {
  period_start: string;
  period_end: string;
  effective_days: number;
  volume: ActivityVolume;
  weekly_volume: WeeklyActivityVolume;
};

export type RecentToBaselineRatios = {
  activities_per_week_ratio: number | null;
  moving_time_seconds_per_week_ratio: number | null;
  distance_meters_per_week_ratio: number | null;
};

export type RecencySignals = {
  nominal_window_days: number;
  effective_window_days: number;
  window_start: string;
  window_end: string;
  volume: ActivityVolume;
  weekly_volume: WeeklyActivityVolume;
  baseline: HistoricalBaselineSignals | null;
  recent_to_baseline: RecentToBaselineRatios | null;
};

export type ConsistencySignals = {
  activity_kind: ActivityKind;
  calendar_weeks: number;
  active_week_ratio: number;
  activities_per_week: number;
  longest_inactivity_gap_days: number;
  days_since_last_activity: number;
  recency: RecencySignals;
};

export type AthleteProfile = {
  period_start: string;
  period_end: string;
  timezone: string;
  activities_analyzed: number;
  unsupported_activities_excluded: number;
  activity_summaries: ActivityKindSummary[];
  dominant_activity: DominantActivity | null;
  consistency_signals: ConsistencySignals[];
};
