import { useState, type FormEvent } from 'react';
import type { Category } from '../../api/types';
import { btnDanger, btnPrimary, btnSecondary, inputClass } from '../../components/ui/classes';
import { Dialog } from '../../components/ui/Dialog';
import { FormError } from '../../components/ui/FormError';
import { describeError } from '../../lib/errors';
import { CATEGORY_KEYS } from '../../styles/palette';
import {
  useCategories,
  useCreateCategory,
  useDeleteCategory,
  useReorderCategories,
  useUpdateCategory,
} from '../categories/api';
import { ColourPicker } from '../categories/ColourPicker';
import { SettingsSection } from './SettingsSection';

/** Settings › Categories: rename, recolour, vacation and hide toggles, reorder, add, delete. */
export function CategoriesSection() {
  const { data: categories, isPending, isError, error } = useCategories();
  const reorder = useReorderCategories();
  const [deleting, setDeleting] = useState<Category | null>(null);

  if (isPending) {
    return (
      <SettingsSection title="Categories">
        <p className="text-sm text-text-muted">Loading...</p>
      </SettingsSection>
    );
  }
  if (isError) {
    return (
      <SettingsSection title="Categories">
        <FormError message={describeError(error)} />
      </SettingsSection>
    );
  }

  const move = (index: number, delta: -1 | 1) => {
    const ids = categories.map((c) => c.id);
    const target = index + delta;
    const a = ids[index];
    const b = ids[target];
    if (a === undefined || b === undefined) return;
    ids[index] = b;
    ids[target] = a;
    reorder.mutate(ids);
  };

  return (
    <SettingsSection title="Categories">
      <ul className="space-y-3">
        {categories.map((category, index) => (
          <CategoryRow
            key={category.id}
            category={category}
            canMoveUp={index > 0}
            canMoveDown={index < categories.length - 1}
            onMove={(delta) => move(index, delta)}
            onDelete={() => setDeleting(category)}
          />
        ))}
      </ul>
      <AddCategory categories={categories} />
      {deleting ? (
        <DeleteCategoryDialog
          category={deleting}
          others={categories.filter((c) => c.id !== deleting.id)}
          onClose={() => setDeleting(null)}
        />
      ) : null}
    </SettingsSection>
  );
}

interface CategoryRowProps {
  category: Category;
  canMoveUp: boolean;
  canMoveDown: boolean;
  onMove(delta: -1 | 1): void;
  onDelete(): void;
}

function CategoryRow({ category, canMoveUp, canMoveDown, onMove, onDelete }: CategoryRowProps) {
  const update = useUpdateCategory();
  const [name, setName] = useState(category.name);
  const [pickerOpen, setPickerOpen] = useState(false);

  const commitName = () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setName(category.name);
      return;
    }
    if (trimmed !== category.name) update.mutate({ category, patch: { name: trimmed } });
  };

  return (
    <li className="space-y-2 rounded-md border border-border p-3">
      <div className="flex items-center gap-2">
        <button
          type="button"
          data-cat={category.colour}
          aria-label={`Colour of ${category.name}: ${category.colour}`}
          aria-expanded={pickerOpen}
          onClick={() => setPickerOpen((open) => !open)}
          className="cat-swatch size-9 shrink-0 rounded-md md:size-8"
        />
        <input
          aria-label={`Name of ${category.name}`}
          value={name}
          maxLength={40}
          onChange={(e) => setName(e.target.value)}
          onBlur={commitName}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              commitName();
            }
          }}
          className={inputClass}
        />
        <div className="flex shrink-0">
          <button
            type="button"
            className={`${btnSecondary} px-2`}
            disabled={!canMoveUp}
            aria-label={`Move ${category.name} up`}
            onClick={() => onMove(-1)}
          >
            {'↑'}
          </button>
          <button
            type="button"
            className={`${btnSecondary} ml-1 px-2`}
            disabled={!canMoveDown}
            aria-label={`Move ${category.name} down`}
            onClick={() => onMove(1)}
          >
            {'↓'}
          </button>
        </div>
      </div>
      {pickerOpen ? (
        <ColourPicker
          label={`Colour for ${category.name}`}
          value={category.colour}
          onChange={(colour) => update.mutate({ category, patch: { colour } })}
        />
      ) : null}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <label className="flex min-h-9 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={category.is_leave}
            onChange={(e) => update.mutate({ category, patch: { is_leave: e.target.checked } })}
            className="size-4"
          />
          Counts as vacation
          <span className="sr-only"> for {category.name}</span>
        </label>
        <label className="flex min-h-9 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={category.hidden}
            onChange={(e) => update.mutate({ category, patch: { hidden: e.target.checked } })}
            className="size-4"
          />
          Hidden
          <span className="sr-only"> for {category.name}</span>
        </label>
        <button
          type="button"
          className="ml-auto min-h-9 text-sm text-danger hover:underline"
          onClick={onDelete}
          aria-label={`Delete ${category.name}`}
        >
          Delete
        </button>
      </div>
      {update.isError ? <FormError message={describeError(update.error)} /> : null}
    </li>
  );
}

