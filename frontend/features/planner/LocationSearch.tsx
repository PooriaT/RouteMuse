"use client";

import { useEffect, useRef, useState } from "react";

import { ApiError, api } from "@/lib/api/client";
import type { PlanningArea } from "@/types/planningArea";

const MINIMUM_QUERY_LENGTH = 2;
const DEBOUNCE_MILLISECONDS = 300;

type LocationSearchProps = {
  selected: PlanningArea | null;
  onSelect: (area: PlanningArea) => void;
};

export function LocationSearch({ selected, onSelect }: LocationSearchProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PlanningArea[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const requestSequence = useRef(0);

  useEffect(() => {
    const trimmed = query.trim();
    const sequence = ++requestSequence.current;
    if (trimmed.length < MINIMUM_QUERY_LENGTH) {
      setResults([]);
      setStatus("idle");
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setStatus("loading");
      try {
        const areas = await api.searchPlanningAreas(trimmed, controller.signal);
        if (sequence !== requestSequence.current) return;
        setResults(areas);
        setStatus("ready");
      } catch (error) {
        if (sequence !== requestSequence.current || controller.signal.aborted) return;
        setResults([]);
        setStatus("error");
        // Keep provider details private; ApiError is checked only to normalize failures.
        void (error instanceof ApiError);
      }
    }, DEBOUNCE_MILLISECONDS);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  return (
    <div className="md:col-span-2">
      <label htmlFor="location-search">Location</label>
      <input
        id="location-search"
        type="search"
        placeholder="Area or location"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <div aria-live="polite" className="mt-2 text-sm text-slate-600">
        {status === "loading" && <p>Searching locations…</p>}
        {status === "ready" && results.length === 0 && <p>No locations found.</p>}
        {status === "error" && <p role="alert">Location search is unavailable. Try again.</p>}
      </div>
      {results.length > 0 && (
        <ul aria-label="Location search results" className="mt-2 grid gap-2">
          {results.map((area) => (
            <li key={`${area.latitude}:${area.longitude}:${area.display_name}`}>
              <button
                type="button"
                className="w-full rounded border border-slate-300 p-3 text-left hover:border-emerald-600"
                onClick={() => {
                  onSelect(area);
                  setQuery(area.display_name);
                  setResults([]);
                  setStatus("idle");
                }}
              >
                {area.display_name}
              </button>
            </li>
          ))}
        </ul>
      )}
      {selected && (
        <div className="mt-3 rounded border border-emerald-300 bg-emerald-50 p-3" data-testid="selected-planning-area">
          <strong>Selected planning area:</strong> {selected.display_name}
          <p className="text-xs text-slate-600">{selected.source_attribution}</p>
        </div>
      )}
    </div>
  );
}
