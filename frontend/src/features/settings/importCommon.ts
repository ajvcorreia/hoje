import type { ImportResult } from './dataApi';

export const MB = 1_000_000;

export function readText(file: File): Promise<string> {
  if (typeof file.text === 'function') return file.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error('read failed'));
    reader.readAsText(file);
  });
}

export function plural(count: number, one: string, many: string) {
  return `${count} ${count === 1 ? one : many}`;
}

export function summary(result: ImportResult): string {
  const added = `${plural(result.events.create, 'event', 'events')} and ${plural(result.categories.create, 'category', 'categories')} added`;
  const skipped =
    result.events.skip_duplicate > 0
      ? `, ${plural(result.events.skip_duplicate, 'duplicate', 'duplicates')} skipped`
      : '';
  return `Import finished: ${added}${skipped}.`;
}
