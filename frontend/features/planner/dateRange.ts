export type HistoricalDateRange = { startDate: string; endDate: string };
function localDateString(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
export function defaultHistoricalDateRange(today = new Date()): HistoricalDateRange {
  const end = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const targetYear = end.getFullYear() - 1;
  const start = new Date(targetYear, end.getMonth(), end.getDate());
  if (start.getMonth() !== end.getMonth()) start.setDate(0); // Feb 29 -> Feb 28
  return { startDate: localDateString(start), endDate: localDateString(end) };
}
