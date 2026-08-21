import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "@/lib/api/client";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("RouteMuse API client", () => {
  it("gets the authoritative Strava connection status", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        connected: true,
        athlete_id: "123456",
        granted_scopes: ["activity:read_all"],
      }),
    );

    await expect(api.stravaStatus()).resolves.toMatchObject({ connected: true });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/strava/status",
      expect.objectContaining({ method: "GET", cache: "no-store" }),
    );
  });

  it("posts a typed synchronization request as JSON", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        status: "completed",
        start_date: "2026-08-01",
        end_date: "2026-08-31",
        pages_fetched: 1,
        fetched: 0,
        inserted: 0,
        updated: 0,
        unsupported: 0,
      }),
    );
    const request = {
      start_date: "2026-08-01",
      end_date: "2026-08-31",
      timezone: "America/Vancouver",
    };

    await api.syncStravaActivities(request);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/strava/sync",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(request),
        headers: { "Content-Type": "application/json" },
      }),
    );
  });

  it("posts a typed athlete-profile request as JSON", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        period_start: "2026-08-01",
        period_end: "2026-08-31",
        timezone: "America/Vancouver",
        activities_analyzed: 0,
        unsupported_activities_excluded: 0,
        activity_summaries: [],
        dominant_activity: null,
        consistency_signals: [],
      }),
    );
    const request = {
      start_date: "2026-08-01",
      end_date: "2026-08-31",
      timezone: "America/Vancouver",
    };

    await api.athleteProfile(request);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/athlete-profile",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(request),
        headers: { "Content-Type": "application/json" },
      }),
    );
  });

  it("preserves safe status, retry, and partial-result error metadata", async () => {
    const partial = {
      status: "partial",
      start_date: "2026-08-01",
      end_date: "2026-08-31",
      pages_fetched: 2,
      fetched: 4,
      inserted: 3,
      updated: 0,
      unsupported: 1,
    };
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          detail: {
            code: "strava_rate_limited",
            message: "provider-safe message",
            retry_after_seconds: 120,
            synchronization: partial,
          },
        },
        429,
      ),
    );

    const error = await api
      .syncStravaActivities({
        start_date: "2026-08-01",
        end_date: "2026-08-31",
        timezone: "UTC",
      })
      .catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 429,
      code: "strava_rate_limited",
      retryAfterSeconds: 120,
      synchronization: partial,
    });
  });

  it("normalizes network failures into a status-aware API error", async () => {
    fetchMock.mockRejectedValue(new TypeError("network details"));

    await expect(api.stravaStatus()).rejects.toMatchObject({
      name: "ApiError",
      status: 0,
      code: "network_error",
    });
  });

  it("builds the OAuth navigation URL without fetching it", () => {
    expect(api.stravaConnectUrl()).toBe(
      "http://localhost:8000/api/v1/strava/connect",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
