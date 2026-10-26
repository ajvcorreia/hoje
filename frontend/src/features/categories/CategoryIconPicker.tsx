import { useState, type FormEvent } from 'react';
import { btnSecondary, inputClass } from '../../components/ui/classes';
import { firstEmoji, searchIcons } from './iconCatalogue';

/**
 * The icon choices for one category: a search box, the grouped glyphs, a field for any other
 * emoji, and "No icon".
 */
export function CategoryIconPicker({
  categoryName,
  value,
  onPick,
}: {
  categoryName: string;
  value: string | null | undefined;
  onPick(icon: string | null): void;
}) {
  const [query, setQuery] = useState('');
  const [own, setOwn] = useState('');
  const [ownError, setOwnError] = useState(false);
  const groups = searchIcons(query);

  const submitOwn = (event: FormEvent) => {
    event.preventDefault();
    const emoji = firstEmoji(own);
    setOwnError(!emoji);
    if (!emoji) return;
    onPick(emoji);
    setOwn('');
  };

  return (
    <div role="group" aria-label={`Icon for ${categoryName}`} className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          aria-label={`Search icons for ${categoryName}`}
          placeholder="Search icons (e.g. birthday, gym)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className={`${inputClass} min-w-0 flex-1`}
        />
        <button
          type="button"
          className={`${btnSecondary} h-9 px-2 text-xs md:h-8`}
          disabled={!value}
          onClick={() => onPick(null)}
        >
          No icon
        </button>
      </div>
      <div className="max-h-64 space-y-2 overflow-y-auto pr-1">
        {groups.map((group) => (
          <section key={group.label} aria-label={group.label}>
            <h4 className="mb-1 text-xs font-medium text-text-muted">{group.label}</h4>
            <div className="flex flex-wrap gap-1">
              {group.icons.map(([icon, keywords]) => (
                <button
                  key={icon}
                  type="button"
                  aria-label={keywords.split(' ')[0]}
                  title={keywords}
                  aria-pressed={value === icon}
                  onClick={() => onPick(icon)}
                  className={`${btnSecondary} size-9 px-0 text-base leading-none md:size-8 ${
                    value === icon ? 'border-text' : ''
                  }`}
                >
                  {icon}
                </button>
              ))}
            </div>
          </section>
        ))}
        {groups.length === 0 ? (
          <p className="text-sm text-text-muted">No icons match. Paste any emoji below.</p>
        ) : null}
      </div>
      <form onSubmit={submitOwn} className="flex flex-wrap items-center gap-2">
        <input
          aria-label={`Any emoji for ${categoryName}`}
          placeholder="Or paste any emoji"
          value={own}
          onChange={(e) => {
            setOwn(e.target.value);
            setOwnError(false);
          }}
          className={`${inputClass} w-40`}
        />
        <button type="submit" className={`${btnSecondary} h-9 px-3 text-sm md:h-8`}>
          Use
        </button>
        {ownError ? (
          <span role="alert" className="text-xs text-danger">
            That isn&apos;t an emoji.
          </span>
        ) : null}
      </form>
    </div>
  );
}
