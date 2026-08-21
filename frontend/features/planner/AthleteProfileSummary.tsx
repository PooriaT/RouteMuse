import type {
  ActivityKindSummary,
  AthleteProfile,
  ConsistencySignals,
  RepresentativeRange,
} from "@/types/athleteProfile";

import {
  formatActivityKind,
  formatClimbingDensity,
  formatDecimal,
  formatDistance,
  formatDuration,
  formatElevation,
  formatPace,
  formatPercent,
  formatRange,
  formatSpeed,
} from "./athleteProfileFormatters";

export type AthleteProfileViewStatus =
  | "idle"
  | "loading"
  | "ready"
  | "error"
  | "partial";

type AthleteProfileSummaryProps = {
  connected: boolean | null;
  hasValidPeriod: boolean;
  profile: AthleteProfile | null;
  status: AthleteProfileViewStatus;
  error: string | null;
  onRetry: () => void;
};

export function AthleteProfileSummary({
  connected,
  hasValidPeriod,
  profile,
  status,
  error,
  onRetry,
}: AthleteProfileSummaryProps) {
  return (
    <section
      aria-labelledby="athlete-profile-heading"
      className="mb-6 rounded-xl bg-white p-6 shadow-sm"
    >
      <h2 id="athlete-profile-heading" className="text-xl font-bold">
        Athlete profile
      </h2>
      <p className="mt-2 max-w-3xl text-sm text-slate-600">
        RouteMuse will use this profile to match future routes to your
        demonstrated historical capability, activity consistency, and recent
        activity pattern. Route matching is not available yet.
      </p>

      <ProfileContent
        connected={connected}
        hasValidPeriod={hasValidPeriod}
        profile={profile}
        status={status}
        error={error}
        onRetry={onRetry}
      />
    </section>
  );
}

function ProfileContent({
  connected,
  hasValidPeriod,
  profile,
  status,
  error,
  onRetry,
}: AthleteProfileSummaryProps) {
  if (connected === null) {
    return (
      <p className="mt-5 text-sm text-slate-500">
        Your saved profile will load after RouteMuse confirms the Strava
        connection.
      </p>
    );
  }

  if (!connected) {
    return (
      <p className="mt-5 text-sm text-slate-600">
        Connect Strava to view a profile built from saved activities.
      </p>
    );
  }

  if (!hasValidPeriod) {
    return (
      <p className="mt-5 text-sm text-amber-800">
        Choose a valid historical period to load the athlete profile.
      </p>
    );
  }

  if (status === "loading") {
    return (
      <p
        role="status"
        aria-live="polite"
        className="mt-5 text-sm font-medium text-emerald-800"
      >
        Loading athlete profile…
      </p>
    );
  }

  if (status === "partial") {
    return (
      <div role="status" className="mt-5 rounded-lg bg-amber-50 p-4 text-sm text-amber-950">
        <p className="font-semibold">Profile refresh paused</p>
        <p className="mt-1">
          The latest import was partial, so RouteMuse is not presenting it as a
          definitive refreshed profile. Retry the import to completion.
        </p>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="mt-5 rounded-lg bg-red-50 p-4">
        <p role="alert" className="text-sm text-red-800">
          {error ?? "The athlete profile could not be loaded. Try again."}
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded-lg border border-red-300 bg-white px-4 py-2 text-sm font-semibold text-red-900 hover:bg-red-100"
        >
          Retry profile
        </button>
      </div>
    );
  }

  if (status !== "ready" || profile === null) {
    return null;
  }

  if (profile.activities_analyzed === 0 || profile.dominant_activity === null) {
    return (
      <div className="mt-5 rounded-lg bg-slate-50 p-4 text-sm text-slate-700">
        <p className="font-semibold">
          No supported activities are available for this period.
        </p>
        <p className="mt-1">
          Import another date range to build your athlete profile.
        </p>
        {profile.unsupported_activities_excluded > 0 && (
          <p className="mt-2 text-slate-600">
            {profile.unsupported_activities_excluded} unsupported
            {profile.unsupported_activities_excluded === 1 ? " activity was" : " activities were"}
            {" "}excluded.
          </p>
        )}
      </div>
    );
  }

  const dominantSummary = profile.activity_summaries.find(
    (summary) =>
      summary.activity_kind === profile.dominant_activity?.activity_kind,
  );
  const dominantConsistency = profile.consistency_signals.find(
    (signals) =>
      signals.activity_kind === profile.dominant_activity?.activity_kind,
  );

  return (
    <div className="mt-6 space-y-7">
      <DatasetContext profile={profile} />
      <DominantActivity profile={profile} />
      <ActivityMix profile={profile} />
      {dominantSummary && <Capability summary={dominantSummary} />}
      {dominantSummary && dominantConsistency && (
        <Consistency
          summary={dominantSummary}
          signals={dominantConsistency}
        />
      )}
    </div>
  );
}