function AddCategory({ categories }: { categories: Category[] }) {
  const create = useCreateCategory();
  const firstUnused =
    CATEGORY_KEYS.find((key) => !categories.some((c) => c.colour === key)) ?? CATEGORY_KEYS[0];
  const [name, setName] = useState('');
  const [colour, setColour] = useState<Category['colour'] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setError(null);
    create.mutate(
      { name: trimmed, colour: colour ?? firstUnused },
      {
        onSuccess: () => {
          setName('');
          setColour(null);
        },
        onError: (e) =>
          setError(describeError(e, { 409: 'A category with that name already exists.' })),
      },
    );
  };

  return (
    <form onSubmit={submit} className="space-y-2 border-t border-border pt-3">
      <div className="flex items-center gap-2">
        <label htmlFor="new-category" className="sr-only">
          New category name
        </label>
        <input
          id="new-category"
          value={name}
          maxLength={40}
          placeholder="New category"
          autoComplete="off"
          onChange={(e) => setName(e.target.value)}
          className={inputClass}
        />
        <button type="submit" className={btnPrimary} disabled={create.isPending}>
          Add
        </button>
      </div>
      <ColourPicker
        label="Colour for the new category"
        value={colour ?? firstUnused}
        onChange={setColour}
      />
      <FormError message={error} />
    </form>
  );
}

function DeleteCategoryDialog({
  category,
  others,
  onClose,
}: {
  category: Category;
  others: Category[];
  onClose(): void;
}) {
  const remove = useDeleteCategory();
  const [target, setTarget] = useState(others[0]?.id ?? '');
  const [error, setError] = useState<string | null>(null);

  if (others.length === 0) {
    return (
      <Dialog title="Delete category" onClose={onClose}>
        <p className="text-sm">
          You need at least one category, so {category.name} cannot be deleted.
        </p>
        <div className="mt-4">
          <button type="button" className={btnSecondary} onClick={onClose}>
            Close
          </button>
        </div>
      </Dialog>
    );
  }

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    remove.mutate(
      { id: category.id, reassignTo: target },
      { onSuccess: onClose, onError: (e) => setError(describeError(e)) },
    );
  };

  return (
    <Dialog title={`Delete ${category.name}?`} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <div className="space-y-1">
          <label htmlFor="reassign-to" className="block text-sm font-medium">
            Move its events to
          </label>
          <select
            id="reassign-to"
            data-autofocus
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            className={inputClass}
          >
            {others.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        <FormError message={error} />
        <div className="flex gap-2">
          <button type="submit" className={btnDanger} disabled={remove.isPending}>
            Delete category
          </button>
          <button type="button" className={btnSecondary} onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Dialog>
  );
}
