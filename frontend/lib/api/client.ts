import type { ActivityType } from "@/types/activity";
import type {
  StravaConnectionStatus,
  StravaSynchronizationRequest,
  StravaSynchronizationResult,
} from "@/types/strava";

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

type ApiErrorDetail = {
  code?: string;
  retry_after_seconds?: number | null;
  synchronization?: StravaSynchronizationResult;
};

type RequestOptions<TBody = never> = {
  method?: "GET" | "POST";
  body?: TBody;
  credentials?: RequestCredentials;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
    readonly retryAfterSeconds?: number,
    readonly synchronization?: StravaSynchronizationResult,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<TResponse, TBody = never>(
  path: string,
  options: RequestOptions<TBody> = {},
): Promise<TResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: options.method ?? "GET",
      body:
        options.body === undefined ? undefined : JSON.stringify(options.body),
      headers:
        options.body === undefined
          ? undefined
          : { "Content-Type": "application/json" },
      cache: "no-store",
      credentials: options.credentials,
    });
  } catch {
    throw new ApiError("RouteMuse API is unavailable", 0, "network_error");
  }

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new ApiError(
      `RouteMuse API request failed (${response.status})`,
      response.status,
      detail?.code,
      detail?.retry_after_seconds ?? undefined,
      detail?.synchronization,
    );
  }

  try {
    return (await response.json()) as TResponse;
  } catch {
    throw new ApiError(
      "RouteMuse API returned an invalid response",
      response.status,
      "invalid_response",
    );
  }
}

async function readErrorDetail(
  response: Response,
): Promise<ApiErrorDetail | null> {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (!payload.detail || typeof payload.detail !== "object") return null;
    return payload.detail as ApiErrorDetail;
  } catch {
    return null;
  }
}

export const api = {
  health: () => request<{ status: "ok" }>("/health"),
  activityTypes: () => request<ActivityType[]>("/api/v1/activity-types"),
  stravaConnectUrl: () => `${API_BASE_URL}/api/v1/strava/connect`,
  stravaStatus: () =>
    request<StravaConnectionStatus>("/api/v1/strava/status"),
  disconnectStrava: () =>
    request<StravaConnectionStatus>("/api/v1/strava/disconnect", {
      method: "POST",
    }),
  syncStravaActivities: (body: StravaSynchronizationRequest) =>
    request<StravaSynchronizationResult, StravaSynchronizationRequest>(
      "/api/v1/strava/sync",
      { method: "POST", body },
    ),
};
