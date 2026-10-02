import { useCategories, useUpdateCategory } from './api';
import { CategorySwatch } from './CategorySwatch';

/**
 * Category filter chips: one toggle per category; pressed = shown. Toggling persists the
 * category's `hidden` flag (`PATCH /categories/{id}`), so the choice follows the user
 * across devices. Shared by the desktop header and the mobile calendar.
 */
export function CategoryChips({
  className = '',
  scroll = false,
}: {
  className?: string;
  /** One horizontally scrollable row with 44 px targets (mobile) instead of wrapping. */
  scroll?: boolean;
}) {
  const { data: categories } = useCategories();
  const update = useUpdateCategory();
  if (!categories || categories.length === 0) return null;
  return (
    <div
      role="group"
      aria-label="Show categories"
      className={`flex gap-1 ${scroll ? 'flex-nowrap overflow-x-auto' : 'flex-wrap'} ${className}`}
    >
      {categories.map((category) => {
        const shown = !category.hidden;
        return (
          <button
            key={category.id}
            type="button"
            aria-pressed={shown}
            onClick={() => update.mutate({ category, patch: { hidden: shown } })}
            className={`inline-flex items-center gap-1.5 rounded-full border border-border text-xs ${
              scroll ? 'min-h-11 shrink-0 whitespace-nowrap px-3' : 'min-h-8 px-2.5 md:min-h-7'
            } ${shown ? 'bg-surface text-text' : 'bg-transparent text-text-muted line-through'}`}
          >
            <CategorySwatch colour={category.colour} className={shown ? '' : 'opacity-40'} />
            {category.name}
          </button>
        );
      })}
    </div>
  );
}
