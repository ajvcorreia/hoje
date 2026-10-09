import { useEffect, useId, useState } from 'react';
import type { Event as HojeEvent } from '../../api/types';
import { inputClass } from '../../components/ui/classes';
import { formatShortDate } from '../../lib/dates';
import { categoryMap, useCategories } from '../categories/api';
import { CategorySwatch } from '../categories/CategorySwatch';
import { useCategoryIcon } from '../categories/icons';
import { useSearchEvents } from '../events/api';

interface SearchBoxProps {
  /** An event was chosen from the results. */
  onPick(event: HojeEvent): void;
}

/** Header search: a debounced title search with a results dropdown (title, date, category). */
export function SearchBox({ onPick }: SearchBoxProps) {
  const listId = useId();
  const [text, setText] = useState('');
  const [term, setTerm] = useState('');
  const [open, setOpen] = useState(false);
  const { data: categories } = useCategories();
  const byId = categoryMap(categories);
  const iconOf = useCategoryIcon();

  useEffect(() => {
    const timer = window.setTimeout(() => setTerm(text), 250);
    return () => window.clearTimeout(timer);
  }, [text]);

  const search = useSearchEvents(term);
  const showResults = open && term.trim().length >= 2 && text.trim() === term.trim();

  return (
    <div
      className="relative"
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false);
      }}
    >
      <label htmlFor={`${listId}-input`} className="sr-only">
        Search events
      </label>
      <input
        id={`${listId}-input`}
        type="search"
        value={text}
        placeholder="Search events"
        autoComplete="off"
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') {
            e.stopPropagation();
            setOpen(false);
          }
        }}
        className={`${inputClass} w-48 md:w-56`}
      />
      {showResults ? (
        <div className="absolute right-0 z-30 mt-1 w-72 rounded-lg border border-border bg-surface p-1 shadow-md">
          {search.isPending ? (
            <p className="px-2 py-1.5 text-sm text-text-muted">Searching...</p>
          ) : search.isError ? (
            <p className="px-2 py-1.5 text-sm text-danger">Search failed</p>
          ) : search.data.items.length === 0 ? (
            <p className="px-2 py-1.5 text-sm text-text-muted">No events found</p>
          ) : (
            <ul aria-label="Search results">
              {search.data.items.map((event) => {
                const category = byId.get(event.category_id);
                return (
                  <li key={event.id}>
                    <button
                      type="button"
                      onClick={() => {
                        setOpen(false);
                        onPick(event);
                      }}
                      className="flex min-h-9 w-full items-center gap-2 rounded-md px-2 py-1 text-left text-sm hover:bg-surface-muted"
                    >
                      <CategorySwatch colour={category?.colour} icon={iconOf(category?.id)} />
                      <span className="min-w-0 flex-1">
                        <span className="block break-words font-medium">{event.title}</span>
                        <span className="block break-words text-xs text-text-muted">
                          {[formatShortDate(event.start_date), category?.name]
                            .filter(Boolean)
                            .join(' · ')}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
