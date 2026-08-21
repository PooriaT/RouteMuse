export type StravaConnectionStatus = {
  connected: boolean;
  athlete_id: string | null;
  granted_scopes: string[];
};

export type StravaSynchronizationStatus =
  | "running"
  | "completed"
  | "partial"
  | "failed";

export type StravaSynchronizationRequest = {
  start_date: string;
  end_date: string;
  timezone: string;
};

export type StravaSynchronizationResult = {
  status: StravaSynchronizationStatus;
  start_date: string;
  end_date: string;
  pages_fetched: number;
  fetched: number;
  inserted: number;
  updated: number;
  unsupported: number;
};
