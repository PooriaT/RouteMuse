import { describe, expect, it } from "vitest";

import { defaultHistoricalDateRange } from "@/features/planner/dateRange";

describe("defaultHistoricalDateRange", () => {
  it("uses the same calendar day one year earlier", () => {
    expect(defaultHistoricalDateRange(new Date(2026, 7, 19, 23, 30))).toEqual({
      startDate: "2025-08-19",
      endDate: "2026-08-19",
    });
  });

  it("safely maps leap day to the final valid day of February", () => {
    expect(defaultHistoricalDateRange(new Date(2024, 1, 29, 12))).toEqual({
      startDate: "2023-02-28",
      endDate: "2024-02-29",
    });
  });

  it("formats the local calendar date without a UTC day shift", () => {
    const localLateEvening = new Date(2026, 0, 2, 23, 59);
    expect(defaultHistoricalDateRange(localLateEvening).endDate).toBe("2026-01-02");
  });

  it("is deterministic when passed a specific date", () => {
    const date = new Date(2030, 10, 5, 8);
    expect(defaultHistoricalDateRange(date)).toEqual(defaultHistoricalDateRange(date));
  });
});
