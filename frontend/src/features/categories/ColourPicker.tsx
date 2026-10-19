import { useEffect, useRef, useState } from 'react';
import { colourLabel } from './colourLabel';
import { CATEGORY_KEYS, CATEGORY_PALETTE, isCategoryKey } from '../../styles/palette';
import { catProps, isHex } from '../../styles/customColour';

const CUSTOM_DELAY_MS = 350;

interface ColourPickerProps {
  /** A palette key, or (with `custom`) a `#rrggbb` colour. */
  value: string;
  onChange(colour: string): void;
  /** Accessible name of the group, e.g. "Colour for Work". */
  label: string;
  /** Also offer the browser's colour picker, for any colour (categories; holidays are palette-only). */
  custom?: boolean;
}

/** The colour the native picker starts from: the stored hex, or the palette colour's tone. */
const startingHex = (value: string) =>
  isHex(value)
    ? value.toLowerCase()
    : isCategoryKey(value)
      ? CATEGORY_PALETTE[value].light.text
      : '#2f6fdf';

/**
 * The palette colours as a radio group (each swatch is labelled with its colour name), and with
 * `custom` a native colour input for any other colour. Dragging in the native picker fires many
 * changes, so the choice is sent once it has settled.
 */
export function ColourPicker({ value, onChange, label, custom = false }: ColourPickerProps) {
  const customSelected = isHex(value);
  const [draft, setDraft] = useState(() => startingHex(value));
  const sent = useRef(value);
  const send = useRef(onChange);
  useEffect(() => {
    send.current = onChange;
  });

  // Follow the stored colour when it changes elsewhere (another device, a palette pick).
  const [seen, setSeen] = useState(value);
  if (seen !== value) {
    setSeen(value);
    setDraft(startingHex(value));
  }
  useEffect(() => {
    sent.current = value;
  }, [value]);

  useEffect(() => {
    if (!custom || draft === sent.current || (!customSelected && draft === startingHex(value))) {
      return;
    }
    const timer = setTimeout(() => {
      sent.current = draft;
      send.current(draft);
    }, CUSTOM_DELAY_MS);
    return () => clearTimeout(timer);
  }, [custom, customSelected, draft, value]);

  return (
    <div role="radiogroup" aria-label={label} className="flex max-w-[21rem] flex-wrap gap-1.5">
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
      {custom ? (
        <label
          title="Custom colour"
          className={`cat-swatch relative inline-flex size-7 cursor-pointer items-center justify-center overflow-hidden rounded-md md:size-6 ${
            customSelected ? 'ring-2 ring-accent ring-offset-1 ring-offset-surface' : ''
          }`}
          {...(customSelected ? catProps(draft) : { style: { background: 'var(--surface)' } })}
        >
          <span aria-hidden="true" className="pointer-events-none text-xs leading-none">
            {customSelected ? '' : '+'}
          </span>
          <input
            type="color"
            aria-label="Custom colour"
            value={draft}
            onChange={(e) => setDraft(e.target.value.toLowerCase())}
            className="absolute inset-0 size-full cursor-pointer opacity-0"
          />
        </label>
      ) : null}
    </div>
  );
}
