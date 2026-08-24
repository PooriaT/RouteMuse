import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocationSearch } from "@/features/planner/LocationSearch";
import { ApiError, api } from "@/lib/api/client";
import type { PlanningArea } from "@/types/planningArea";

vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return { ...actual, api: { ...actual.api, searchPlanningAreas: vi.fn() } };
});

const area: PlanningArea = {
  latitude: 49.32,
  longitude: -123.07,
  display_name: "North Vancouver, BC",
  bounding_box: { south: 49.2, west: -123.2, north: 49.4, east: -122.9 },
  source_provider: "openrouteservice",
  source_attribution: "© openrouteservice.org | © OpenStreetMap",
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
});

afterEach(() => vi.useRealTimers());

describe("LocationSearch", () => {
  it("does not request a very short query", async () => {
    render(<LocationSearch selected={null} onSelect={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Location"), { target: { value: "N" } });
    await act(() => vi.advanceTimersByTimeAsync(400));
    expect(api.searchPlanningAreas).not.toHaveBeenCalled();
  });

  it("debounces, loads, renders results, and selects normalized state", async () => {
    const pending = deferred<PlanningArea[]>();
    vi.mocked(api.searchPlanningAreas).mockReturnValue(pending.promise);
    const onSelect = vi.fn();
    const view = render(<LocationSearch selected={null} onSelect={onSelect} />);
    fireEvent.change(screen.getByLabelText("Location"), { target: { value: "North" } });
    await act(() => vi.advanceTimersByTimeAsync(299));
    expect(api.searchPlanningAreas).not.toHaveBeenCalled();
    await act(() => vi.advanceTimersByTimeAsync(1));
    expect(screen.getByText("Searching locations…")).toBeInTheDocument();
    await act(async () => pending.resolve([area]));
    fireEvent.click(screen.getByRole("button", { name: area.display_name }));
    expect(onSelect).toHaveBeenCalledWith(area);
    view.rerender(<LocationSearch selected={area} onSelect={onSelect} />);
    expect(screen.getByTestId("selected-planning-area")).toHaveTextContent(area.display_name);
    expect(screen.getByTestId("selected-planning-area")).toHaveTextContent(area.source_attribution);
  });

  it("reports no results and provider failures", async () => {
    vi.mocked(api.searchPlanningAreas).mockResolvedValueOnce([]);
    const view = render(<LocationSearch selected={null} onSelect={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Location"), { target: { value: "Nowhere" } });
    await act(() => vi.advanceTimersByTimeAsync(300));
    expect(screen.getByText("No locations found.")).toBeInTheDocument();

    vi.mocked(api.searchPlanningAreas).mockRejectedValueOnce(new ApiError("failed", 503));
    fireEvent.change(screen.getByLabelText("Location"), { target: { value: "Failure" } });
    await act(() => vi.advanceTimersByTimeAsync(300));
    expect(screen.getByRole("alert")).toHaveTextContent("Location search is unavailable");
    view.unmount();
  });

  it("does not let a stale response overwrite a newer query", async () => {
    const oldRequest = deferred<PlanningArea[]>();
    const newRequest = deferred<PlanningArea[]>();
    vi.mocked(api.searchPlanningAreas)
      .mockReturnValueOnce(oldRequest.promise)
      .mockReturnValueOnce(newRequest.promise);
    render(<LocationSearch selected={null} onSelect={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Location"), { target: { value: "Old" } });
    await act(() => vi.advanceTimersByTimeAsync(300));
    fireEvent.change(screen.getByLabelText("Location"), { target: { value: "New" } });
    await act(() => vi.advanceTimersByTimeAsync(300));
    await act(async () => newRequest.resolve([{ ...area, display_name: "New result" }]));
    await act(async () => oldRequest.resolve([{ ...area, display_name: "Old result" }]));
    expect(screen.getByRole("button", { name: "New result" })).toBeInTheDocument();
    expect(screen.queryByText("Old result")).not.toBeInTheDocument();
  });
});
