export function formatScore(value: number | null, unavailable = "Not available") {
  return value === null ? unavailable : `${Math.round(value * 100)}%`;
}

export function formatDistance(meters: number) {
  const kilometres = meters / 1_000;
  return `${kilometres.toLocaleString(undefined, { maximumFractionDigits: kilometres < 100 ? 1 : 0 })} km`;
}

export function formatDuration(seconds: number | null) {
  if (seconds === null || seconds <= 0) return "Not available";
  const minutes = Math.round(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return hours ? `${hours} h${remainder ? ` ${remainder} min` : ""}` : `${remainder} min`;
}

export function formatElevation(meters: number | null) {
  return meters === null ? "Not available" : `${Math.round(meters).toLocaleString()} m gained`;
}

export function friendlyLabel(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export const shapeLabels = { loop: "Loop", out_and_back: "Out-and-back", point_to_point: "Point-to-point" } as const;

const warningMessages: Record<string, string> = {
  fewer_candidates_than_desired: "Fewer distinct routes were available than requested.",
  fewer_diverse_recommendations_available: "Fewer meaningfully distinct recommendations were available than requested.",
  trail_discovery_unavailable: "Trail discovery was temporarily unavailable, so route variety may be limited.",
  partial_route_data: "Some route details are unavailable.",
  limited_surface_data: "Surface information is limited.",
  limited_technical_data: "Technical information is limited.",
  insufficient_history: "Your activity history is insufficient for part of this assessment.",
  missing_climbing_density_evidence: "Climbing density could not be assessed without route elevation.",
  missing_elevation_fit_evidence: "Elevation fit could not be compared without route elevation.",
  missing_elevation_gain_evidence: "Route elevation gain was not provided.",
  missing_named_content_evidence: "Nearby named trail information was unavailable.",
  missing_novelty_evidence: "Historical route geometry was insufficient to assess novelty.",
  partial_steepness_evidence: "Steepness information covers only part of this route.",
  partial_surface_evidence: "Known surface information covers only part of this route.",
  ollama_unconfigured_using_fallback: "Using RouteMuse's built-in explanation because the local AI explanation is not configured.",
  ollama_timeout_using_fallback: "Using RouteMuse's built-in explanation because the local AI explanation timed out.",
  ollama_invalid_output_using_fallback: "Using RouteMuse's built-in explanation because the local AI response was invalid.",
  ollama_model_unavailable_using_fallback: "Using RouteMuse's built-in explanation because the local AI model is unavailable.",
  ollama_unavailable_using_fallback: "Using RouteMuse's built-in explanation because the local AI explanation is unavailable.",
};

export function warningMessage(warning: string) {
  return warningMessages[warning] ?? (warning.includes(" ") ? warning : "Additional route information is unavailable.");
}
