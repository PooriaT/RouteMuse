import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { RecommendationExperience } from "@/features/recommendations/RecommendationExperience";
import type { RankedRecommendation, RecommendationResult, ScoreComponent } from "@/types/recommendations";

vi.mock("@/features/recommendations/RouteMap", () => ({ RouteMap: ({ onSelectCandidate }: { onSelectCandidate: (id: string) => void }) => <button onClick={() => onSelectCandidate("route-two")}>Select route two on map</button> }));

const evidence: ScoreComponent = { name: "distance", score: 0.8, weight: 0.5, evidence_available: true, evidence_summary: "Near the requested distance." };

function recommendation(id: string, name: string, rank: number, overrides: Partial<RankedRecommendation> = {}): RankedRecommendation {
  const difficulty = { score: 0.9, components: [evidence], evidence_coverage: 1, scoring_version: "v1", warnings: [] };
  const athlete_fit = { score: 0.82, confidence: 0.7, components: [{ name: "capability", score: 0.82, evidence: ["Supported by recent efforts."] }], status: "scored" as const, scoring_version: "v1", warnings: [] };
  const novelty = { status: "available" as const, novelty_score: 0.6, confidence: 0.7, eligible_activity_count: 4, geometry_activity_count: 4, missing_geometry_activity_count: 0, geometry_coverage_ratio: 1 };
  const excitement = { score: 0.75, components: [{ ...evidence, base_weight: 0.5 }], evidence_coverage: 1, scoring_version: "v1", warnings: [] };
  const preference_alignment = { score: 0.88, components: [evidence], evidence_coverage: 1, scoring_version: "v1", warnings: [] };
  const confidence = { score: 0.7, components: [evidence], scoring_version: "v1" };
  const candidate = { id, name, activity_kind: "hiking" as const, distance_meters: 12_450, estimated_duration_seconds: 5_460, elevation_gain_meters: 421, elevation_loss_meters: null, geometry: { type: "LineString" as const, coordinates: [[-123, 49] as [number, number], [-122.9, 49.1] as [number, number]] }, geojson_reference: null, route_shape: "out_and_back" as const, surface_breakdown: [{ value: "paved", distance_meters: 8_000, proportion: 0.64 }], way_type_breakdown: [{ value: "path", distance_meters: 4_450, proportion: 0.36 }], technical_breakdown: [{ characteristic: "steepness", value: "moderate", distance_meters: 2_000, proportion: 0.16 }], provenance: [{ provider: "ors", attribution: "Provider data", source_ids: [], provider_request_id: null, provider_profile: null }], data_confidence: 0.8, generation_provenance: null, warnings: ["mystery_code"], difficulty_score: null, athlete_fit_score: null, excitement_score: null, novelty_score: null, confidence_score: null, explanation: null };
  const final_score = 0.84;
  return { rank, candidate, final_score, difficulty, athlete_fit, novelty, excitement, preference_alignment, confidence, scorecard: { final_score, ranking_version: "v1", difficulty, athlete_fit, novelty, excitement, preference_alignment, confidence }, warnings: ["fewer_candidates_than_desired"], reasoning: { source: rank === 1 ? "ollama" : "deterministic_fallback", schema_version: "v1", context_version: "v1", model: rank === 1 ? "local" : null, reasoning: { summary: `Summary for ${name}`, reasons: ["Matches your request."], cautions: ["Check conditions."], highlights: ["Measured route facts."], qualitative_tags: rank === 1 ? ["close_to_target", "strong_athlete_fit", "high_climbing", "mixed_surface", "technical_terrain", "novel", "familiar", "limited_evidence"] : ["unknown_tag"] } }, ...overrides };
}

const result: RecommendationResult = { recommendations: [recommendation("route-two", "Server first", 2), recommendation("route-one", "Server second", 1, { candidate: { ...recommendation("route-one", "Server second", 1).candidate, estimated_duration_seconds: null, elevation_gain_meters: null }, novelty: { ...recommendation("x", "x", 1).novelty, status: "insufficient_history", novelty_score: null } })], requested_recommendations: 2, generated_candidates: 2, ranking_version: "v1", warnings: ["trail_discovery_unavailable", "fewer_diverse_recommendations_available"] };

function Harness() { const [selected, setSelected] = useState(result.recommendations[0].candidate.id); return <RecommendationExperience result={result} selectedCandidateId={selected} onSelectCandidate={setSelected} />; }

describe("RecommendationExperience", () => {
  it("preserves server order and renders facts, distinct scores, reasoning, warnings, and attribution", () => {
    render(<Harness />);
    const cards = screen.getAllByRole("article");
    expect(within(cards[0]).getByText("Server first")).toBeInTheDocument();
    expect(within(cards[1]).getByText("Server second")).toBeInTheDocument();
    expect(within(cards[0]).getByText("12.5 km")).toBeInTheDocument();
    expect(within(cards[0]).getByText("1 h 31 min")).toBeInTheDocument();
    expect(within(cards[0]).getByText("421 m gained")).toBeInTheDocument();
    expect(within(cards[0]).getByText("Out-and-back")).toBeInTheDocument();
    expect(within(cards[1]).getAllByText("Not available")).toHaveLength(2);
    expect(within(cards[0]).getByText(/intrinsically demanding/)).toBeInTheDocument();
    expect(within(cards[0]).getByText("Preference alignment")).toBeInTheDocument();
    expect(within(cards[1]).getAllByText("Insufficient history").length).toBeGreaterThan(0);
    expect(screen.getByText("Summary for Server first")).toBeInTheDocument();
    expect(screen.getByText("Explanation: local model")).toBeInTheDocument();
    expect(screen.getByText("Explanation: RouteMuse deterministic summary")).toBeInTheDocument();
    expect(screen.getAllByText("Matches your request.")).toHaveLength(2);
    expect(screen.getAllByText("Check conditions.")).toHaveLength(2);
    expect(screen.getAllByText("Measured route facts.")).toHaveLength(2);
    for (const tag of ["Close to target", "Strong athlete fit", "High climbing", "Mixed surface", "Technical terrain", "Novel", "Familiar", "Limited evidence"]) {
      expect(screen.getByText(tag)).toBeInTheDocument();
    }
    expect(screen.queryByText("unknown_tag")).not.toBeInTheDocument();
    expect(screen.getByText("Trail discovery was temporarily unavailable, so route variety may be limited.")).toBeInTheDocument();
    expect(screen.getByText("Fewer meaningfully distinct recommendations were available than requested.")).toBeInTheDocument();
    expect(screen.getAllByText("Fewer distinct routes were available than requested.")).toHaveLength(2);
    expect(screen.getAllByText("Additional route information is unavailable.")).toHaveLength(2);
    expect(screen.getAllByText("Provider data")).toHaveLength(2);
  });

  it("synchronizes accessible card and map selection", () => {
    render(<Harness />);
    const controls = screen.getAllByRole("button", { name: /route$/ });
    expect(controls[0]).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(controls[1]);
    expect(controls[1]).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Select route two on map" }));
    expect(controls[0]).toHaveAttribute("aria-pressed", "true");
  });

  it("handles an empty result", () => {
    render(<RecommendationExperience result={{ ...result, recommendations: [], warnings: [] }} selectedCandidateId={null} onSelectCandidate={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("No recommendations were returned for these inputs.");
  });
});
