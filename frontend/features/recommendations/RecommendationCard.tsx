import type { RankedRecommendation } from "@/types/recommendations";
import { RecommendationReasoning } from "./RecommendationReasoning";
import { RouteAttributes } from "./RouteAttributes";
import { ScoreSummary } from "./ScoreSummary";
import { warningMessage } from "./formatters";

export function RecommendationCard({ recommendation, selected, onSelect }: { recommendation: RankedRecommendation; selected: boolean; onSelect: () => void }) {
  const warnings = [...new Set([...recommendation.warnings, ...recommendation.candidate.warnings])];
  const attributions = [...new Set(recommendation.candidate.provenance.map(({ attribution }) => attribution).filter(Boolean))];
  return <article className={`recommendation-card ${selected ? "recommendation-card-selected" : ""}`} aria-labelledby={`route-${recommendation.candidate.id}`}>
    <div className="flex items-start justify-between gap-4"><div><p className="rank">Rank {recommendation.rank}</p><h3 id={`route-${recommendation.candidate.id}`} className="text-2xl font-bold">{recommendation.candidate.name}</h3></div><button type="button" aria-pressed={selected} onClick={onSelect} className="select-route">{selected ? "Selected route" : "Select route"}</button></div>
    <RouteAttributes candidate={recommendation.candidate} />
    <ScoreSummary recommendation={recommendation} />
    {warnings.length > 0 && <div className="route-warnings" role="status"><strong>Route notices</strong><ul>{warnings.map((warning) => <li key={warning}>{warningMessage(warning)}</li>)}</ul></div>}
    <RecommendationReasoning envelope={recommendation.reasoning} />
    {attributions.length > 0 && <details className="mt-4"><summary>Route data attribution</summary><p className="mt-2 text-sm">{attributions.join(" · ")}</p></details>}
  </article>;
}
