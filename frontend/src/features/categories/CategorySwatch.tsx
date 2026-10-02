import type { Category } from '../../api/types';

/**
 * Small colour square for a category. Colour comes from the palette via `data-cat`
 * (see `calendar.css`); it is decorative, so always pair it with the category name.
 */
export function CategorySwatch({
  colour,
  className = '',
}: {
  colour: Category['colour'] | undefined;
  className?: string;
}) {
  return (
    <span
      aria-hidden="true"
      data-cat={colour ?? 'slate'}
      className={`cat-swatch inline-block size-3 shrink-0 rounded-sm ${className}`}
    />
  );
}
