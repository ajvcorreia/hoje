import { describe, expect, it } from 'vitest';
import { todoMarkerStyle } from './todoMarker';

describe('todoMarkerStyle', () => {
  it('leaves the theme colour alone for auto', () => {
    expect(todoMarkerStyle('auto')).toEqual({});
  });

  it('sets the picked colour with readable badge text', () => {
    expect(todoMarkerStyle('#1d4ed8')).toEqual({ '--todo': '#1d4ed8', '--todo-text': '#ffffff' });
    expect(todoMarkerStyle('#fde047')).toEqual({ '--todo': '#fde047', '--todo-text': '#000000' });
  });
});
