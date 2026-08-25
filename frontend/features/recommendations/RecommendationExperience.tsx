import type { RecommendationResult } from "@/types/recommendations";
import { RecommendationCard } from "./RecommendationCard";
import { RouteMap } from "./RouteMap";

export function RecommendationExperience({ result, selectedCandidateId, onSelectCandidate }: { result: RecommendationResult; selectedCandidateId: string | null; onSelectCandidate: (id: string) => void }) {
  if (result.recommendations.length === 0) return <p className="mt-3" role="status">No recommendations were returned for these inputs.</p>;
  return <div className="recommendation-layout"><div className="recommendation-list">{result.recommendations.map((recommendation) => <RecommendationCard key={recommendation.candidate.id} recommendation={recommendation} selected={recommendation.candidate.id === selectedCandidateId} onSelect={() => onSelectCandidate(recommendation.candidate.id)} />)}</div><aside aria-label="Route map" className="recommendation-map"><RouteMap recommendations={result.recommendations} selectedCandidateId={selectedCandidateId} onSelectCandidate={onSelectCandidate} /></aside></div>;
}
