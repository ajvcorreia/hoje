import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router/dom';
import { applyTheme, readStoredTheme } from './lib/theme';
import { applyTextSize, readStoredTextSize } from './lib/textSize';
import { createQueryClient } from './app/queryClient';
import { createRouter } from './app/router';
import './styles/index.css';

applyTheme(readStoredTheme());
applyTextSize(readStoredTextSize());

const queryClient = createQueryClient();
const router = createRouter();

const root = document.getElementById('root');
if (!root) throw new Error('Missing #root element');

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
