import type { ActivityKind, RepresentativeRange } from "@/types/athleteProfile";

const activityLabels: Record<ActivityKind, string> = {
  walking: "Walking",
  running: "Running",
  trail_running: "Trail running",
  hiking: "Hiking",
  road_cycling: "Road cycling",
  gravel_cycling: "Gravel cycling",
  mountain_biking: "Mountain biking",
  alpine_skiing: "Alpine skiing",
  backcountry_skiing: "Backcountry skiing",
  nordic_skiing: "Nordic skiing",
};

export function formatActivityKind(kind: ActivityKind) {
  return activityLabels[kind];
}

export function formatDistance(meters: number) {
  const kilometers = meters / 1_000;
  return `${formatNumber(kilometers, kilometers < 10 ? 1 : 0)} km`;
}

export function formatDuration(seconds: number) {
  const roundedMinutes = Math.round(seconds / 60);
  const hours = Math.floor(roundedMinutes / 60);
  const minutes = roundedMinutes % 60;
  if (hours === 0) return `${minutes} min`;
  if (minutes === 0) return `${hours} hr`;
  return `${hours} hr ${minutes} min`;
}

export function formatElevation(meters: number) {
  return `${formatNumber(meters, 0)} m`;
}

export function formatClimbingDensity(metersPerKm: number) {
  return `${formatNumber(metersPerKm, 0)} m/km`;
}

export function formatPace(secondsPerKm: number) {
  const roundedSeconds = Math.round(secondsPerKm);
  const minutes = Math.floor(roundedSeconds / 60);
  const seconds = String(roundedSeconds % 60).padStart(2, "0");
  return `${minutes}:${seconds} min/km`;
}

export function formatSpeed(metersPerSecond: number) {
  return `${formatNumber(metersPerSecond * 3.6, 1)} km/h`;
}

export function formatPercent(fraction: number) {
  return `${Math.round(fraction * 100)}%`;
}

export function formatDecimal(value: number) {
  return formatNumber(value, 1);
}

export function formatRange(
  range: RepresentativeRange,
  formatter: (value: number) => string,
) {
  return `${formatter(range.p25)}–${formatter(range.p75)}`;
}

function formatNumber(value: number, maximumFractionDigits: number) {
  return new Intl.NumberFormat("en", {
    maximumFractionDigits,
  }).format(value);
}
