"use client";

import { useEffect, useId, useState } from "react";

import type { ActivityType } from "@/types/activity";

import { defaultHistoricalDateRange, type HistoricalDateRange } from "./dateRange";
import { StravaActivitySync } from "./StravaActivitySync";

type PlannerFormProps = {
  activityTypes: ActivityType[];
  activityTypesUnavailable?: boolean;
  initialDateRange?: HistoricalDateRange;
};

export function PlannerForm({
  activityTypes,
  activityTypesUnavailable = false,
  initialDateRange,
}: PlannerFormProps) {
  const [dates, setDates] = useState(() =>
    initialDateRange
      ? initialDateRange
      : { startDate: "", endDate: "" },
  );
  const validationMessageId = useId();
  const hasInvalidRange = Boolean(
    dates.startDate && dates.endDate && dates.startDate > dates.endDate,
  );

  useEffect(() => {
    if (!initialDateRange) {
      setDates(defaultHistoricalDateRange());
    }
  }, [initialDateRange]);

  return (
    <main className="mx-auto max-w-5xl p-6 md:p-10">
      <header className="mb-8">
        <p className="font-semibold text-emerald-700">RouteMuse</p>
        <h1 className="text-4xl font-bold">Plan your next outdoor route</h1>
        <p className="mt-3 max-w-2xl text-slate-600">
          Start with your activity history, then add preferences to receive future
          provider-backed route recommendations.
        </p>
        <ol aria-label="Planner workflow" className="mt-5 grid gap-2 text-sm text-slate-600 sm:grid-cols-4">
          <li><strong>1.</strong> Historical range</li>
          <li><strong>2.</strong> Strava import</li>
          <li><strong>3.</strong> Preferences</li>
          <li><strong>4.</strong> Recommendations</li>
        </ol>
      </header>

      <section aria-labelledby="history-heading" className="mb-6 rounded-xl bg-white p-6 shadow-sm">
        <h2 id="history-heading" className="mb-4 text-xl font-bold">Historical activity period</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <label>
            Start date
            <input
              aria-describedby={hasInvalidRange ? validationMessageId : undefined}
              aria-invalid={hasInvalidRange}
              type="date"
              value={dates.startDate}
              onChange={(event) => setDates((current) => ({ ...current, startDate: event.target.value }))}
            />
          </label>
          <label>
            End date
            <input
              aria-describedby={hasInvalidRange ? validationMessageId : undefined}
              aria-invalid={hasInvalidRange}
              type="date"
              value={dates.endDate}
              onChange={(event) => setDates((current) => ({ ...current, endDate: event.target.value }))}
            />
          </label>
        </div>
        {hasInvalidRange && (
          <p id={validationMessageId} role="alert" className="mt-3 text-sm font-medium text-red-700">
            Start date must be on or before end date.
          </p>
        )}
        <StravaActivitySync dates={dates} hasInvalidRange={hasInvalidRange} />
      </section>

      <section aria-labelledby="preferences-heading" className="mb-6 rounded-xl bg-white p-6 shadow-sm">
        <h2 id="preferences-heading" className="mb-4 text-xl font-bold">Planning preferences</h2>
        <fieldset disabled aria-describedby="preferences-status" className="grid gap-4 opacity-60 md:grid-cols-2">
          <legend className="sr-only">Route planning preferences</legend>
          <label>Location<input placeholder="Area or location" /></label>
          <label>
            Activity type
            <select defaultValue="">
              <option value="">Select after connecting</option>
              {activityTypes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </label>
          <label>Target distance (km), optional<input type="number" min="0" /></label>
          <label>Target duration (minutes), optional<input type="number" min="0" /></label>
          <label>Desired challenge, optional<select defaultValue=""><option value="">Any challenge</option><option value="easy">Easy</option><option value="moderate">Moderate</option><option value="hard">Hard</option></select></label>
          <label>Route shape, optional<select defaultValue=""><option value="">Any route shape</option><option value="loop">Loop</option><option value="out-and-back">Out-and-back</option><option value="point-to-point">Point-to-point</option></select></label>
        </fieldset>
        <p id="preferences-status" className="mt-4 text-sm text-slate-500">Athlete analysis and route planning are not available yet.</p>
        {activityTypesUnavailable && (
          <p role="status" className="mt-2 text-sm text-amber-700">Activity types are temporarily unavailable. Try again when the RouteMuse API is running.</p>
        )}
      </section>

      <section aria-labelledby="recommendations-heading" className="rounded-xl border-2 border-dashed border-emerald-200 p-8 text-center">
        <h2 id="recommendations-heading" className="text-xl font-bold">Recommendations</h2>
        <p className="mt-2 text-slate-600">No recommendations yet. Provider-backed, personalized route candidates will appear here in a future release.</p>
      </section>
    </main>
  );
}
