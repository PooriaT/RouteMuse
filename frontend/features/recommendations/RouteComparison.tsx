import type { ReactNode } from "react";
import type { RankedRecommendation, ScoreComponent } from "@/types/recommendations";
import type { ProviderProvenance, RouteCandidate, TechnicalSummary } from "@/types/routes";
import { formatDistance, formatDuration, formatElevation, formatScore, friendlyLabel, shapeLabels, warningMessage } from "./formatters";

const unavailable = "Not available";

function distribution(items: Array<{ value: string; proportion: number | null; distance_meters: number | null }>) {
  if (!items.length) return unavailable;
  return <ul className="comparison-values">{items.map((item, index) => <li key={`${item.value}-${index}`}>{friendlyLabel(item.value)}{item.proportion !== null ? ` · ${Math.round(item.proportion * 100)}%` : item.distance_meters !== null ? ` · ${formatDistance(item.distance_meters)}` : ""}</li>)}</ul>;
}

function technical(items: TechnicalSummary[]) {
  if (!items.length) return unavailable;
  return <ul className="comparison-values">{items.map((item, index) => <li key={`${item.characteristic}-${item.value}-${index}`}><strong>{friendlyLabel(item.characteristic)}:</strong> {friendlyLabel(item.value)}{item.proportion !== null ? ` · ${Math.round(item.proportion * 100)}%` : ""}</li>)}</ul>;
}

function providerMetadata(provenance: ProviderProvenance[]) {
  if (!provenance.length) return unavailable;
  const providers = [...new Set(provenance.map(({ provider, provider_profile }) => `${friendlyLabel(provider)}${provider_profile ? ` · ${friendlyLabel(provider_profile)}` : ""}`))];
  const attributions = [...new Set(provenance.map(({ attribution }) => attribution).filter(Boolean))];
  return <><ul className="comparison-values">{providers.map((provider) => <li key={provider}>{provider}</li>)}</ul>{attributions.length > 0 && <p className="comparison-attribution">Attribution: {attributions.join(" · ")}</p>}</>;
}

function preferenceDetails(components: ScoreComponent[]) {
  if (!components.length) return null;
  return <details><summary>Component details</summary><ul className="comparison-values">{components.map((component) => <li key={component.name}><strong>{friendlyLabel(component.name)}:</strong> {component.evidence_available ? formatScore(component.score) : unavailable}</li>)}</ul></details>;
}

function climbingDensity(candidate: RouteCandidate) {
  if (candidate.elevation_gain_meters === null || candidate.distance_meters <= 0) return unavailable;
  return `${Math.round(candidate.elevation_gain_meters / (candidate.distance_meters / 1_000))} m/km`;
}

type Row = { label: string; value: (route: RankedRecommendation) => ReactNode };

export function RouteComparison({ recommendations, selectedCandidateId, onSelectCandidate }: { recommendations: RankedRecommendation[]; selectedCandidateId: string | null; onSelectCandidate: (id: string) => void }) {
  const rows: Row[] = [
    { label: "Distance", value: ({ candidate }) => formatDistance(candidate.distance_meters) },
    { label: "Estimated duration", value: ({ candidate }) => formatDuration(candidate.estimated_duration_seconds) },
    { label: "Elevation gain", value: ({ candidate }) => formatElevation(candidate.elevation_gain_meters) },
    { label: "Climbing density", value: ({ candidate }) => climbingDensity(candidate) },
    { label: "Route shape", value: ({ candidate }) => candidate.route_shape ? shapeLabels[candidate.route_shape] : unavailable },
    { label: "Key surfaces", value: ({ candidate }) => distribution(candidate.surface_breakdown) },
    { label: "Way types", value: ({ candidate }) => distribution(candidate.way_type_breakdown) },
    { label: "Technical characteristics", value: ({ candidate }) => technical(candidate.technical_breakdown) },
    { label: "Final recommendation score", value: (route) => formatScore(route.final_score) },
    { label: "Route difficulty", value: (route) => <>{formatScore(route.difficulty.score)}<small>Intrinsic demand; higher is not automatically better.</small></> },
    { label: "Athlete fit", value: (route) => route.athlete_fit.score === null ? friendlyLabel(route.athlete_fit.status) : formatScore(route.athlete_fit.score) },
    { label: "Geographic novelty", value: (route) => <>{route.novelty.novelty_score === null ? friendlyLabel(route.novelty.status) : formatScore(route.novelty.novelty_score)}<small>More novel is not automatically preferable.</small></> },
    { label: "Excitement", value: (route) => formatScore(route.excitement.score) },
    { label: "Confidence", value: (route) => formatScore(route.confidence.score) },
    { label: "Preference alignment", value: (route) => <>{formatScore(route.preference_alignment.score)}{preferenceDetails(route.preference_alignment.components)}</> },
    { label: "Warnings", value: (route) => { const warnings = [...new Set([...route.warnings, ...route.candidate.warnings])]; return warnings.length ? <ul className="comparison-values">{warnings.map((warning) => <li key={warning}>{warningMessage(warning)}</li>)}</ul> : "None reported"; } },
    { label: "Provider metadata", value: ({ candidate }) => providerMetadata(candidate.provenance) },
    { label: "Why suggested", value: (route) => route.reasoning?.reasoning.summary ?? unavailable },
  ];

  return <section aria-labelledby="comparison-heading" className="route-comparison"><h2 id="comparison-heading">Compare routes</h2><p className="comparison-note">Compare existing route facts and backend scores. No new ranking is applied.</p><div className="comparison-scroll"><table><thead><tr><th scope="col">Characteristic</th>{recommendations.map((route) => <th scope="col" key={route.candidate.id}><span className="rank">Rank {route.rank}</span><strong>{route.candidate.name}</strong>{route.candidate.id === selectedCandidateId && <span className="map-highlighted">Highlighted on map</span>}<button type="button" className="view-on-map" onClick={() => onSelectCandidate(route.candidate.id)}>View on map</button></th>)}</tr></thead><tbody>{rows.map((row) => <tr key={row.label}><th scope="row">{row.label}</th>{recommendations.map((route) => <td key={route.candidate.id}>{row.value(route)}</td>)}</tr>)}</tbody></table></div></section>;
}
