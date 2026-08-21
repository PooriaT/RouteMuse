import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AthleteProfileSummary } from "@/features/planner/AthleteProfileSummary";

import { athleteProfile, emptyAthleteProfile } from "./athleteProfileFixture";

function renderProfile(
  overrides: Partial<React.ComponentProps<typeof AthleteProfileSummary>> = {},
) {
  const props: React.ComponentProps<typeof AthleteProfileSummary> = {
    connected: true,
    hasValidPeriod: true,
    profile: athleteProfile,
    status: "ready",
    error: null,
    onRetry: vi.fn(),
    ...overrides,
  };
  render(<AthleteProfileSummary {...props} />);
  return props;
}

describe("AthleteProfileSummary", () => {
  it("renders the dominant activity with factual supporting context", () => {
    renderProfile();

    expect(screen.getByText("Primary activity")).toBeInTheDocument();
    expect(screen.getAllByText("Road cycling")).toHaveLength(2);
    expect(screen.getByText(/79% of moving time/)).toHaveTextContent(
      "3 activities",
    );
    expect(screen.getByText(/79% of moving time/)).toHaveTextContent("240 km");
  });

  it("labels activity mix by moving time and exposes every numeric value as text", () => {
    renderProfile();

    const heading = screen.getByRole("heading", {
      name: "Activity mix by moving time",
    });
    const mix = heading.parentElement;
    expect(mix).not.toBeNull();
    expect(within(mix!).getByText("Road cycling")).toBeInTheDocument();
    expect(within(mix!).getByText("Running")).toBeInTheDocument();
    expect(within(mix!).getByText(/79% · 7 hr 30 min/)).toBeInTheDocument();
    expect(within(mix!).getByText(/21% · 2 hr/)).toBeInTheDocument();
    expect(within(mix!).getByText(/240 km · 2,400 m elevation/)).toBeInTheDocument();
  });

  it("renders percentile semantics, representative ranges, and sample sizes", () => {
    renderProfile();

    expect(screen.getByText("Typical distance").nextSibling).toHaveTextContent(
      "60 km–100 km",
    );
    expect(
      screen.getByText("Strong historical distance").nextSibling,
    ).toHaveTextContent("110 km");
    expect(screen.getByText("Typical duration").nextSibling).toHaveTextContent(
      "2 hr–3 hr",
    );
    expect(screen.getByText("Typical elevation").nextSibling).toHaveTextContent(
      "500 m–1,000 m",
    );
    expect(
      screen.getByText("Typical climbing density").nextSibling,
    ).toHaveTextContent("8 m/km–12 m/km");
    expect(screen.getAllByText("3 samples").length).toBeGreaterThan(0);
    expect(document.body).not.toHaveTextContent("Maximum capability");
    expect(document.body).not.toHaveTextContent("Safe maximum");
  });

  it("renders descriptive consistency and recent-versus-baseline signals", () => {
    renderProfile();

    expect(screen.getByText("Active weeks").nextSibling).toHaveTextContent(
      "3 of 14 (21%)",
    );
    expect(screen.getByText("Activities per week").nextSibling).toHaveTextContent(
      "0.2",
    );
    expect(
      screen.getByText("Days since last activity").nextSibling,
    ).toHaveTextContent("11");
    expect(screen.getByText("Longest inactivity gap").nextSibling).toHaveTextContent(
      "37 days",
    );
    expect(screen.getByText("Recent activity (28 days)").nextSibling).toHaveTextContent(
      "1 activity, 100 km, 3 hr",
    );
    expect(
      screen.getByText("Recent vs baseline moving time").nextSibling,
    ).toHaveTextContent("80% of baseline weekly volume");
  });

  it("renders the typed empty state without capability measurements", () => {
    renderProfile({ profile: emptyAthleteProfile });

    expect(
      screen.getByText("No supported activities are available for this period."),
    ).toBeInTheDocument();
    expect(screen.getByText(/Import another date range/)).toBeInTheDocument();
    expect(screen.queryByText("Typical distance")).not.toBeInTheDocument();
  });

  it("uses an accessible live loading status", () => {
    renderProfile({ profile: null, status: "loading" });

    const status = screen.getByRole("status", {
      name: "",
    });
    expect(status).toHaveTextContent("Loading athlete profile");
    expect(status).toHaveAttribute("aria-live", "polite");
  });

  it("shows a safe recoverable error", () => {
    const onRetry = vi.fn();
    renderProfile({
      profile: null,
      status: "error",
      error: "The athlete profile is temporarily unavailable. Try again.",
      onRetry,
    });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "temporarily unavailable",
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry profile" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("does not present a partial import as a definitive profile", () => {
    renderProfile({ profile: null, status: "partial" });

    expect(screen.getByRole("status")).toHaveTextContent(
      "not presenting it as a definitive refreshed profile",
    );
    expect(screen.queryByText("Primary activity")).not.toBeInTheDocument();
  });
});
