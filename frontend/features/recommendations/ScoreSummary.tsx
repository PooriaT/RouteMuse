import type { RankedRecommendation, ScoreComponent } from "@/types/recommendations";
import { formatScore, friendlyLabel } from "./formatters";

export function ScoreSummary({ recommendation }: { recommendation: RankedRecommendation }) {
  const scores = [
    ["Difficulty", recommendation.difficulty.score, "Higher means more intrinsically demanding."],
    ["Athlete fit", recommendation.athlete_fit.score, recommendation.athlete_fit.status === "insufficient_history" ? "Insufficient history" : "Match to your demonstrated profile and request."],
    ["Excitement", recommendation.excitement.score, "RouteMuse heuristic based on available route evidence."],
    ["Novelty", recommendation.novelty.novelty_score, recommendation.novelty.status === "insufficient_history" ? "Insufficient history" : "How geographically new the route is; more is not always better."],
    ["Confidence", recommendation.confidence.score, "Evidence coverage, not safety certainty."],
    ["Preference alignment", recommendation.preference_alignment.score, "Match to your explicit route preferences."],
  ] as const;
  return <section aria-label="Route scorecard" className="mt-5">
    <div className="final-score"><span><strong>Recommendation score</strong><small>Backend ranking score</small></span><strong>{formatScore(recommendation.final_score)}</strong></div>
    <div className="score-grid">{scores.map(([label, score, explanation]) => <div className="score-item" key={label}><div><strong>{label}</strong><span>{formatScore(score, label === "Athlete fit" || label === "Novelty" ? "Insufficient history" : "Limited evidence")}</span></div>{score !== null && <progress aria-label={`${label}: ${formatScore(score)}`} max="1" value={score} />}<small>{explanation}</small></div>)}</div>
    <details className="mt-4"><summary>How this ranking score is supported</summary><p className="mt-2 text-sm text-slate-600">The server combines athlete fit, preference alignment, excitement, and evidence confidence. RouteMuse displays that result without recalculating it.</p><Assessment title="Difficulty evidence" components={recommendation.difficulty.components} /><Assessment title="Preference alignment evidence" components={recommendation.preference_alignment.components} /><Assessment title="Confidence evidence" components={recommendation.confidence.components} />{recommendation.athlete_fit.components.length > 0 && <div className="mt-3"><h5 className="font-semibold">Athlete fit evidence</h5><ul className="detail-list">{recommendation.athlete_fit.components.map((component) => <li key={component.name}><strong>{friendlyLabel(component.name)} ({formatScore(component.score)}):</strong> {component.evidence.join("; ") || "Limited evidence"}</li>)}</ul></div>}</details>
  </section>;
}

function Assessment({ title, components }: { title: string; components: ScoreComponent[] }) {
  if (!components.length) return null;
  return <div className="mt-3"><h5 className="font-semibold">{title}</h5><ul className="detail-list">{components.map((component) => <li key={component.name}><strong>{friendlyLabel(component.name)}:</strong> {component.evidence_available ? `${formatScore(component.score)} — ${component.evidence_summary}` : component.evidence_summary || "Limited evidence"}</li>)}</ul></div>;
}
