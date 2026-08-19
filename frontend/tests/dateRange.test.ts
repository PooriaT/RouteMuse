import { describe, expect, it } from "vitest";
import { defaultHistoricalDateRange } from "@/features/planner/dateRange";
describe("defaultHistoricalDateRange", () => {
  it("uses the same calendar day one year earlier", () => expect(defaultHistoricalDateRange(new Date(2026, 7, 19))).toEqual({ startDate: "2025-08-19", endDate: "2026-08-19" }));
  it("safely maps leap day to February 28", () => expect(defaultHistoricalDateRange(new Date(2024, 1, 29))).toEqual({ startDate: "2023-02-28", endDate: "2024-02-29" }));
});
