import { describe, expect, it } from "vitest";

import { warningMessage } from "@/features/recommendations/formatters";

describe("warningMessage", () => {
  it("translates evidence codes into specific route notices", () => {
    expect(warningMessage("missing_elevation_gain_evidence")).toBe(
      "Route elevation gain was not provided.",
    );
    expect(warningMessage("missing_novelty_evidence")).toBe(
      "Historical route geometry was insufficient to assess novelty.",
    );
    expect(warningMessage("partial_surface_evidence")).toBe(
      "Known surface information covers only part of this route.",
    );
  });

  it("describes a successful deterministic explanation fallback accurately", () => {
    expect(warningMessage("ollama_model_unavailable_using_fallback")).toBe(
      "Using RouteMuse's built-in explanation because the local AI model is unavailable.",
    );
  });
});
