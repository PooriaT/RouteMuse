import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PlannerForm } from "@/features/planner/PlannerForm";
import { ApiError, api } from "@/lib/api/client";
import type { ActivityType } from "@/types/activity";
import type { AthleteProfile } from "@/types/athleteProfile";
import type {
  StravaConnectionStatus,
  StravaSynchronizationResult,
} from "@/types/strava";

import { athleteProfile, emptyAthleteProfile } from "./athleteProfileFixture";

vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      stravaConnectUrl: vi.fn(() =>
        "http://localhost:8000/api/v1/strava/connect"
      ),
      stravaStatus: vi.fn(),
      disconnectStrava: vi.fn(),
      syncStravaActivities: vi.fn(),
      athleteProfile: vi.fn(),
      searchPlanningAreas: vi.fn(),
      validatePlanningRequest: vi.fn(),
      recommendations: vi.fn(),
    },
  };
});

const types: ActivityType[] = [
  { value: "walking", label: "Walking" },
  { value: "trail_running", label: "Trail Running" },
  { value: "road_cycling", label: "Road Cycling" },
  { value: "hiking", label: "Hiking" },
];

const hikingProfile: AthleteProfile = {
  ...athleteProfile,
  dominant_activity: {
    ...athleteProfile.dominant_activity!,
    activity_kind: "hiking",
  },
};

const disconnected: StravaConnectionStatus = {
  connected: false,
  athlete_id: null,
  granted_scopes: [],
};

const connected: StravaConnectionStatus = {
  connected: true,
  athlete_id: "123456",
  granted_scopes: ["activity:read_all"],
};

const completed: StravaSynchronizationResult = {
  status: "completed",
  start_date: "2025-08-19",
  end_date: "2026-08-19",
  pages_fetched: 2,
  fetched: 5,
  inserted: 3,
  updated: 1,
  unsupported: 1,
};

const planningArea = {
  latitude: 49.2827,
  longitude: -123.1207,
  display_name: "Vancouver, British Columbia",
  bounding_box: null,
  source_provider: "openrouteservice",
  source_attribution: "© OpenStreetMap contributors",
};

function renderPlanner() {
  return render(
    <PlannerForm
      activityTypes={types}
      initialDateRange={{ startDate: "2025-08-19", endDate: "2026-08-19" }}
    />,
  );
}

function mockConnected() {
  vi.mocked(api.stravaStatus).mockResolvedValue(connected);
}

