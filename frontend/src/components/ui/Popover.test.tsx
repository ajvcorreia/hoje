import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Popover } from './Popover';

let resized: (() => void) | null = null;
let height = 100;

beforeEach(() => {
  resized = null;
  height = 100;
  vi.stubGlobal(
    'ResizeObserver',
    class {
      constructor(callback: () => void) {
        resized = callback;
      }
      observe() {}
      disconnect() {}
    },
  );
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockImplementation(() => height);
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockImplementation(() => 200);
  vi.stubGlobal('innerHeight', 600);
  vi.stubGlobal('innerWidth', 1000);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function anchorAt(top: number): HTMLElement {
  const anchor = document.createElement('button');
  document.body.append(anchor);
  anchor.getBoundingClientRect = () =>
    ({ top, bottom: top + 20, left: 100, right: 120, width: 20, height: 20 }) as DOMRect;
  return anchor;
}

describe('Popover', () => {
  it('moves up as its content grows, so the bottom stays on screen', () => {
    render(
      <Popover anchor={anchorAt(400)} label="Day" onClose={() => undefined}>
        <p>content</p>
      </Popover>,
    );
    const panel = screen.getByRole('dialog');
    expect(panel.style.top).toBe('400px'); // 400 + 100 fits above 600 - 8

    height = 300; // a to-do was added
    act(() => resized?.());
    expect(panel.style.top).toBe(`${600 - 300 - 8}px`);

    height = 120; // and removed again: back beside the anchor
    act(() => resized?.());
    expect(panel.style.top).toBe('400px');
  });

  it('never goes above the top margin, and scrolls inside instead', () => {
    height = 900;
    render(
      <Popover anchor={anchorAt(400)} label="Day" onClose={() => undefined}>
        <p>content</p>
      </Popover>,
    );
    const panel = screen.getByRole('dialog');
    expect(panel.style.top).toBe('8px');
    expect(panel.className).toContain('overflow-y-auto');
    expect(panel.className).toContain('max-h-[calc(100dvh-1rem)]');
  });
});
