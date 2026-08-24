import type { ActivityKind } from "./athleteProfile";
import type { PlanningArea } from "./planningArea";

export type DesiredChallenge = "easy" | "moderate" | "hard";
export type RouteShape = "loop" | "out_and_back" | "point_to_point";
export type NoveltyPreference = "familiar" | "balanced" | "novel";

export type PlanningPreferences = {
  planningArea: PlanningArea | null;
  activityKind: ActivityKind | null;
  targetDistanceKm: string;
  targetDurationMinutes: string;
  desiredChallenge: DesiredChallenge | null;
  routeShape: RouteShape | null;
  noveltyPreference: NoveltyPreference | null;
};

export type RoutePlanningRequest = {
  planning_area: PlanningArea;
  activity_kind: ActivityKind;
  target_distance_meters: number | null;
  target_duration_seconds: number | null;
  desired_challenge: DesiredChallenge | null;
  route_shape: RouteShape | null;
  novelty_preference: NoveltyPreference | null;
};

export type PlanningValidationResponse = RoutePlanningRequest;

export type PlanningPreferenceErrors = Partial<
  Record<"planningArea" | "activityKind" | "targetDistanceKm" | "targetDurationMinutes", string>
>;

export function validatePlanningPreferences(
  preferences: PlanningPreferences,
): PlanningPreferenceErrors {
  const errors: PlanningPreferenceErrors = {};
  if (!preferences.planningArea) errors.planningArea = "Choose a planning area.";
  if (!preferences.activityKind) errors.activityKind = "Choose an activity type.";
  if (
    preferences.targetDistanceKm !== "" &&
    (!Number.isFinite(Number(preferences.targetDistanceKm)) ||
      Number(preferences.targetDistanceKm) <= 0)
  ) {
    errors.targetDistanceKm = "Distance must be greater than zero.";
  }
  if (
    preferences.targetDurationMinutes !== "" &&
    (!Number.isFinite(Number(preferences.targetDurationMinutes)) ||
      Number(preferences.targetDurationMinutes) <= 0)
  ) {
    errors.targetDurationMinutes = "Duration must be greater than zero.";
  } else if (
    preferences.targetDurationMinutes !== "" &&
    !Number.isInteger(Number(preferences.targetDurationMinutes) * 60)
  ) {
    errors.targetDurationMinutes =
      "Duration must convert to a whole number of seconds.";
  }
  return errors;
}

/** The single presentation-units to canonical API-boundary transformation. */
export function toRoutePlanningRequest(
  preferences: PlanningPreferences,
): RoutePlanningRequest | null {
  if (Object.keys(validatePlanningPreferences(preferences)).length > 0) return null;
  if (!preferences.planningArea || !preferences.activityKind) return null;

  return {
    planning_area: preferences.planningArea,
    activity_kind: preferences.activityKind,
    target_distance_meters:
      preferences.targetDistanceKm === ""
        ? null
        : Number(preferences.targetDistanceKm) * 1_000,
    target_duration_seconds:
      preferences.targetDurationMinutes === ""
        ? null
        : Number(preferences.targetDurationMinutes) * 60,
    desired_challenge: preferences.desiredChallenge,
    route_shape: preferences.routeShape,
    novelty_preference: preferences.noveltyPreference,
  };
}
