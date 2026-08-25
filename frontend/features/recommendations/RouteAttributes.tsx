import type { RouteCandidate } from "@/types/routes";
import { formatDistance, formatDuration, formatElevation, friendlyLabel, shapeLabels } from "./formatters";

export function RouteAttributes({ candidate }: { candidate: RouteCandidate }) {
  const summaries = [...candidate.surface_breakdown.slice(0, 2), ...candidate.way_type_breakdown.slice(0, 2)];
  return <>
    <dl className="route-facts">
      <div><dt>Distance</dt><dd>{formatDistance(candidate.distance_meters)}</dd></div>
      <div><dt>Estimated duration</dt><dd>{formatDuration(candidate.estimated_duration_seconds)}</dd></div>
      <div><dt>Elevation</dt><dd>{formatElevation(candidate.elevation_gain_meters)}</dd></div>
      <div><dt>Route shape</dt><dd>{candidate.route_shape ? shapeLabels[candidate.route_shape] : "Not available"}</dd></div>
    </dl>
    {summaries.length > 0 && <div className="mt-4"><h4 className="text-sm font-bold">Key route characteristics</h4><ul className="mt-2 flex flex-wrap gap-2">{summaries.map((item, index) => <li className="attribute-chip" key={`${item.value}-${index}`}>{friendlyLabel(item.value)}{item.proportion !== null ? ` · ${Math.round(item.proportion * 100)}%` : item.distance_meters !== null ? ` · ${formatDistance(item.distance_meters)}` : ""}</li>)}</ul></div>}
    {candidate.technical_breakdown.length > 0 && <details className="mt-4"><summary>Technical characteristics</summary><ul className="detail-list">{candidate.technical_breakdown.map((item, index) => <li key={`${item.characteristic}-${item.value}-${index}`}><strong>{friendlyLabel(item.characteristic)}:</strong> {friendlyLabel(item.value)}{item.proportion !== null && ` (${Math.round(item.proportion * 100)}%)`}</li>)}</ul></details>}
  </>;
}
