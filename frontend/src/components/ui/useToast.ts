import { useContext } from 'react';
import { ToastContext, type ToastApi } from './toastContext';

/** Access the toast queue. Must be used under `<ToastProvider>` (the app shell provides it). */
export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error('useToast must be used inside <ToastProvider>');
  return api;
}