async function renderConnectedPlanner() {
  mockConnected();
  renderPlanner();
  await screen.findByText("Connected to Strava");
  return screen.getByRole("button", { name: "Import activities" });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.stravaStatus).mockResolvedValue(disconnected);
  vi.mocked(api.disconnectStrava).mockResolvedValue(disconnected);
  vi.mocked(api.syncStravaActivities).mockResolvedValue(completed);
  vi.mocked(api.athleteProfile).mockResolvedValue(emptyAthleteProfile);
  vi.mocked(api.validatePlanningRequest).mockImplementation(async (request) => request);
  vi.mocked(api.recommendations).mockResolvedValue({ recommendations: [], requested_recommendations: 3, generated_candidates: 0, ranking_version: "recommendation-v1", warnings: [] });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("PlannerForm", () => {
  it("does not render timezone-dependent default dates on the server", () => {
    const markup = renderToString(<PlannerForm activityTypes={types} />);

    expect(markup).toContain('type="date" value=""');
    expect(markup).not.toContain(defaultDateForServerTimezone());
  });

  it("initializes default dates from the browser calendar after mounting", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 19, 23));

    try {
      render(<PlannerForm activityTypes={types} />);
      expect(screen.getByLabelText("Start date")).toHaveValue("2025-08-19");
      expect(screen.getByLabelText("End date")).toHaveValue("2026-08-19");
    } finally {
      vi.useRealTimers();
    }
  });

  it("renders the historical period with deterministic local defaults", () => {
    renderPlanner();
    expect(
      screen.getByRole("heading", { name: "Historical activity period" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Start date")).toHaveValue("2025-08-19");
    expect(screen.getByLabelText("End date")).toHaveValue("2026-08-19");
  });

  it("shows a checking state while connection status is pending", () => {
    vi.mocked(api.stravaStatus).mockReturnValue(new Promise(() => undefined));

    renderPlanner();

    expect(screen.getByRole("status")).toHaveTextContent(
      "Checking Strava connection",
    );
    expect(
      screen.queryByRole("button", { name: "Import activities" }),
    ).not.toBeInTheDocument();
  });

  it("offers browser navigation to the backend connect endpoint when disconnected", async () => {
    renderPlanner();

    expect(await screen.findByText(/Strava is not connected/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Connect with Strava" }),
    ).toHaveAttribute(
      "href",
      "http://localhost:8000/api/v1/strava/connect",
    );
    expect(api.athleteProfile).not.toHaveBeenCalled();
  });

  it("shows the server-verified connected state", async () => {
    await renderConnectedPlanner();

    expect(screen.getByText("Connected to Strava")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disconnect" })).toBeEnabled();
  });

  it("loads an existing persisted profile only after confirming the connection", async () => {
    mockConnected();
    vi.mocked(api.athleteProfile).mockResolvedValue(athleteProfile);

    renderPlanner();

    expect(await screen.findAllByText("Road cycling")).toHaveLength(2);
    expect(api.athleteProfile).toHaveBeenCalledWith({
      start_date: "2025-08-19",
      end_date: "2026-08-19",
      timezone: expect.any(String),
    });
  });

  it("preserves an incomplete synchronization warning across profile loads", async () => {
    mockConnected();
    vi.mocked(api.athleteProfile).mockRejectedValue(
      new ApiError(
        "raw FastAPI detail",
        409,
        "athlete_profile_history_incomplete",
      ),
    );

    renderPlanner();

    const paused = await screen.findByText("Profile refresh paused");
    expect(paused.parentElement).toHaveAttribute("role", "status");
    expect(paused.parentElement).toHaveTextContent(
      "not presenting it as a definitive refreshed profile",
    );
    expect(screen.queryByText("Primary activity")).not.toBeInTheDocument();
  });

  it("rechecks server status when the planner is restored after OAuth navigation", async () => {
    vi.mocked(api.stravaStatus)
      .mockResolvedValueOnce(disconnected)
      .mockResolvedValueOnce(connected);
    renderPlanner();
    await screen.findByText(/Strava is not connected/);
    const pageShow = new Event("pageshow");
    Object.defineProperty(pageShow, "persisted", { value: true });

    window.dispatchEvent(pageShow);

    expect(await screen.findByText("Connected to Strava")).toBeInTheDocument();
    expect(api.stravaStatus).toHaveBeenCalledTimes(2);
  });

  it("shows a recoverable connection-status error", async () => {
    vi.mocked(api.stravaStatus).mockRejectedValue(new ApiError("raw", 503));
    renderPlanner();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "could not check your Strava connection",
    );
    expect(screen.getByRole("button", { name: "Check again" })).toBeEnabled();
  });

  it("prevents synchronization for an invalid date range", async () => {
    const importButton = await renderConnectedPlanner();

    fireEvent.change(screen.getByLabelText("Start date"), {
      target: { value: "2026-08-20" },
    });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Start date must be on or before end date.",
    );
    expect(
      screen.getByText(
        "Choose a valid historical period to load the athlete profile.",
      ),
    ).toBeInTheDocument();
    expect(importButton).toBeDisabled();
    fireEvent.click(importButton);
    expect(api.syncStravaActivities).not.toHaveBeenCalled();
  });

  it("enables synchronization only for a connected, valid range", async () => {
    const importButton = await renderConnectedPlanner();
    expect(importButton).toBeEnabled();

    vi.mocked(api.stravaStatus).mockResolvedValue(disconnected);
    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    expect(await screen.findByText(/Strava is not connected/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Import activities" }),
    ).not.toBeInTheDocument();
  });

  it("sends the selected dates and browser IANA timezone", async () => {
    vi.spyOn(
      Intl.DateTimeFormat.prototype,
      "resolvedOptions",
    ).mockReturnValue({
      locale: "en-CA",
      calendar: "gregory",
      numberingSystem: "latn",
      timeZone: "America/Vancouver",
      year: "numeric",
      month: "numeric",
      day: "numeric",
    });
    const importButton = await renderConnectedPlanner();

    fireEvent.click(importButton);

    await waitFor(() =>
      expect(api.syncStravaActivities).toHaveBeenCalledWith({
        start_date: "2025-08-19",
        end_date: "2026-08-19",
        timezone: "America/Vancouver",
      }),
    );
  });

  it("shows a truthful busy state and prevents duplicate submission", async () => {
    let finishImport: ((result: StravaSynchronizationResult) => void) | undefined;
    vi.mocked(api.syncStravaActivities).mockReturnValue(
      new Promise((resolve) => {
        finishImport = resolve;
      }),
    );
    const importButton = await renderConnectedPlanner();

    fireEvent.click(importButton);
    fireEvent.click(importButton);

    expect(importButton).toBeDisabled();
    expect(importButton).toHaveAttribute("aria-busy", "true");
    expect(screen.getAllByText("Importing activities…")).toHaveLength(2);
    expect(api.syncStravaActivities).toHaveBeenCalledTimes(1);

    finishImport?.(completed);
    expect(await screen.findByText("Activity import complete")).toBeInTheDocument();
  });

  it("shows imported, updated, and unsupported counts", async () => {
    const importButton = await renderConnectedPlanner();

    fireEvent.click(importButton);

    const result = await screen.findByText("Activity import complete");
    const resultPanel = result.parentElement;
    expect(resultPanel).not.toBeNull();
    expect(within(resultPanel!).getByText("Imported").nextSibling).toHaveTextContent("3");
    expect(within(resultPanel!).getByText("Updated").nextSibling).toHaveTextContent("1");
    expect(within(resultPanel!).getByText("Unsupported").nextSibling).toHaveTextContent("1");
    expect(resultPanel).toHaveTextContent(
      "Selected period: 2025-08-19 to 2026-08-19.",
    );
  });

  it("refreshes the profile after a completed synchronization", async () => {
    vi.mocked(api.athleteProfile)
      .mockResolvedValueOnce(emptyAthleteProfile)
      .mockResolvedValueOnce(athleteProfile);
    const importButton = await renderConnectedPlanner();
    await waitFor(() => expect(api.athleteProfile).toHaveBeenCalledTimes(1));

    fireEvent.click(importButton);

    expect(await screen.findByText("Activity import complete")).toBeInTheDocument();
    expect(await screen.findAllByText("Road cycling")).toHaveLength(2);
    expect(api.athleteProfile).toHaveBeenCalledTimes(2);
    expect(api.athleteProfile).toHaveBeenLastCalledWith({
      start_date: "2025-08-19",
      end_date: "2026-08-19",
      timezone: expect.any(String),
    });
  });

  it("does not let an older import refresh overwrite a newly selected period", async () => {
    let finishImport: ((result: StravaSynchronizationResult) => void) | undefined;
    const newPeriodProfile = {
      ...athleteProfile,
      period_start: "2025-09-01",
      period_end: "2026-08-19",
    };
    vi.mocked(api.athleteProfile).mockImplementation(async (request) =>
      request.start_date === "2025-09-01"
        ? newPeriodProfile
        : emptyAthleteProfile,
    );
    vi.mocked(api.syncStravaActivities).mockReturnValue(
      new Promise((resolve) => {
        finishImport = resolve;
      }),
    );
    const importButton = await renderConnectedPlanner();
    await waitFor(() => expect(api.athleteProfile).toHaveBeenCalledTimes(1));

    fireEvent.click(importButton);
    fireEvent.change(screen.getByLabelText("Start date"), {
      target: { value: "2025-09-01" },
    });

    await waitFor(() => expect(api.athleteProfile).toHaveBeenCalledTimes(2));
    expect(api.athleteProfile).toHaveBeenLastCalledWith({
      start_date: "2025-09-01",
      end_date: "2026-08-19",
      timezone: expect.any(String),
    });
    expect(await screen.findAllByText("Road cycling")).toHaveLength(2);
    expect(screen.getByText("Period").nextSibling).toHaveTextContent(
      "2025-09-01 to 2026-08-19",
    );

    finishImport?.(completed);
    expect(await screen.findByText("Activity import complete")).toBeInTheDocument();
    await waitFor(() => expect(api.athleteProfile).toHaveBeenCalledTimes(2));
    expect(screen.getByText("Period").nextSibling).toHaveTextContent(
      "2025-09-01 to 2026-08-19",
    );
  });

  it("shows a dedicated zero-activity state", async () => {
    vi.mocked(api.syncStravaActivities).mockResolvedValue({
      ...completed,
      pages_fetched: 1,
      fetched: 0,
      inserted: 0,
      updated: 0,
      unsupported: 0,
    });
    const importButton = await renderConnectedPlanner();

    fireEvent.click(importButton);

    expect(await screen.findByText("No activities found")).toBeInTheDocument();
    expect(screen.getByText(/Choose another date range/)).toBeInTheDocument();
  });

  it("retains partial counts and gives a rate-limit retry message", async () => {
    const partial: StravaSynchronizationResult = {
      ...completed,
      status: "partial",
      fetched: 4,
      inserted: 3,
      updated: 0,
    };
    vi.mocked(api.syncStravaActivities).mockRejectedValue(
      new ApiError("raw provider message", 429, "strava_rate_limited", 120, partial),
    );
    const importButton = await renderConnectedPlanner();

    fireEvent.click(importButton);

    expect(
      await screen.findByText(/synchronization did not finish/),
    ).toBeInTheDocument();
    expect(screen.getByText("Imported").nextSibling).toHaveTextContent("3");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Retry in about 2 minutes",
    );
    expect(screen.getByRole("alert")).not.toHaveTextContent("raw provider message");
    expect(screen.getByText("Profile refresh paused")).toBeInTheDocument();
    expect(screen.queryByText("Primary activity")).not.toBeInTheDocument();
    expect(api.athleteProfile).toHaveBeenCalledTimes(1);
  });

  it("recovers from a profile API failure without exposing raw payloads", async () => {
    vi.mocked(api.athleteProfile).mockRejectedValueOnce(
      new ApiError("raw FastAPI detail", 503, "athlete_profile_unavailable"),
    );
    await renderConnectedPlanner();

    const alert = await screen.findByText(/profile is temporarily unavailable/i);
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).not.toHaveTextContent("raw FastAPI detail");

    vi.mocked(api.athleteProfile).mockResolvedValueOnce(athleteProfile);
    fireEvent.click(screen.getByRole("button", { name: "Retry profile" }));

    expect(await screen.findAllByText("Road cycling")).toHaveLength(2);
  });

  it("shows a concise temporary-provider error", async () => {
    vi.mocked(api.syncStravaActivities).mockRejectedValue(
      new ApiError("secret provider response", 503, "strava_temporarily_unavailable"),
    );
    const importButton = await renderConnectedPlanner();

    fireEvent.click(importButton);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Strava is temporarily unavailable",
    );
    expect(screen.getByRole("alert")).not.toHaveTextContent(
      "secret provider response",
    );
  });

  it("disconnects, refreshes server status, and clears prior results", async () => {
    vi.mocked(api.stravaStatus)
      .mockResolvedValueOnce(connected)
      .mockResolvedValueOnce(disconnected);
    renderPlanner();
    await screen.findByText("Connected to Strava");
    fireEvent.click(screen.getByRole("button", { name: "Import activities" }));
    await screen.findByText("Activity import complete");

    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));

    expect(await screen.findByText(/Strava is not connected/)).toBeInTheDocument();
    expect(api.disconnectStrava).toHaveBeenCalledTimes(1);
    expect(api.stravaStatus).toHaveBeenCalledTimes(2);
    expect(screen.queryByText("Activity import complete")).not.toBeInTheDocument();
  });

  it("keeps the connected state after a failed disconnect", async () => {
    vi.mocked(api.disconnectStrava).mockRejectedValue(
      new ApiError("raw", 502, "strava_token_revocation_failed"),
    );
    await renderConnectedPlanner();

    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "still shown as connected",
    );
    expect(screen.getByText("Connected to Strava")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Import activities" })).toBeEnabled();
  });

  it("never renders token-like API fields", async () => {
    vi.mocked(api.stravaStatus).mockResolvedValue({
      ...connected,
      access_token: "never-render-access",
      refresh_token: "never-render-refresh",
    } as StravaConnectionStatus);
    vi.mocked(api.syncStravaActivities).mockResolvedValue({
      ...completed,
      access_token: "never-render-sync-token",
    } as StravaSynchronizationResult);
    renderPlanner();
    await screen.findByText("Connected to Strava");

    fireEvent.click(screen.getByRole("button", { name: "Import activities" }));
    await screen.findByText("Activity import complete");

    expect(document.body).not.toHaveTextContent("never-render-access");
    expect(document.body).not.toHaveTextContent("never-render-refresh");
    expect(document.body).not.toHaveTextContent("never-render-sync-token");
    expect(document.body).not.toHaveTextContent("access_token");
    expect(document.body).not.toHaveTextContent("refresh_token");
  });

  it("makes all planning inputs interactive", () => {
    renderPlanner();
    expect(screen.getByLabelText("Location")).toBeEnabled();
    expect(screen.getByLabelText("Activity type")).toBeEnabled();
    expect(screen.getByLabelText("Target distance (km), optional")).toBeEnabled();
    expect(screen.getByLabelText("Target duration (minutes), optional")).toBeEnabled();
    expect(screen.getByLabelText("Desired challenge, optional")).toBeEnabled();
    expect(screen.getByLabelText("Route shape, optional")).toBeEnabled();
    expect(screen.getByLabelText(/Novelty preference/)).toBeEnabled();
    expect(screen.getByRole("option", { name: "Walking" })).toHaveValue("walking");
    expect(screen.getByRole("option", { name: "Trail Running" })).toHaveValue(
      "trail_running",
    );
    expect(screen.getByText(/Optional values stay empty/)).toBeInTheDocument();
  });

  it("rejects missing required inputs and non-positive effort values locally", () => {
    renderPlanner();
    fireEvent.change(screen.getByLabelText("Target distance (km), optional"), { target: { value: "0" } });
    fireEvent.change(screen.getByLabelText("Target duration (minutes), optional"), { target: { value: "-2" } });
    fireEvent.click(screen.getByRole("button", { name: "Generate recommendations" }));

    expect(screen.getByText("Choose a planning area.")).toHaveAttribute("role", "alert");
    expect(screen.getByText("Choose an activity type.")).toHaveAttribute("role", "alert");
    expect(screen.getByText("Distance must be greater than zero.")).toHaveAttribute("role", "alert");
    expect(screen.getByText("Duration must be greater than zero.")).toHaveAttribute("role", "alert");
    expect(api.validatePlanningRequest).not.toHaveBeenCalled();
  });

  it("clears the missing-activity error as soon as a valid activity is selected", () => {
    renderPlanner();
    fireEvent.click(screen.getByRole("button", { name: "Generate recommendations" }));
    const selector = screen.getByLabelText("Activity type");
    expect(screen.getByText("Choose an activity type.")).toHaveAttribute(
      "role",
      "alert",
    );

    fireEvent.change(selector, { target: { value: "hiking" } });

    expect(screen.queryByText("Choose an activity type.")).not.toBeInTheDocument();
    expect(selector).not.toHaveAttribute("aria-describedby", "activity-kind-error");
  });

  it("rejects durations that would send fractional canonical seconds", () => {
    renderPlanner();
    const duration = screen.getByLabelText("Target duration (minutes), optional");
    fireEvent.change(duration, { target: { value: "2.51" } });
    fireEvent.click(screen.getByRole("button", { name: "Generate recommendations" }));

    expect(
      screen.getByText("Duration must convert to a whole number of seconds."),
    ).toHaveAttribute("role", "alert");
    expect(duration).toHaveAttribute("aria-invalid", "true");
    expect(api.validatePlanningRequest).not.toHaveBeenCalled();
  });

  it("requests recommendations with the canonical planning request", async () => {
    vi.mocked(api.searchPlanningAreas).mockResolvedValue([planningArea]);
    renderPlanner();
    fireEvent.change(screen.getByLabelText("Location"), { target: { value: "Vancouver" } });
    fireEvent.click(await screen.findByRole("button", { name: planningArea.display_name }));
    fireEvent.change(screen.getByLabelText("Activity type"), { target: { value: "hiking" } });
    fireEvent.change(screen.getByLabelText("Target distance (km), optional"), { target: { value: "25" } });
    fireEvent.change(screen.getByLabelText("Target duration (minutes), optional"), { target: { value: "90" } });
    fireEvent.change(screen.getByLabelText("Desired challenge, optional"), { target: { value: "hard" } });
    fireEvent.change(screen.getByLabelText("Route shape, optional"), { target: { value: "out_and_back" } });
    fireEvent.change(screen.getByLabelText(/Novelty preference/), { target: { value: "novel" } });

    fireEvent.click(screen.getByRole("button", { name: "Generate recommendations" }));

    await waitFor(() => expect(api.recommendations).toHaveBeenCalled());
    expect(api.recommendations).toHaveBeenCalledWith({
      planning_request: {
      planning_area: planningArea,
      activity_kind: "hiking",
      target_distance_meters: 25_000,
      target_duration_seconds: 5_400,
      desired_challenge: "hard",
      route_shape: "out_and_back",
      novelty_preference: "novel",
      },
      start_date: "2025-08-19",
      end_date: "2026-08-19",
      timezone: expect.any(String),
    });
    expect(screen.getByText(/Map is not configured/)).toBeInTheDocument();
  });

  it("presents backend planning validation failures accessibly", async () => {
    vi.mocked(api.searchPlanningAreas).mockResolvedValue([planningArea]);
    vi.mocked(api.recommendations).mockRejectedValue(new ApiError("raw", 422));
    renderPlanner();
    fireEvent.change(screen.getByLabelText("Location"), { target: { value: "Vancouver" } });
    fireEvent.click(await screen.findByRole("button", { name: planningArea.display_name }));
    fireEvent.change(screen.getByLabelText("Activity type"), { target: { value: "hiking" } });
    fireEvent.click(screen.getByRole("button", { name: "Generate recommendations" }));

    expect(await screen.findByText(/could not be generated/)).toHaveAttribute("role", "alert");
  });

  it("defaults road cycling from the athlete profile", async () => {
    mockConnected();
    vi.mocked(api.athleteProfile).mockResolvedValue(athleteProfile);

    renderPlanner();

    await waitFor(() =>
      expect(screen.getByLabelText("Activity type")).toHaveValue(
        "road_cycling",
      ),
    );
    expect(screen.getByText("Suggested from your athlete profile")).toBeInTheDocument();
  });

  it("defaults hiking from the athlete profile", async () => {
    mockConnected();
    vi.mocked(api.athleteProfile).mockResolvedValue(hikingProfile);

    renderPlanner();

    await waitFor(() =>
      expect(screen.getByLabelText("Activity type")).toHaveValue("hiking"),
    );
  });

  it("preserves a manual override across profile refreshes", async () => {
    mockConnected();
    vi.mocked(api.athleteProfile)
      .mockResolvedValueOnce(athleteProfile)
      .mockResolvedValueOnce(hikingProfile);
    renderPlanner();
    const selector = await screen.findByLabelText("Activity type");
    await waitFor(() => expect(selector).toHaveValue("road_cycling"));

    fireEvent.change(selector, { target: { value: "walking" } });
    expect(selector).toHaveValue("walking");
    expect(screen.queryByText("Suggested from your athlete profile")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Import activities" }));

    await waitFor(() => expect(api.athleteProfile).toHaveBeenCalledTimes(2));
    expect(selector).toHaveValue("walking");
  });

  it("allows the user to clear an activity selection", async () => {
    mockConnected();
    vi.mocked(api.athleteProfile)
      .mockResolvedValueOnce(athleteProfile)
      .mockResolvedValueOnce(hikingProfile);
    renderPlanner();
    const selector = await screen.findByLabelText("Activity type");
    await waitFor(() => expect(selector).toHaveValue("road_cycling"));

    fireEvent.change(selector, { target: { value: "" } });

    expect(selector).toHaveValue("");
    expect(screen.queryByText("Suggested from your athlete profile")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Import activities" }));
    await waitFor(() => expect(api.athleteProfile).toHaveBeenCalledTimes(2));
    expect(selector).toHaveValue("");
  });

  it("clears an automatic selection when the current profile is invalidated", async () => {
    mockConnected();
    vi.mocked(api.athleteProfile)
      .mockResolvedValueOnce(athleteProfile)
      .mockRejectedValueOnce(
        new ApiError("raw", 503, "athlete_profile_unavailable"),
      );
    renderPlanner();
    const selector = await screen.findByLabelText("Activity type");
    await waitFor(() => expect(selector).toHaveValue("road_cycling"));

    fireEvent.change(screen.getByLabelText("Start date"), {
      target: { value: "2025-09-01" },
    });

    await screen.findByRole("alert");
    expect(selector).toHaveValue("");
    expect(screen.queryByText("Suggested from your athlete profile")).not.toBeInTheDocument();
  });

  it("follows a refreshed profile while the selection remains automatic", async () => {
    mockConnected();
    vi.mocked(api.athleteProfile)
      .mockResolvedValueOnce(athleteProfile)
      .mockResolvedValueOnce(hikingProfile);
    renderPlanner();
    const selector = await screen.findByLabelText("Activity type");
    await waitFor(() => expect(selector).toHaveValue("road_cycling"));

    fireEvent.click(screen.getByRole("button", { name: "Import activities" }));

    await waitFor(() => expect(selector).toHaveValue("hiking"));
    expect(screen.getByText("Suggested from your athlete profile")).toBeInTheDocument();
  });

  it("does not invent a default for an empty profile", async () => {
    await renderConnectedPlanner();

    await waitFor(() => expect(api.athleteProfile).toHaveBeenCalled());
    expect(screen.getByLabelText("Activity type")).toHaveValue("");
  });

  it("safely ignores a dominant kind missing from API-provided options", async () => {
    mockConnected();
    vi.mocked(api.athleteProfile).mockResolvedValue({
      ...athleteProfile,
      dominant_activity: {
        ...athleteProfile.dominant_activity!,
        activity_kind: "swimming",
      },
    } as unknown as AthleteProfile);

    renderPlanner();

    await screen.findByText("Primary activity");
    expect(screen.getByLabelText("Activity type")).toHaveValue("");
    expect(screen.queryByText("Suggested from your athlete profile")).not.toBeInTheDocument();
  });

  it("keeps the API-backed selector keyboard accessible", () => {
    renderPlanner();
    const selector = screen.getByRole("combobox", { name: "Activity type" });

    selector.focus();
    expect(selector).toHaveFocus();
    expect(selector).toBeEnabled();
    fireEvent.change(selector, { target: { value: "trail_running" } });
    expect(selector).toHaveValue("trail_running");
  });

  it("renders a clear recommendations empty state", () => {
    renderPlanner();
    expect(
      screen.getByRole("heading", { name: "Recommendations" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/No recommendations yet/)).toBeInTheDocument();
  });

  it("keeps validation errors associated with both date fields", () => {
    renderPlanner();
    fireEvent.change(screen.getByLabelText("Start date"), {
      target: { value: "2026-08-20" },
    });
    const alert = screen.getByText("Start date must be on or before end date.");
    expect(alert).toHaveAttribute("role", "alert");
    expect(screen.getByLabelText("Start date")).toHaveAttribute(
      "aria-describedby",
      alert.id,
    );
    expect(screen.getByLabelText("End date")).toHaveAttribute(
      "aria-describedby",
      alert.id,
    );
  });

  it("shows a user-safe activity-type fallback", () => {
    render(
      <PlannerForm
        activityTypes={[]}
        activityTypesUnavailable
        initialDateRange={{ startDate: "2025-08-19", endDate: "2026-08-19" }}
      />,
    );
    expect(
      screen.getByText(/Activity types are temporarily unavailable/),
    ).toHaveAttribute("role", "status");
  });
});

function defaultDateForServerTimezone() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}
