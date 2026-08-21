"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api } from "@/lib/api/client";
import type { StravaSynchronizationResult } from "@/types/strava";

import type { HistoricalDateRange } from "./dateRange";

type ConnectionState =
  | { status: "checking" }
  | { status: "disconnected" }
  | { status: "connected" }
  | { status: "error" };

type StravaActivitySyncProps = {
  dates: HistoricalDateRange;
  hasInvalidRange: boolean;
};

export function StravaActivitySync({
  dates,
  hasInvalidRange,
}: StravaActivitySyncProps) {
  const [connection, setConnection] = useState<ConnectionState>({
    status: "checking",
  });
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [disconnecting, setDisconnecting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [syncResult, setSyncResult] =
    useState<StravaSynchronizationResult | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const importInFlight = useRef(false);

  const refreshConnection = useCallback(async () => {
    setConnection({ status: "checking" });
    setConnectionError(null);
    try {
      const response = await api.stravaStatus();
      setConnection(
        response.connected
          ? { status: "connected" }
          : { status: "disconnected" },
      );
    } catch {
      setConnection({ status: "error" });
      setConnectionError(
        "RouteMuse could not check your Strava connection. Try again.",
      );
    }
  }, []);

  useEffect(() => {
    void refreshConnection();
    const refreshAfterHistoryRestore = (event: PageTransitionEvent) => {
      if (event.persisted) void refreshConnection();
    };
    window.addEventListener("pageshow", refreshAfterHistoryRestore);
    return () =>
      window.removeEventListener("pageshow", refreshAfterHistoryRestore);
  }, [refreshConnection]);

  async function disconnect() {
    if (disconnecting) return;
    setDisconnecting(true);
    setConnectionError(null);
    try {
      await api.disconnectStrava();
      setSyncResult(null);
      setSyncError(null);
      await refreshConnection();
    } catch (error) {
      setConnectionError(disconnectErrorMessage(error));
    } finally {
      setDisconnecting(false);
    }
  }

  async function synchronize() {
    if (
      importInFlight.current ||
      connection.status !== "connected" ||
      hasInvalidRange ||
      !dates.startDate ||
      !dates.endDate
    ) {
      return;
    }

    importInFlight.current = true;
    setImporting(true);
    setSyncResult(null);
    setSyncError(null);
    try {
      const result = await api.syncStravaActivities({
        start_date: dates.startDate,
        end_date: dates.endDate,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      });
      setSyncResult(result);
    } catch (error) {
      if (
        error instanceof ApiError &&
        error.synchronization?.status === "partial"
      ) {
        setSyncResult(error.synchronization);
      }
      setSyncError(syncErrorMessage(error));
    } finally {
      importInFlight.current = false;
      setImporting(false);
    }
  }

  const canSynchronize =
    connection.status === "connected" &&
    Boolean(dates.startDate && dates.endDate) &&
    !hasInvalidRange &&
    !importing;

  return (
    <div className="mt-5 border-t border-slate-200 pt-5">
      <ConnectionStatus
        connection={connection}
        connectionError={connectionError}
        disconnecting={disconnecting}
        onDisconnect={disconnect}
        onRetry={refreshConnection}
      />

      {connection.status === "connected" && (
        <div className="mt-5">
          <button
            type="button"
            disabled={!canSynchronize}
            aria-describedby="import-action-help"
            aria-busy={importing}
            onClick={synchronize}
            className="rounded-lg bg-emerald-700 px-5 py-3 font-semibold text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-600"
          >
            {importing ? "Importing activities…" : "Import activities"}
          </button>
          <p id="import-action-help" className="mt-2 text-sm text-slate-500">
            {hasInvalidRange
              ? "Choose a valid historical period before importing."
              : "Imports Strava activities from the selected calendar dates."}
          </p>
        </div>
      )}

      {importing && (
        <p role="status" aria-live="polite" className="mt-4 text-sm font-medium text-emerald-800">
          Importing activities…
        </p>
      )}

      {syncResult && <SyncResult result={syncResult} />}
      {syncError && (
        <p role="alert" className="mt-4 rounded-lg bg-red-50 p-4 text-sm text-red-800">
          {syncError}
        </p>
      )}
    </div>
  );
}

type ConnectionStatusProps = {
  connection: ConnectionState;
  connectionError: string | null;
  disconnecting: boolean;
  onDisconnect: () => Promise<void>;
  onRetry: () => Promise<void>;
};

function ConnectionStatus({
  connection,
  connectionError,
  disconnecting,
  onDisconnect,
  onRetry,
}: ConnectionStatusProps) {
  if (connection.status === "checking") {
    return (
      <p role="status" aria-live="polite" className="text-sm text-slate-600">
        Checking Strava connection…
      </p>
    );
  }

  if (connection.status === "error") {
    return (
      <div>
        <p role="alert" className="text-sm text-red-700">
          {connectionError}
        </p>
        <button
          type="button"
          onClick={() => void onRetry()}
          className="mt-3 rounded-lg border border-slate-300 px-4 py-2 font-semibold hover:bg-slate-50"
        >
          Check again
        </button>
      </div>
    );
  }

  if (connection.status === "disconnected") {
    return (
      <div>
        <p role="status" className="text-sm text-slate-600">
          Strava is not connected. Connect it before importing activities.
        </p>
        <a
          href={api.stravaConnectUrl()}
          className="mt-3 inline-block rounded-lg bg-orange-600 px-5 py-3 font-semibold text-white hover:bg-orange-700"
        >
          Connect with Strava
        </a>
      </div>
    );
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <p role="status" className="font-semibold text-emerald-800">
          Connected to Strava
        </p>
        <button
          type="button"
          disabled={disconnecting}
          aria-busy={disconnecting}
          onClick={() => void onDisconnect()}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-50 disabled:cursor-wait disabled:opacity-60"
        >
          {disconnecting ? "Disconnecting…" : "Disconnect"}
        </button>
      </div>
      {connectionError && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {connectionError}
        </p>
      )}
    </div>
  );
}

