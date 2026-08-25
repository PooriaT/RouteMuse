import type { RoutePlanningRequest } from "./planning";
import type { RouteCandidate } from "./routes";

export type RecommendationRequest = {
  planning_request: RoutePlanningRequest;
  start_date: string;
  end_date: string;
  timezone: string;
};

export type ScoreComponent = {
  name: string;
  score: number | null;
  weight: number;
  evidence_available: boolean;
  evidence_summary: string;
};
export type ExcitementComponent = Omit<ScoreComponent, "weight"> & { base_weight: number };
export type AthleteFitComponent = { name: string; score: number; evidence: string[] };
export type RouteDifficultyAssessment = { score: number; components: ScoreComponent[]; evidence_coverage: number; scoring_version: string; warnings: string[] };
export type ExcitementAssessment = { score: number | null; components: ExcitementComponent[]; evidence_coverage: number; scoring_version: string; warnings: string[] };
export type AthleteFitAssessment = { score: number | null; confidence: number; components: AthleteFitComponent[]; status: "scored" | "insufficient_history" | "unsupported_activity"; scoring_version: string; warnings: string[] };
export type NoveltyAssessment = { status: "available" | "insufficient_history"; novelty_score: number | null; confidence: number; eligible_activity_count: number; geometry_activity_count: number; missing_geometry_activity_count: number; geometry_coverage_ratio: number };
export type PreferenceAlignmentAssessment = { score: number | null; components: ScoreComponent[]; evidence_coverage: number; scoring_version: string; warnings: string[] };
export type RecommendationConfidence = { score: number; components: ScoreComponent[]; scoring_version: string };
export type RecommendationScorecard = { final_score: number; ranking_version: string; difficulty: RouteDifficultyAssessment; athlete_fit: AthleteFitAssessment; novelty: NoveltyAssessment; excitement: ExcitementAssessment; preference_alignment: PreferenceAlignmentAssessment; confidence: RecommendationConfidence };
export type RecommendationReasoning = { summary: string; reasons: string[]; cautions: string[]; highlights: string[]; qualitative_tags: string[] };
export type RecommendationReasoningEnvelope = { source: "ollama" | "deterministic_fallback"; reasoning: RecommendationReasoning; schema_version: string; context_version: string; model: string | null };
export type RankedRecommendation = { rank: number; candidate: RouteCandidate; final_score: number; difficulty: RouteDifficultyAssessment; athlete_fit: AthleteFitAssessment; novelty: NoveltyAssessment; excitement: ExcitementAssessment; preference_alignment: PreferenceAlignmentAssessment; confidence: RecommendationConfidence; scorecard: RecommendationScorecard; warnings: string[]; reasoning: RecommendationReasoningEnvelope | null };
export type RecommendationResult = { recommendations: RankedRecommendation[]; requested_recommendations: number; generated_candidates: number; ranking_version: string; warnings: string[] };
