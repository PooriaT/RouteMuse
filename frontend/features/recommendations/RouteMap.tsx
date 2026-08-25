"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { GeoJSONSource, Map as MapLibreMap, MapLayerMouseEvent } from "maplibre-gl";

import type { RankedRecommendation } from "@/types/recommendations";

const SOURCE_ID = "route-candidates";
const UNSELECTED_LAYER = "route-candidates-unselected";
const SELECTED_LAYER = "route-candidates-selected";
const HIT_LAYER = "route-candidates-hit-area";

type RouteMapProps = {
  recommendations: RankedRecommendation[];
  selectedCandidateId: string | null;
  onSelectCandidate: (candidateId: string) => void;
  styleUrl?: string;
};

export function RouteMap({ recommendations, selectedCandidateId, onSelectCandidate, styleUrl = process.env.NEXT_PUBLIC_MAP_STYLE_URL }: RouteMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const onSelectRef = useRef(onSelectCandidate);
  const fittedResultRef = useRef<RankedRecommendation[] | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const data = useMemo(() => featureCollection(recommendations), [recommendations]);
  const latestDataRef = useRef(data);
  const latestRecommendationsRef = useRef(recommendations);
  const latestSelectionRef = useRef(selectedCandidateId);
  latestDataRef.current = data;
  latestRecommendationsRef.current = recommendations;
  latestSelectionRef.current = selectedCandidateId;

  useEffect(() => { onSelectRef.current = onSelectCandidate; }, [onSelectCandidate]);

  useEffect(() => {
    if (!styleUrl || !containerRef.current || mapRef.current) return;
    let disposed = false;
    let map: MapLibreMap | null = null;
    void import("maplibre-gl").then(({ default: maplibregl }) => {
      if (disposed || !containerRef.current) return;
      try {
        map = new maplibregl.Map({ container: containerRef.current, style: styleUrl, attributionControl: {} });
        mapRef.current = map;
        map.addControl(new maplibregl.NavigationControl({ showCompass: true }), "top-right");
        map.on("load", () => {
          if (!map) return;
          map.addSource(SOURCE_ID, { type: "geojson", data: latestDataRef.current });
          map.addLayer({ id: UNSELECTED_LAYER, type: "line", source: SOURCE_ID, filter: ["!=", ["get", "candidate_id"], latestSelectionRef.current ?? ""], paint: { "line-color": "#64748b", "line-width": 4, "line-opacity": 0.72 } });
          map.addLayer({ id: SELECTED_LAYER, type: "line", source: SOURCE_ID, filter: ["==", ["get", "candidate_id"], latestSelectionRef.current ?? ""], paint: { "line-color": "#047857", "line-width": 7, "line-opacity": 1 } });
          map.addLayer({ id: HIT_LAYER, type: "line", source: SOURCE_ID, paint: { "line-color": "#000000", "line-width": 18, "line-opacity": 0 } });
          fitAll(map, latestRecommendationsRef.current);
          fittedResultRef.current = latestRecommendationsRef.current;
        });
        const select = (event: MapLayerMouseEvent) => {
          const candidateId = event.features?.[0]?.properties?.candidate_id;
          if (typeof candidateId === "string") onSelectRef.current(candidateId);
        };
        map.on("click", HIT_LAYER, select);
        map.on("mouseenter", HIT_LAYER, () => { if (map) map.getCanvas().style.cursor = "pointer"; });
        map.on("mouseleave", HIT_LAYER, () => { if (map) map.getCanvas().style.cursor = ""; });
        map.on("error", () => setFailure("The route map could not be loaded. Your recommendations are still available."));
      } catch {
        setFailure("The route map could not be initialized. Your recommendations are still available.");
      }
    }).catch(() => setFailure("The route map could not be initialized. Your recommendations are still available."));
    return () => { disposed = true; map?.remove(); mapRef.current = null; };
  }, [styleUrl]); // Map lifecycle intentionally does not follow result/selection updates.

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    (map.getSource(SOURCE_ID) as GeoJSONSource | undefined)?.setData(data);
    if (fittedResultRef.current !== recommendations) {
      fitAll(map, recommendations);
      fittedResultRef.current = recommendations;
    }
  }, [data, recommendations]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.getLayer(SELECTED_LAYER)) return;
    const selected = selectedCandidateId ?? "";
    map.setFilter(UNSELECTED_LAYER, ["!=", ["get", "candidate_id"], selected]);
    map.setFilter(SELECTED_LAYER, ["==", ["get", "candidate_id"], selected]);
  }, [selectedCandidateId]);

  if (!styleUrl) return <MapMessage>Map is not configured. Set NEXT_PUBLIC_MAP_STYLE_URL to display route geometry.</MapMessage>;
  if (failure) return <MapMessage alert>{failure}</MapMessage>;
  return <div ref={containerRef} className="route-map" role="img" aria-label="Interactive map showing all ranked route candidates. Routes may be selected on the map; detailed accessible selection will be added with recommendation cards." />;
}

function MapMessage({ children, alert = false }: { children: React.ReactNode; alert?: boolean }) {
  return <div className="route-map grid place-items-center bg-slate-100 p-6 text-center text-slate-700" role={alert ? "alert" : "status"}>{children}</div>;
}

function featureCollection(recommendations: RankedRecommendation[]) {
  return { type: "FeatureCollection" as const, features: recommendations.map(({ candidate, rank }) => ({ type: "Feature" as const, properties: { candidate_id: candidate.id, rank, name: candidate.name }, geometry: candidate.geometry })) };
}

function fitAll(map: MapLibreMap, recommendations: RankedRecommendation[]) {
  const coordinates = recommendations.flatMap(({ candidate }) => candidate.geometry.coordinates);
  if (!coordinates.length) return;
  const longitudes = unwrapLongitudes(coordinates.map(([longitude]) => longitude));
  const latitudes = coordinates.map(([, latitude]) => latitude);
  map.fitBounds([[Math.min(...longitudes), Math.min(...latitudes)], [Math.max(...longitudes), Math.max(...latitudes)]], { padding: 36, maxZoom: 15, duration: 0 });
}

function unwrapLongitudes(values: number[]) {
  const reference = values[0];
  return values.map((value) => {
    let adjusted = value;
    while (adjusted - reference > 180) adjusted -= 360;
    while (adjusted - reference < -180) adjusted += 360;
    return adjusted;
  });
}
