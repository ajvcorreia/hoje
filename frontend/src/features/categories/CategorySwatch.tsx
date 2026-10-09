import type { Category } from '../../api/types';

/**
 * Small colour square, followed by the category's glyph when one is passed (the caller leaves it
 * out when icons are switched off in Settings) for a category. Colour comes from the palette via `data-cat`
 * (see `calendar.css`); it is decorative, so always pair it with the category name.
 */
export function CategorySwatch({
  colour,
  icon,
  className = '',
}: {
  colour: Category['colour'] | undefined;
  icon?: string | null;
  className?: string;
}) {
  return (
    <>
      <span
        aria-hidden="true"
        data-cat={colour ?? 'slate'}
        className={`cat-swatch inline-block size-3 shrink-0 rounded-sm ${className}`}
      />
      {icon ? (
        <span
          aria-hidden="true"
          data-testid="category-icon"
          className={`shrink-0 leading-none ${className}`}
        >
          {icon}
        </span>
      ) : null}
    </>
  );
}
