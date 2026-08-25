import { describe, expect, it } from "vitest";
import { recommendationErrorMessage, isTransientRecommendationError } from "@/features/planner/PlannerForm";
import { ApiError } from "@/lib/api/client";

describe("recommendation error presentation", () => {
  it.each([
    ["recommendation_target_unavailable", "Add a target distance or import enough matching activity history."],
    ["athlete_profile_history_incomplete", "Complete the interrupted Strava import first."],
    ["route_provider_rate_limited", "Route generation is temporarily rate limited."],
    ["route_provider_unavailable", "Route generation is temporarily unavailable."],
    ["network_error", "The RouteMuse API is unavailable. Check your connection and try again."],
  ])("maps %s", (code, message) => expect(recommendationErrorMessage(new ApiError("internal", 503, code))).toBe(message));

  it("only offers retries for transient failures", () => {
    expect(isTransientRecommendationError(new ApiError("internal", 429, "route_provider_rate_limited"))).toBe(true);
    expect(isTransientRecommendationError(new ApiError("internal", 422, "recommendation_target_unavailable"))).toBe(false);
  });
});
