import type { ActivityType } from "@/types/activity";
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
async function request<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store" });
  } catch {
    throw new Error("RouteMuse API is unavailable");
  }
  if (!response.ok) throw new Error(`RouteMuse API request failed (${response.status})`);
  try {
    return await response.json() as T;
  } catch {
    throw new Error("RouteMuse API returned an invalid response");
  }
}
export const api = {
  health: () => request<{ status: "ok" }>("/health"),
  activityTypes: () => request<ActivityType[]>("/api/v1/activity-types"),
};
