import type { RecommendationResult } from "@/types/recommendations";
import { RecommendationCard } from "./RecommendationCard";
import { RouteMap } from "./RouteMap";
import { warningMessage } from "./formatters";

export function RecommendationExperience({ result, selectedCandidateId, onSelectCandidate }: { result: RecommendationResult; selectedCandidateId: string | null; onSelectCandidate: (id: string) => void }) {
  return <>
    {result.warnings.length > 0 && <div className="route-warnings" role="status"><strong>Recommendation notices</strong><ul>{[...new Set(result.warnings)].map((warning) => <li key={warning}>{warningMessage(warning)}</li>)}</ul></div>}
    {result.recommendations.length === 0
      ? <p className="mt-3" role="status">No recommendations were returned for these inputs.</p>
      : <div className="recommendation-layout"><div className="recommendation-list">{result.recommendations.map((recommendation) => <RecommendationCard key={recommendation.candidate.id} recommendation={recommendation} selected={recommendation.candidate.id === selectedCandidateId} onSelect={() => onSelectCandidate(recommendation.candidate.id)} />)}</div><aside aria-label="Route map" className="recommendation-map"><RouteMap recommendations={result.recommendations} selectedCandidateId={selectedCandidateId} onSelectCandidate={onSelectCandidate} /></aside></div>}
  </>;
}
