/**
 * `scrollLeft` that centres a column of `columnWidth` starting at `columnLeft` in a viewport of
 * `viewportWidth`, clamped to the scrollable range `[0, scrollWidth - viewportWidth]`.
 */
export function centerScrollLeft(
  columnLeft: number,
  columnWidth: number,
  viewportWidth: number,
  scrollWidth: number,
): number {
  const max = Math.max(0, scrollWidth - viewportWidth);
  const target = columnLeft - (viewportWidth - columnWidth) / 2;
  return Math.min(max, Math.max(0, target));
}
