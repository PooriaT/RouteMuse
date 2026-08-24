import { describe, expect, it } from "vitest";

import { toRoutePlanningRequest, validatePlanningPreferences, type PlanningPreferences } from "@/types/planning";

const area = { latitude: 49.2827, longitude: -123.1207, display_name: "Vancouver, BC", bounding_box: null, source_provider: "openrouteservice", source_attribution: "© OpenStreetMap contributors" };

function preferences(overrides: Partial<PlanningPreferences> = {}): PlanningPreferences {
  return { planningArea: area, activityKind: "hiking", targetDistanceKm: "", targetDurationMinutes: "", desiredChallenge: null, routeShape: null, noveltyPreference: null, ...overrides };
}

describe("planning request normalization", () => {
  it("keeps empty overrides null and includes the selected canonical area unchanged", () => {
    expect(toRoutePlanningRequest(preferences())).toEqual({ planning_area: area, activity_kind: "hiking", target_distance_meters: null, target_duration_seconds: null, desired_challenge: null, route_shape: null, novelty_preference: null });
  });

  it("converts display units and maps each enum without alternative spellings", () => {
    expect(toRoutePlanningRequest(preferences({ targetDistanceKm: "25", targetDurationMinutes: "90", desiredChallenge: "hard", routeShape: "out_and_back", noveltyPreference: "novel" }))).toMatchObject({ target_distance_meters: 25_000, target_duration_seconds: 5_400, desired_challenge: "hard", route_shape: "out_and_back", novelty_preference: "novel" });
  });

  it.each([["targetDistanceKm", "0"], ["targetDistanceKm", "-1"], ["targetDurationMinutes", "0"], ["targetDurationMinutes", "-1"]] as const)("rejects non-positive %s", (field, value) => {
    const state = preferences({ [field]: value });
    expect(validatePlanningPreferences(state)[field]).toBeDefined();
    expect(toRoutePlanningRequest(state)).toBeNull();
  });

  it("requires a location and activity before validation", () => {
    expect(validatePlanningPreferences(preferences({ planningArea: null, activityKind: null }))).toMatchObject({ planningArea: expect.any(String), activityKind: expect.any(String) });
  });
});
