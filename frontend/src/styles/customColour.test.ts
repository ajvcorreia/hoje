import { describe, expect, it } from 'vitest';
import { catProps, customColour, isHex } from './customColour';
import { contrastRatio } from './palette';

const SAMPLES = [
  '#000000',
  '#ffffff',
  '#ffff00',
  '#ff0000',
  '#00ff00',
  '#0000ff',
  '#2f6fdf',
  '#d98a1c',
  '#1f9d6b',
  '#888888',
  '#12ab34',
  '#fe00fe',
];

describe('custom category colours', () => {
  it.each(SAMPLES)('%s: text reads on its fill in every theme', (hex) => {
    const tokens = customColour(hex);

    expect(contrastRatio(tokens.light.text, tokens.light.fill)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(tokens.dark.text, tokens.dark.fill)).toBeGreaterThanOrEqual(4.5);
    expect(
      contrastRatio(tokens['light-contrast'].text, tokens['light-contrast'].fill),
    ).toBeGreaterThanOrEqual(7);
  });

  it('keeps the hue: a red stays red-ish and the light fill is paler than the colour', () => {
    const { light, dark } = customColour('#ff0000');

    expect(light.fill).toMatch(/^#ff[0-9a-f]{2}[0-9a-f]{2}$/);
    expect(light.fill).not.toBe('#ff0000');
    expect(dark.fill).toMatch(/^#[0-9a-f]{2}0000$/);
  });

  it('recognises hex colours only', () => {
    expect(isHex('#a1B2c3')).toBe(true);
    expect(isHex('teal')).toBe(false);
    expect(isHex('#abc')).toBe(false);
    expect(isHex(undefined)).toBe(false);
  });

  it('a palette key stays a plain data-cat, a hex becomes custom tokens', () => {
    expect(catProps('teal')).toEqual({ 'data-cat': 'teal' });
    expect(catProps(undefined)).toEqual({});
    const custom = catProps('#12ab34');
    expect(custom['data-cat']).toBe('custom');
    expect(custom.style).toMatchObject({
      '--cc-light-fill': expect.stringMatching(/^#[0-9a-f]{6}$/),
      '--cc-dark-text': expect.stringMatching(/^#[0-9a-f]{6}$/),
      '--cc-contrast-text': expect.stringMatching(/^#[0-9a-f]{6}$/),
    });
  });
});