function DatasetContext({ profile }: { profile: AthleteProfile }) {
  return (
    <div>
      <h3 className="font-bold text-slate-900">Selected history</h3>
      <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
        <Definition label="Period">
          {profile.period_start} to {profile.period_end}
        </Definition>
        <Definition label="Supported activities">
          {profile.activities_analyzed}
        </Definition>
        <Definition label="Unsupported excluded">
          {profile.unsupported_activities_excluded}
        </Definition>
      </dl>
    </div>
  );
}

function DominantActivity({ profile }: { profile: AthleteProfile }) {
  const dominant = profile.dominant_activity;
  if (!dominant) return null;
  return (
    <div>
      <h3 className="text-sm font-semibold uppercase tracking-wide text-emerald-700">
        Primary activity
      </h3>
      <p className="mt-1 text-2xl font-bold">
        {formatActivityKind(dominant.activity_kind)}
      </p>
      <p className="mt-2 text-sm text-slate-600">
        {formatPercent(dominant.moving_time_share)} of moving time ·{" "}
        {dominant.activity_count} {dominant.activity_count === 1 ? "activity" : "activities"} ·{" "}
        {formatDistance(dominant.total_distance_meters)} in the selected period
      </p>
    </div>
  );
}

function ActivityMix({ profile }: { profile: AthleteProfile }) {
  const totalMovingTime = profile.activity_summaries.reduce(
    (total, summary) => total + summary.total_moving_time_seconds,
    0,
  );
  const summaries = [...profile.activity_summaries].sort(
    (left, right) =>
      right.total_moving_time_seconds - left.total_moving_time_seconds,
  );

  return (
    <div>
      <h3 className="font-bold text-slate-900">Activity mix by moving time</h3>
      <ul className="mt-4 space-y-4">
        {summaries.map((summary) => {
          const share =
            totalMovingTime === 0
              ? 0
              : summary.total_moving_time_seconds / totalMovingTime;
          const shareText = formatPercent(share);
          return (
            <li key={summary.activity_kind}>
              <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
                <span className="font-semibold">
                  {formatActivityKind(summary.activity_kind)}
                </span>
                <span className="text-slate-700">
                  {shareText} · {formatDuration(summary.total_moving_time_seconds)} ·{" "}
                  {summary.activity_count} {summary.activity_count === 1 ? "activity" : "activities"}
                </span>
              </div>
              <div
                className="mt-1 h-3 overflow-hidden rounded-full bg-slate-200"
                aria-hidden="true"
              >
                <div
                  className="h-full rounded-full bg-emerald-700"
                  style={{ width: `${Math.max(0, Math.min(100, share * 100))}%` }}
                />
              </div>
              <p className="mt-1 text-xs text-slate-500">
                {formatDistance(summary.total_distance_meters)} ·{" "}
                {summary.total_elevation_gain_meters === null
                  ? "Elevation unavailable"
                  : `${formatElevation(summary.total_elevation_gain_meters)} elevation`} ·{" "}
                {summary.active_weeks} active {summary.active_weeks === 1 ? "week" : "weeks"}
              </p>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Capability({ summary }: { summary: ActivityKindSummary }) {
  const ranges = summary.capability_ranges;
  return (
    <div>
      <h3 className="font-bold text-slate-900">
        Representative {formatActivityKind(summary.activity_kind).toLowerCase()} capability
      </h3>
      <p className="mt-1 text-sm text-slate-600">
        Typical values show the historical p25–p75 range. Strong historical
        efforts show p90, not a maximum or safety threshold.
      </p>
      <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <RangeDefinition
          label="Typical distance"
          range={ranges.distance_meters}
          value={formatRange(ranges.distance_meters, formatDistance)}
        />
        <RangeDefinition
          label="Strong historical distance"
          range={ranges.distance_meters}
          value={formatDistance(ranges.distance_meters.p90)}
        />
        <RangeDefinition
          label="Typical duration"
          range={ranges.moving_time_seconds}
          value={formatRange(ranges.moving_time_seconds, formatDuration)}
        />
        <RangeDefinition
          label="Strong historical duration"
          range={ranges.moving_time_seconds}
          value={formatDuration(ranges.moving_time_seconds.p90)}
        />
        {ranges.elevation_gain_meters && (
          <>
            <RangeDefinition
              label="Typical elevation"
              range={ranges.elevation_gain_meters}
              value={formatRange(ranges.elevation_gain_meters, formatElevation)}
            />
            <RangeDefinition
              label="Strong historical elevation"
              range={ranges.elevation_gain_meters}
              value={formatElevation(ranges.elevation_gain_meters.p90)}
            />
          </>
        )}
        {ranges.elevation_gain_meters_per_km && (
          <RangeDefinition
            label="Typical climbing density"
            range={ranges.elevation_gain_meters_per_km}
            value={formatRange(
              ranges.elevation_gain_meters_per_km,
              formatClimbingDensity,
            )}
          />
        )}
        {ranges.pace_seconds_per_km && (
          <RangeDefinition
            label="Typical historical pace"
            range={ranges.pace_seconds_per_km}
            value={formatRange(ranges.pace_seconds_per_km, formatPace)}
          />
        )}
        {ranges.average_moving_speed_meters_per_second && (
          <>
            <RangeDefinition
              label="Typical moving speed"
              range={ranges.average_moving_speed_meters_per_second}
              value={formatRange(
                ranges.average_moving_speed_meters_per_second,
                formatSpeed,
              )}
            />
            <RangeDefinition
              label="Strong historical moving speed"
              range={ranges.average_moving_speed_meters_per_second}
              value={formatSpeed(
                ranges.average_moving_speed_meters_per_second.p90,
              )}
            />
          </>
        )}
      </dl>
    </div>
  );
}

function Consistency({
  summary,
  signals,
}: {
  summary: ActivityKindSummary;
  signals: ConsistencySignals;
}) {
  const recent = signals.recency;
  const baselineRatio =
    recent.recent_to_baseline?.moving_time_seconds_per_week_ratio;
  return (
    <div>
      <h3 className="font-bold text-slate-900">Consistency and recency</h3>
      <p className="mt-1 text-sm text-slate-600">
        Descriptive signals for {formatActivityKind(summary.activity_kind).toLowerCase()};
        they do not diagnose fitness, fatigue, or readiness.
      </p>
      <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Definition label="Active weeks">
          {summary.active_weeks} of {signals.calendar_weeks} ({formatPercent(signals.active_week_ratio)})
        </Definition>
        <Definition label="Activities per week">
          {formatDecimal(signals.activities_per_week)}
        </Definition>
        <Definition label="Days since last activity">
          {signals.days_since_last_activity}
        </Definition>
        <Definition label="Longest inactivity gap">
          {signals.longest_inactivity_gap_days} days
        </Definition>
        <Definition label={`Recent activity (${recent.effective_window_days} days)`}>
          {recent.volume.activity_count} {recent.volume.activity_count === 1 ? "activity" : "activities"}, {" "}
          {formatDistance(recent.volume.distance_meters)}, {" "}
          {formatDuration(recent.volume.moving_time_seconds)}
        </Definition>
        <Definition label="Recent vs baseline moving time">
          {baselineRatio === null || baselineRatio === undefined
            ? "Comparison unavailable"
            : `${formatPercent(baselineRatio)} of baseline weekly volume`}
        </Definition>
      </dl>
    </div>
  );
}

function Definition({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg bg-slate-50 p-3">
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </dt>
      <dd className="mt-1 font-semibold text-slate-900">{children}</dd>
    </div>
  );
}

function RangeDefinition({
  label,
  range,
  value,
}: {
  label: string;
  range: RepresentativeRange;
  value: string;
}) {
  return (
    <Definition label={label}>
      {value}
      <span className="mt-1 block text-xs font-normal text-slate-500">
        {range.sample_size} {range.sample_size === 1 ? "sample" : "samples"}
      </span>
    </Definition>
  );
}
