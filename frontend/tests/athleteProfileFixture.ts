import type {
  AthleteProfile,
  RepresentativeRange,
} from "@/types/athleteProfile";

function range(
  p25: number,
  median: number,
  p75: number,
  p90: number,
  sampleSize = 3,
): RepresentativeRange {
  return { sample_size: sampleSize, p25, median, p75, p90 };
}

export const athleteProfile: AthleteProfile = {
  period_start: "2026-01-01",
  period_end: "2026-03-31",
  timezone: "America/Vancouver",
  activities_analyzed: 5,
  unsupported_activities_excluded: 1,
  dominant_activity: {
    activity_kind: "road_cycling",
    total_moving_time_seconds: 27_000,
    activity_count: 3,
    total_distance_meters: 240_000,
    moving_time_share: 27_000 / 34_200,
  },
  activity_summaries: [
    {
      activity_kind: "road_cycling",
      activity_count: 3,
      total_distance_meters: 240_000,
      total_moving_time_seconds: 27_000,
      total_elevation_gain_meters: 2_400,
      elevation_sample_count: 3,
      active_weeks: 3,
      median_distance_meters: 80_000,
      median_moving_time_seconds: 9_000,
      median_elevation_gain_meters: 800,
      capability_ranges: {
        distance_meters: range(60_000, 80_000, 100_000, 110_000),
        moving_time_seconds: range(7_200, 9_000, 10_800, 12_000),
        elevation_gain_meters: range(500, 800, 1_000, 1_200),
        elevation_gain_meters_per_km: range(8, 10, 12, 14),
        pace_seconds_per_km: null,
        average_moving_speed_meters_per_second: range(7, 8, 9, 10),
      },
    },
    {
      activity_kind: "running",
      activity_count: 2,
      total_distance_meters: 20_000,
      total_moving_time_seconds: 7_200,
      total_elevation_gain_meters: 200,
      elevation_sample_count: 2,
      active_weeks: 2,
      median_distance_meters: 10_000,
      median_moving_time_seconds: 3_600,
      median_elevation_gain_meters: 100,
      capability_ranges: {
        distance_meters: range(8_000, 10_000, 12_000, 13_000, 2),
        moving_time_seconds: range(3_000, 3_600, 4_200, 4_500, 2),
        elevation_gain_meters: range(80, 100, 120, 130, 2),
        elevation_gain_meters_per_km: range(8, 10, 12, 13, 2),
        pace_seconds_per_km: range(300, 360, 420, 450, 2),
        average_moving_speed_meters_per_second: null,
      },
    },
  ],
  consistency_signals: [
    {
      activity_kind: "road_cycling",
      calendar_weeks: 14,
      active_week_ratio: 3 / 14,
      activities_per_week: 3 * 7 / 90,
      longest_inactivity_gap_days: 37,
      days_since_last_activity: 11,
      recency: {
        nominal_window_days: 28,
        effective_window_days: 28,
        window_start: "2026-03-04",
        window_end: "2026-03-31",
        volume: {
          activity_count: 1,
          moving_time_seconds: 10_800,
          distance_meters: 100_000,
          active_weeks: 1,
        },
        weekly_volume: {
          activities_per_week: 0.25,
          moving_time_seconds_per_week: 2_700,
          distance_meters_per_week: 25_000,
        },
        baseline: {
          period_start: "2026-01-01",
          period_end: "2026-03-03",
          effective_days: 62,
          volume: {
            activity_count: 2,
            moving_time_seconds: 16_200,
            distance_meters: 140_000,
            active_weeks: 2,
          },
          weekly_volume: {
            activities_per_week: 0.23,
            moving_time_seconds_per_week: 1_829,
            distance_meters_per_week: 15_806,
          },
        },
        recent_to_baseline: {
          activities_per_week_ratio: 1.1,
          moving_time_seconds_per_week_ratio: 0.8,
          distance_meters_per_week_ratio: 1.58,
        },
      },
    },
    {
      activity_kind: "running",
      calendar_weeks: 14,
      active_week_ratio: 2 / 14,
      activities_per_week: 2 * 7 / 90,
      longest_inactivity_gap_days: 50,
      days_since_last_activity: 6,
      recency: {
        nominal_window_days: 28,
        effective_window_days: 28,
        window_start: "2026-03-04",
        window_end: "2026-03-31",
        volume: {
          activity_count: 1,
          moving_time_seconds: 3_600,
          distance_meters: 10_000,
          active_weeks: 1,
        },
        weekly_volume: {
          activities_per_week: 0.25,
          moving_time_seconds_per_week: 900,
          distance_meters_per_week: 2_500,
        },
        baseline: null,
        recent_to_baseline: null,
      },
    },
  ],
};

export const emptyAthleteProfile: AthleteProfile = {
  period_start: "2026-01-01",
  period_end: "2026-03-31",
  timezone: "America/Vancouver",
  activities_analyzed: 0,
  unsupported_activities_excluded: 0,
  activity_summaries: [],
  dominant_activity: null,
  consistency_signals: [],
};