function SyncResult({ result }: { result: StravaSynchronizationResult }) {
  if (result.status === "completed" && result.fetched === 0) {
    return (
      <div role="status" className="mt-4 rounded-lg bg-slate-50 p-4 text-sm text-slate-700">
        <p className="font-semibold">No activities found</p>
        <p className="mt-1">
          No Strava activities were found in this period. Choose another date
          range and try again.
        </p>
        <p className="mt-1">{formatPeriod(result.start_date, result.end_date)}</p>
      </div>
    );
  }

  const partial = result.status === "partial";
  return (
    <div role="status" className="mt-4 rounded-lg bg-emerald-50 p-4 text-sm text-emerald-950">
      <p className="font-semibold">
        {partial
          ? "Some activities were imported, but synchronization did not finish."
          : "Activity import complete"}
      </p>
      <p className="mt-1">
        {formatPeriod(result.start_date, result.end_date)}
        {partial ? " You can retry the import." : ""}
      </p>
      <dl className="mt-3 grid gap-2 sm:grid-cols-3">
        <div>
          <dt className="text-slate-600">Imported</dt>
          <dd className="text-lg font-bold">{result.inserted}</dd>
        </div>
        <div>
          <dt className="text-slate-600">Updated</dt>
          <dd className="text-lg font-bold">{result.updated}</dd>
        </div>
        <div>
          <dt className="text-slate-600">Unsupported</dt>
          <dd className="text-lg font-bold">{result.unsupported}</dd>
        </div>
      </dl>
    </div>
  );
}

function formatPeriod(startDate: string, endDate: string) {
  return `Selected period: ${startDate} to ${endDate}.`;
}

function disconnectErrorMessage(error: unknown) {
  if (
    error instanceof ApiError &&
    error.code === "strava_token_revocation_failed"
  ) {
    return "Strava did not confirm the disconnect. Your account is still shown as connected; try again.";
  }
  return "RouteMuse could not disconnect Strava. Your account is still shown as connected; try again.";
}

function syncErrorMessage(error: unknown) {
  if (!(error instanceof ApiError)) {
    return "Activities could not be imported. Try again.";
  }

  switch (error.code) {
    case "strava_authentication_invalid":
    case "strava_token_refresh_failed":
      return "Your Strava authorization has expired. Disconnect and reconnect Strava, then try again.";
    case "strava_insufficient_scope":
      return "RouteMuse does not have permission to read your Strava activities. Reconnect Strava and grant activity access.";
    case "strava_rate_limited":
      return `Strava's rate limit paused this import. ${retryMessage(error.retryAfterSeconds)}`;
    case "strava_request_timed_out":
    case "strava_temporarily_unavailable":
      return "Strava is temporarily unavailable. Your saved progress is safe; try the import again later.";
    case "strava_network_error":
      return "RouteMuse could not reach Strava. Check your connection and try again.";
    case "network_error":
      return "The RouteMuse API is unavailable. Check your connection and try again.";
    default:
      if (error.status === 422) {
        return "The selected historical period is invalid. Check both dates and try again.";
      }
      return "Activities could not be imported. Try again.";
  }
}

function retryMessage(seconds?: number) {
  if (!seconds) return "Wait a little while, then retry.";
  if (seconds < 60) return `Retry in about ${seconds} seconds.`;
  const minutes = Math.ceil(seconds / 60);
  return `Retry in about ${minutes} ${minutes === 1 ? "minute" : "minutes"}.`;
}
