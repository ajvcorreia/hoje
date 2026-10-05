import { format, isToday, isYesterday } from 'date-fns';

export const RESTORE_GUIDE_URL =
  'https://github.com/ajvcorreia/hoje/blob/main/deploy/backup/restore.md';

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 10 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
}

/** "today 02:00", "yesterday 02:00" or "5 Oct 2026, 02:00" in the browser's time zone. */
export function formatWhen(iso: string): string {
  const date = new Date(iso);
  if (isToday(date)) return `today ${format(date, 'HH:mm')}`;
  if (isYesterday(date)) return `yesterday ${format(date, 'HH:mm')}`;
  return format(date, 'd MMM yyyy, HH:mm');
}
