import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PlannerForm } from "@/features/planner/PlannerForm";

const types = [
  { value: "walking", label: "Walking" },
  { value: "trail_running", label: "Trail Running" },
];

function renderPlanner() {
  return render(<PlannerForm activityTypes={types} today={new Date(2026, 7, 19, 23)} />);
}

describe("PlannerForm", () => {
  it("renders the historical period with deterministic local defaults", () => {
    renderPlanner();
    expect(screen.getByRole("heading", { name: "Historical activity period" })).toBeInTheDocument();
    expect(screen.getByLabelText("Start date")).toHaveValue("2025-08-19");
    expect(screen.getByLabelText("End date")).toHaveValue("2026-08-19");
  });

  it("shows Strava as explicitly unavailable", () => {
    renderPlanner();
    expect(screen.getByRole("button", { name: "Connect with Strava" })).toBeDisabled();
    expect(screen.getByText(/Not implemented/)).toBeInTheDocument();
  });

  it("renders disabled planning controls and API-supplied activity types", () => {
    renderPlanner();
    expect(screen.getByLabelText("Location")).toBeDisabled();
    expect(screen.getByLabelText("Activity type")).toBeDisabled();
    expect(screen.getByLabelText("Target distance (km), optional")).toBeDisabled();
    expect(screen.getByLabelText("Target duration (minutes), optional")).toBeDisabled();
    expect(screen.getByLabelText("Desired challenge, optional")).toBeDisabled();
    expect(screen.getByLabelText("Route shape, optional")).toBeDisabled();
    expect(screen.getByRole("option", { name: "Walking" })).toHaveValue("walking");
    expect(screen.getByRole("option", { name: "Trail Running" })).toHaveValue("trail_running");
  });

  it("renders a clear recommendations empty state", () => {
    renderPlanner();
    expect(screen.getByRole("heading", { name: "Recommendations" })).toBeInTheDocument();
    expect(screen.getByText(/No recommendations yet/)).toBeInTheDocument();
  });

  it("announces a start date after the end date as invalid", () => {
    renderPlanner();
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-08-20" } });
    expect(screen.getByRole("alert")).toHaveTextContent("Start date must be on or before end date.");
    expect(screen.getByLabelText("Start date")).toHaveAttribute("aria-invalid", "true");
  });

  it("shows a user-safe activity-type fallback", () => {
    render(<PlannerForm activityTypes={[]} activityTypesUnavailable today={new Date(2026, 7, 19)} />);
    expect(screen.getByRole("status")).toHaveTextContent("Activity types are temporarily unavailable");
  });
});
