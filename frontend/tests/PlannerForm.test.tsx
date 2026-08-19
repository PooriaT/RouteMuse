import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PlannerForm } from "@/features/planner/PlannerForm";
const types = [{ value: "walking", label: "Walking" }, { value: "trail_running", label: "Trail Running" }];
describe("PlannerForm", () => {
  it("renders the planner shell and disabled integration", () => { render(<PlannerForm activityTypes={types}/>); expect(screen.getByLabelText("Start date")).toBeInTheDocument(); expect(screen.getByRole("button", { name: /Connect with Strava/ })).toBeDisabled(); expect(screen.getByText("Recommendations")).toBeInTheDocument(); });
  it("renders activity types supplied by the API layer", () => { render(<PlannerForm activityTypes={types}/>); expect(screen.getByRole("option", { name: "Walking" })).toHaveValue("walking"); expect(screen.getByRole("option", { name: "Trail Running" })).toHaveValue("trail_running"); });
});
