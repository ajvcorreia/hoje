import type { Category } from '../../api/types';
import { CATEGORY_KEYS } from '../../styles/palette';

type Colour = Category['colour'];

/** "teal" -> "Teal": the accessible name of a palette swatch. */
export const colourLabel = (colour: string) => colour.charAt(0).toUpperCase() + colour.slice(1);

interface ColourPickerProps {
  value: Colour;
  onChange(colour: Colour): void;
  /** Accessible name of the group, e.g. "Colour for Work". */
  label: string;
}

/** The 12 palette colours as a radio group; each swatch is labelled with its colour name. */
export function ColourPicker({ value, onChange, label }: ColourPickerProps) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-1.5">
      {CATEGORY_KEYS.map((colour) => {
        const selected = colour === value;
        return (
          <button
            key={colour}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={colourLabel(colour)}
            title={colourLabel(colour)}
            data-cat={colour}
            onClick={() => onChange(colour)}
            className={`cat-swatch size-7 rounded-md md:size-6 ${
              selected ? 'ring-2 ring-accent ring-offset-1 ring-offset-surface' : ''
            }`}
          />
        );
      })}
    </div>
  );
}
