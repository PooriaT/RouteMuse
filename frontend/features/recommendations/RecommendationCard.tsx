"use client";

import { useState } from "react";

import { downloadGpx } from "@/lib/gpx";
import type { RankedRecommendation } from "@/types/recommendations";
import { RecommendationReasoning } from "./RecommendationReasoning";
import { RouteAttributes } from "./RouteAttributes";
import { ScoreSummary } from "./ScoreSummary";
import { warningMessage } from "./formatters";

export function RecommendationCard({ recommendation, selected, compared, onSelect, onToggleCompare }: { recommendation: RankedRecommendation; selected: boolean; compared: boolean; onSelect: () => void; onToggleCompare: () => void }) {
  const [exportError, setExportError] = useState<string | null>(null);
  const cautions = new Set(recommendation.reasoning?.reasoning.cautions ?? []);
  const warnings = [...new Set([...recommendation.warnings, ...recommendation.candidate.warnings])].filter((warning) => !cautions.has(warning));
  const attributions = [...new Set(recommendation.candidate.provenance.map(({ attribution }) => attribution).filter(Boolean))];
  const exportRoute = () => {
    try {
      downloadGpx(recommendation.candidate, recommendation.rank);
      setExportError(null);
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "This route could not be exported.");
    }
  };
  return <article className={`recommendation-card ${selected ? "recommendation-card-selected" : ""}`} aria-labelledby={`route-${recommendation.candidate.id}`}>
    <div className="flex items-start justify-between gap-4"><div><p className="rank">Rank {recommendation.rank}</p><h3 id={`route-${recommendation.candidate.id}`} className="text-2xl font-bold">{recommendation.candidate.name}</h3></div><div className="card-actions"><button type="button" aria-pressed={selected} onClick={onSelect} className="select-route">{selected ? "Selected route" : "Select route"}</button><button type="button" aria-label={compared ? `Remove ${recommendation.candidate.name} from comparison` : `Compare ${recommendation.candidate.name}`} aria-pressed={compared} onClick={onToggleCompare} className="compare-route">{compared ? "Remove from comparison" : "Compare"}</button><button type="button" aria-label={`Download GPX for ${recommendation.candidate.name}`} onClick={exportRoute} className="export-route">Download GPX</button></div></div>
    {exportError && <p className="route-export-error" role="alert">GPX export unavailable: {exportError}</p>}
    <RouteAttributes candidate={recommendation.candidate} />
    <ScoreSummary recommendation={recommendation} />
    {warnings.length > 0 && <div className="route-warnings" role="status"><strong>Route notices</strong><ul>{warnings.map((warning) => <li key={warning}>{warningMessage(warning)}</li>)}</ul></div>}
    <RecommendationReasoning envelope={recommendation.reasoning} />
    {attributions.length > 0 && <details className="mt-4"><summary>Route data attribution</summary><p className="mt-2 text-sm">{attributions.join(" · ")}</p></details>}
  </article>;
}
