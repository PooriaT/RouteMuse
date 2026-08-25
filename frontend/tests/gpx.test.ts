import { afterEach, describe, expect, it, vi } from "vitest";

import { buildGpx, downloadGpx, GpxExportError, gpxFilename } from "@/lib/gpx";
import type { RouteCandidate } from "@/types/routes";

function candidate(coordinates: unknown = [[-123.123, 49.321, 120], [-122.9, 49.4]]) {
  return {
    id: "route-1", name: "Creek & Ridge <Loop>", activity_kind: "mountain_biking", distance_meters: 12_450,
    estimated_duration_seconds: null, elevation_gain_meters: 421, elevation_loss_meters: null,
    geometry: { type: "LineString", coordinates }, geojson_reference: null, route_shape: "loop",
    surface_breakdown: [], way_type_breakdown: [], technical_breakdown: [],
    provenance: [
      { provider: "ors", attribution: "Map & Trail <data>", source_ids: [], provider_request_id: "private-id", provider_profile: null },
      { provider: "ors", attribution: "Map & Trail <data>", source_ids: [], provider_request_id: null, provider_profile: null },
    ],
    data_confidence: null, generation_provenance: null, warnings: [], difficulty_score: null, athlete_fit_score: null,
    excitement_score: null, novelty_score: null, confidence_score: null, explanation: null,
  } as RouteCandidate;
}

afterEach(() => vi.restoreAllMocks());

describe("buildGpx", () => {
  it("builds an escaped GPX 1.1 track with original coordinate order and optional elevation", () => {
    const gpx = buildGpx(candidate());
    expect(gpx).toContain('<gpx version="1.1" creator="RouteMuse" xmlns="http://www.topografix.com/GPX/1/1"');
    expect(gpx).toContain("<name>Creek &amp; Ridge &lt;Loop&gt;</name>");
    expect(gpx).toContain("<type>Mountain Biking</type>");
    expect(gpx).toContain("Attribution: Map &amp; Trail &lt;data&gt;");
    expect(gpx.match(/<trkpt /g)).toHaveLength(2);
    expect(gpx).toContain('<trkpt lat="49.321" lon="-123.123"><ele>120</ele></trkpt>');
    expect(gpx).toContain('<trkpt lat="49.4" lon="-122.9" />');
    expect(gpx.indexOf('lat="49.321"')).toBeLessThan(gpx.indexOf('lat="49.4"'));
    expect(gpx).not.toContain("<time>");
    expect(gpx).not.toContain("private-id");
  });

  it.each([
    ["invalid latitude", [[0, 91], [0, 0]]],
    ["invalid longitude", [[181, 0], [0, 0]]],
    ["NaN", [[Number.NaN, 0], [0, 0]]],
    ["Infinity", [[0, Number.POSITIVE_INFINITY], [0, 0]]],
    ["too few points", [[0, 0]]],
  ])("rejects %s", (_label, coordinates) => {
    expect(() => buildGpx(candidate(coordinates))).toThrow(GpxExportError);
  });
});

describe("downloadGpx", () => {
  it("downloads a GPX Blob using a safe filename and revokes its object URL", () => {
    const createObjectURL = vi.fn(() => "blob:gpx");
    const revokeObjectURL = vi.fn();
    Object.defineProperties(URL, { createObjectURL: { configurable: true, value: createObjectURL }, revokeObjectURL: { configurable: true, value: revokeObjectURL } });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const append = vi.spyOn(document.body, "append");

    downloadGpx(candidate(), 1);

    const blob = createObjectURL.mock.calls[0][0] as Blob;
    expect(blob).toBeInstanceOf(Blob);
    expect(blob.type).toBe("application/gpx+xml");
    const anchor = append.mock.calls[0][0] as HTMLAnchorElement;
    expect(anchor.download).toBe("routemuse-creek-ridge-loop.gpx");
    expect(anchor.href).toBe("blob:gpx");
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:gpx");
  });

  it("does not begin a download for invalid geometry", () => {
    const createObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
    expect(() => downloadGpx(candidate([[0, 0]]))).toThrow(GpxExportError);
    expect(createObjectURL).not.toHaveBeenCalled();
  });

  it("sanitizes paths and has a stable fallback", () => {
    expect(gpxFilename("../A / Route???")).toBe("routemuse-a-route.gpx");
    expect(gpxFilename("///", 3)).toBe("routemuse-route-3.gpx");
  });
});
