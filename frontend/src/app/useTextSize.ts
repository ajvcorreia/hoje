import { useCallback, useState } from 'react';
import { applyTextSize, readStoredTextSize, storeTextSize, type TextSize } from '../lib/textSize';

export function useTextSize(): [TextSize, (size: TextSize) => void] {
  const [size, setSizeState] = useState<TextSize>(readStoredTextSize);
  const setSize = useCallback((next: TextSize) => {
    setSizeState(next);
    storeTextSize(next);
    applyTextSize(next);
  }, []);
  return [size, setSize];
}
