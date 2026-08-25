import type { ActivityKind } from "./athleteProfile";

export type GeoJsonPosition =
  | [longitude: number, latitude: number]
  | [longitude: number, latitude: number, elevation: number];

export type GeoJsonLineString = {
  type: "LineString";
  coordinates: GeoJsonPosition[];
};

export type RouteShape = "loop" | "out_and_back" | "point_to_point";

export type ProviderProvenance = {
  provider: string;
  attribution: string;
  source_ids: string[];
  provider_request_id: string | null;
  provider_profile: string | null;
};

type DistanceBreakdown = {
  value: string;
  distance_meters: number | null;
  proportion: number | null;
};

export type SurfaceSummary = DistanceBreakdown;
export type WayTypeSummary = DistanceBreakdown;
export type TechnicalSummary = DistanceBreakdown & { characteristic: string };

export type CandidateGenerationProvenance = {
  algorithm_version: string;
  requested_distance_meters: number;
  effective_target_distance_meters: number;
  seed: number;
  round_trip_points: number;
  attempt_index: number;
};

export type RouteCandidate = {
  id: string;
  name: string;
  activity_kind: ActivityKind;
  distance_meters: number;
  estimated_duration_seconds: number | null;
  elevation_gain_meters: number | null;
  elevation_loss_meters: number | null;
  geometry: GeoJsonLineString;
  geojson_reference: string | null;
  route_shape: RouteShape | null;
  surface_breakdown: SurfaceSummary[];
  way_type_breakdown: WayTypeSummary[];
  technical_breakdown: TechnicalSummary[];
  provenance: ProviderProvenance[];
  data_confidence: number | null;
  generation_provenance: CandidateGenerationProvenance | null;
  warnings: string[];
  difficulty_score: number | null;
  athlete_fit_score: number | null;
  excitement_score: number | null;
  novelty_score: number | null;
  confidence_score: number | null;
  explanation: string | null;
};
