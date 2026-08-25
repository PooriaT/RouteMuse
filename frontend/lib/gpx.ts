import type { RouteCandidate } from "@/types/routes";

export class GpxExportError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "GpxExportError";
  }
}

function escapeXml(value: string | number) {
  return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&apos;");
}

function validatePoint(point: unknown, index: number) {
  if (!Array.isArray(point) || point.length < 2) throw new GpxExportError(`Route point ${index + 1} is missing coordinates.`);
  const [longitude, latitude, elevation] = point;
  if (typeof longitude !== "number" || !Number.isFinite(longitude) || longitude < -180 || longitude > 180) throw new GpxExportError(`Route point ${index + 1} has an invalid longitude.`);
  if (typeof latitude !== "number" || !Number.isFinite(latitude) || latitude < -90 || latitude > 90) throw new GpxExportError(`Route point ${index + 1} has an invalid latitude.`);
  if (elevation !== undefined && (typeof elevation !== "number" || !Number.isFinite(elevation))) throw new GpxExportError(`Route point ${index + 1} has an invalid elevation.`);
  return { longitude, latitude, elevation: elevation as number | undefined };
}

/** Serialize the candidate's canonical geometry without changing its point order or facts. */
export function buildGpx(candidate: RouteCandidate) {
  const coordinates = candidate.geometry?.coordinates;
  if (!Array.isArray(coordinates) || coordinates.length < 2) throw new GpxExportError("A route needs at least two track points to export GPX.");
  const points = coordinates.map(validatePoint);
  const activity = candidate.activity_kind.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  const attributions = [...new Set(candidate.provenance.map(({ attribution }) => attribution.trim()).filter(Boolean))];
  const facts = [`Distance: ${candidate.distance_meters} m`];
  if (candidate.elevation_gain_meters !== null) facts.push(`Elevation gain: ${candidate.elevation_gain_meters} m`);
  if (attributions.length > 0) facts.push(`Attribution: ${attributions.join(" · ")}`);
  const trackPoints = points.map(({ longitude, latitude, elevation }) => elevation === undefined
    ? `      <trkpt lat="${escapeXml(latitude)}" lon="${escapeXml(longitude)}" />`
    : `      <trkpt lat="${escapeXml(latitude)}" lon="${escapeXml(longitude)}"><ele>${escapeXml(elevation)}</ele></trkpt>`).join("\n");

  return `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="RouteMuse" xmlns="http://www.topografix.com/GPX/1/1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">
  <trk>
    <name>${escapeXml(candidate.name)}</name>
    <desc>${escapeXml(facts.join("; "))}</desc>
    <type>${escapeXml(activity)}</type>
    <trkseg>
${trackPoints}
    </trkseg>
  </trk>
</gpx>`;
}

export function gpxFilename(candidateName: string, rank?: number) {
  const safeName = candidateName.normalize("NFKD").replace(/[\u0000-\u001f\u007f]/g, " ").replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase();
  return `routemuse-${safeName || `route${rank ? `-${rank}` : ""}`}.gpx`;
}

/** Download a pre-existing candidate; this performs no network or routing work. */
export function downloadGpx(candidate: RouteCandidate, rank?: number) {
  const blob = new Blob([buildGpx(candidate)], { type: "application/gpx+xml" });
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = gpxFilename(candidate.name, rank);
  anchor.style.display = "none";
  document.body.append(anchor);
  try { anchor.click(); } finally { anchor.remove(); URL.revokeObjectURL(objectUrl); }
}
