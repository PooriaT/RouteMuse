import type { RecommendationReasoningEnvelope } from "@/types/recommendations";
const knownTags: Record<string, string> = {
  close_to_target: "Close to target",
  strong_athlete_fit: "Strong athlete fit",
  high_climbing: "High climbing",
  mixed_surface: "Mixed surface",
  technical_terrain: "Technical terrain",
  novel: "Novel",
  familiar: "Familiar",
  limited_evidence: "Limited evidence",
};

export function RecommendationReasoning({ envelope }: { envelope: RecommendationReasoningEnvelope | null }) {
  if (!envelope) return <section className="reasoning"><h4>Why RouteMuse suggested this</h4><p className="text-sm text-slate-600">Limited evidence is available for an explanation.</p></section>;
  const { reasoning } = envelope;
  return <section className="reasoning"><h4>Why RouteMuse suggested this</h4><p className="mt-2">{reasoning.summary}</p>{reasoning.qualitative_tags.some((tag) => tag in knownTags) && <ul aria-label="Route tags" className="mt-3 flex flex-wrap gap-2">{reasoning.qualitative_tags.filter((tag) => tag in knownTags).map((tag) => <li className="tag" key={tag}>{knownTags[tag]}</li>)}</ul>}<ReasonList title="Reasons" items={reasoning.reasons} /><ReasonList title="Highlights" items={reasoning.highlights} />{reasoning.cautions.length > 0 && <div className="cautions" role="status"><strong>Cautions</strong><ul>{reasoning.cautions.map((item) => <li key={item}>{item}</li>)}</ul></div>}<p className="mt-3 text-xs text-slate-500">Explanation: {envelope.source === "ollama" ? "local model" : "RouteMuse deterministic summary"}</p></section>;
}

function ReasonList({ title, items }: { title: string; items: string[] }) { return items.length ? <div className="mt-3"><strong>{title}</strong><ul className="detail-list">{items.map((item) => <li key={item}>{item}</li>)}</ul></div> : null; }
