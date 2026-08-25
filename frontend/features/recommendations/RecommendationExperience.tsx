"use client";

import { useEffect, useState } from "react";
import type { RecommendationResult } from "@/types/recommendations";
import { RecommendationCard } from "./RecommendationCard";
import { RouteMap } from "./RouteMap";
import { warningMessage } from "./formatters";
import { RouteComparison } from "./RouteComparison";

export const MAX_COMPARISON_ROUTES = 3;

export function RecommendationExperience({ result, selectedCandidateId, onSelectCandidate }: { result: RecommendationResult; selectedCandidateId: string | null; onSelectCandidate: (id: string) => void }) {
  const [comparisonCandidateIds, setComparisonCandidateIds] = useState<string[]>([]);
  const [comparisonMessage, setComparisonMessage] = useState<string | null>(null);
  useEffect(() => { setComparisonCandidateIds([]); setComparisonMessage(null); }, [result]);
  const toggleComparison = (id: string) => {
    setComparisonCandidateIds((current) => {
      if (current.includes(id)) { setComparisonMessage(null); return current.filter((candidateId) => candidateId !== id); }
      if (current.length >= MAX_COMPARISON_ROUTES) { setComparisonMessage(`You can compare up to ${MAX_COMPARISON_ROUTES} routes at once.`); return current; }
      setComparisonMessage(null); return [...current, id];
    });
  };
  const comparedRecommendations = comparisonCandidateIds.map((id) => result.recommendations.find(({ candidate }) => candidate.id === id)).filter((route) => route !== undefined);
  return <>
    {result.warnings.length > 0 && <div className="route-warnings" role="status"><strong>Recommendation notices</strong><ul>{[...new Set(result.warnings)].map((warning) => <li key={warning}>{warningMessage(warning)}</li>)}</ul></div>}
    {result.recommendations.length === 0
      ? <p className="mt-3" role="status">No recommendations were returned for these inputs.</p>
      : <><div className="recommendation-layout"><div className="recommendation-list">{result.recommendations.map((recommendation) => <RecommendationCard key={recommendation.candidate.id} recommendation={recommendation} selected={recommendation.candidate.id === selectedCandidateId} compared={comparisonCandidateIds.includes(recommendation.candidate.id)} onToggleCompare={() => toggleComparison(recommendation.candidate.id)} onSelect={() => onSelectCandidate(recommendation.candidate.id)} />)}</div><aside aria-label="Route map" className="recommendation-map"><RouteMap recommendations={result.recommendations} selectedCandidateId={selectedCandidateId} onSelectCandidate={onSelectCandidate} /></aside></div><div aria-live="polite">{comparisonMessage ? <p className="comparison-helper comparison-limit">{comparisonMessage}</p> : comparedRecommendations.length < 2 ? <p className="comparison-helper">Select at least two routes to compare.</p> : null}</div>{comparedRecommendations.length >= 2 && <RouteComparison recommendations={comparedRecommendations} selectedCandidateId={selectedCandidateId} onSelectCandidate={onSelectCandidate} />}</>}
  </>;
}
