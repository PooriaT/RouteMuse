"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";

import { ApiError, api } from "@/lib/api/client";
import type { ActivityType } from "@/types/activity";
import type {
  ActivityKind,
  AthleteProfile,
  AthleteProfileRequest,
} from "@/types/athleteProfile";
import type { PlanningArea } from "@/types/planningArea";

import {
  AthleteProfileSummary,
  type AthleteProfileViewStatus,
} from "./AthleteProfileSummary";
import { defaultHistoricalDateRange, type HistoricalDateRange } from "./dateRange";
import { StravaActivitySync } from "./StravaActivitySync";
import { LocationSearch } from "./LocationSearch";

type PlannerFormProps = {
  activityTypes: ActivityType[];
  activityTypesUnavailable?: boolean;
  initialDateRange?: HistoricalDateRange;
};

type ActivitySelection = {
  kind: ActivityKind | null;
  source: "automatic" | "user";
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
  const [timezone, setTimezone] = useState<string | null>(null);
  const [stravaConnected, setStravaConnected] = useState<boolean | null>(null);
  const [profile, setProfile] = useState<AthleteProfile | null>(null);
  const [profileStatus, setProfileStatus] =
    useState<AthleteProfileViewStatus>("idle");
  const [profileError, setProfileError] = useState<string | null>(null);
  const [planningArea, setPlanningArea] = useState<PlanningArea | null>(null);
  const [activitySelection, setActivitySelection] =
    useState<ActivitySelection>({ kind: null, source: "automatic" });
  const profileRequestSequence = useRef(0);
  const selectedProfileRequest = useRef<AthleteProfileRequest | null>(null);
  const hasInvalidRange = Boolean(
    dates.startDate && dates.endDate && dates.startDate > dates.endDate,
  );
  const hasValidPeriod = Boolean(
    dates.startDate && dates.endDate && !hasInvalidRange,
  );
  selectedProfileRequest.current =
    timezone && hasValidPeriod
      ? {
          start_date: dates.startDate,
          end_date: dates.endDate,
          timezone,
        }
      : null;

  useEffect(() => {
    setTimezone(Intl.DateTimeFormat().resolvedOptions().timeZone);
    if (!initialDateRange) {
      setDates(defaultHistoricalDateRange());
    }
  }, [initialDateRange]);

  const requestProfile = useCallback(async (request: AthleteProfileRequest) => {
    const sequence = ++profileRequestSequence.current;
    setProfile(null);
    setProfileError(null);
    setProfileStatus("loading");
    try {
      const response = await api.athleteProfile(request);
      if (sequence !== profileRequestSequence.current) return;
      setProfile(response);
      setProfileStatus("ready");
    } catch (error) {
      if (sequence !== profileRequestSequence.current) return;
      if (
        error instanceof ApiError &&
        error.code === "athlete_profile_history_incomplete"
      ) {
        setProfile(null);
        setProfileError(null);
        setProfileStatus("partial");
        return;
      }
      setProfileError(profileErrorMessage(error));
      setProfileStatus("error");
    }
  }, []);

  const loadSelectedProfile = useCallback(() => {
    if (!timezone || !hasValidPeriod) return;
    void requestProfile({
      start_date: dates.startDate,
      end_date: dates.endDate,
      timezone,
    });
  }, [dates.endDate, dates.startDate, hasValidPeriod, requestProfile, timezone]);

  const handleConnectionChange = useCallback((connected: boolean | null) => {
    setStravaConnected(connected);
    if (connected !== true) {
      profileRequestSequence.current += 1;
      setProfile(null);
      setProfileError(null);
      setProfileStatus("idle");
    }
  }, []);

  const handleSynchronizationComplete = useCallback(
    (request: AthleteProfileRequest) => {
      const selected = selectedProfileRequest.current;
      if (
        selected === null ||
        selected.start_date !== request.start_date ||
        selected.end_date !== request.end_date ||
        selected.timezone !== request.timezone
      ) {
        return;
      }
      void requestProfile(request);
    },
    [requestProfile],
  );

  const handleSynchronizationPartial = useCallback(() => {
    profileRequestSequence.current += 1;
    setProfile(null);
    setProfileError(null);
    setProfileStatus("partial");
  }, []);

  useEffect(() => {
    if (stravaConnected && hasValidPeriod && timezone) {
      loadSelectedProfile();
    } else if (stravaConnected && !hasValidPeriod) {
      profileRequestSequence.current += 1;
      setProfile(null);
      setProfileError(null);
      setProfileStatus("idle");
    }
  }, [hasValidPeriod, loadSelectedProfile, stravaConnected, timezone]);

  useEffect(() => {
    if (profileStatus !== "ready" || profile === null) return;

    setActivitySelection((current) => {
      const selectionIsSupported =
        current.kind !== null &&
        activityTypes.some((activityType) => activityType.value === current.kind);
      if (current.source === "user" && selectionIsSupported) return current;

      const dominantKind = profile.dominant_activity?.activity_kind ?? null;
      const supportedDominant =
        dominantKind !== null &&
        activityTypes.some((activityType) => activityType.value === dominantKind)
          ? dominantKind
          : null;
      if (
        current.kind === supportedDominant &&
        current.source === "automatic"
      ) {
        return current;
      }
      return { kind: supportedDominant, source: "automatic" };
    });
  }, [activityTypes, profile, profileStatus]);

  const handleActivityChange = (value: string) => {
    const selectedKind = activityTypes.find(
      (activityType) => activityType.value === value,
    )?.value;
    if (!selectedKind) return;
    setActivitySelection({ kind: selectedKind, source: "user" });
  };

  return (
    <main className="mx-auto max-w-5xl p-6 md:p-10">
      <header className="mb-8">
        <p className="font-semibold text-emerald-700">RouteMuse</p>
        <h1 className="text-4xl font-bold">Plan your next outdoor route</h1>
        <p className="mt-3 max-w-2xl text-slate-600">
          Start with your activity history, then add preferences to receive future
          provider-backed route recommendations.
        </p>
        <ol aria-label="Planner workflow" className="mt-5 grid gap-2 text-sm text-slate-600 sm:grid-cols-5">
          <li><strong>1.</strong> Historical range</li>
          <li><strong>2.</strong> Strava import</li>
          <li><strong>3.</strong> Athlete profile</li>
          <li><strong>4.</strong> Preferences</li>
          <li><strong>5.</strong> Recommendations</li>
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
        <StravaActivitySync
          dates={dates}
          hasInvalidRange={hasInvalidRange}
          timezone={timezone}
          onConnectionChange={handleConnectionChange}
          onSynchronizationComplete={handleSynchronizationComplete}
          onSynchronizationPartial={handleSynchronizationPartial}
        />
      </section>

      <AthleteProfileSummary
        connected={stravaConnected}
        hasValidPeriod={hasValidPeriod}
        profile={profile}
        status={profileStatus}
        error={profileError}
        onRetry={loadSelectedProfile}
      />

      <section aria-labelledby="preferences-heading" className="mb-6 rounded-xl bg-white p-6 shadow-sm">
        <h2 id="preferences-heading" className="mb-4 text-xl font-bold">Planning preferences</h2>
        <fieldset aria-describedby="preferences-status" className="grid gap-4 md:grid-cols-2">
          <legend className="sr-only">Route planning preferences</legend>
          <LocationSearch selected={planningArea} onSelect={setPlanningArea} />
          <div>
            <label htmlFor="activity-type">Activity type</label>
            <select
              id="activity-type"
              aria-describedby={
                activitySelection.source === "automatic" &&
                activitySelection.kind !== null
                  ? "activity-default-context"
                  : undefined
              }
              disabled={activityTypes.length === 0}
              value={activitySelection.kind ?? ""}
              onChange={(event) => handleActivityChange(event.target.value)}
            >
              <option value="">Choose an activity</option>
              {activityTypes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
            {activitySelection.source === "automatic" &&
              activitySelection.kind !== null && (
                <span
                  id="activity-default-context"
                  className="text-xs font-normal text-slate-500"
                >
                  Suggested from your athlete profile
                </span>
              )}
          </div>
          <label className="opacity-60">Target distance (km), optional<input disabled type="number" min="0" /></label>
          <label className="opacity-60">Target duration (minutes), optional<input disabled type="number" min="0" /></label>
          <label className="opacity-60">Desired challenge, optional<select disabled defaultValue=""><option value="">Any challenge</option><option value="easy">Easy</option><option value="moderate">Moderate</option><option value="hard">Hard</option></select></label>
          <label className="opacity-60">Route shape, optional<select disabled defaultValue=""><option value="">Any route shape</option><option value="loop">Loop</option><option value="out-and-back">Out-and-back</option><option value="point-to-point">Point-to-point</option></select></label>
        </fieldset>
        <p id="preferences-status" className="mt-4 text-sm text-slate-500">Choose a planning area and activity type now. Other route planning controls remain disabled until route generation is implemented.</p>
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

function profileErrorMessage(error: unknown) {
  if (!(error instanceof ApiError)) {
    return "The athlete profile could not be loaded. Try again.";
  }
  if (error.code === "strava_connection_required") {
    return "Connect Strava before loading an athlete profile.";
  }
  if (error.status === 422) {
    return "The selected historical period is invalid. Check both dates and try again.";
  }
  if (error.code === "network_error" || error.status === 0) {
    return "The RouteMuse API is unavailable. Check your connection and try again.";
  }
  return "The athlete profile is temporarily unavailable. Try again.";
}
