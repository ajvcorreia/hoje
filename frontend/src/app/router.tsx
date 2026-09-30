import { createBrowserRouter, type RouteObject } from 'react-router';
import { CalendarPage } from '../features/calendar/CalendarPage';
import { SettingsPage } from '../features/settings/SettingsPage';
import { AppShell } from './AppShell';

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <CalendarPage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
];

export const createRouter = () => createBrowserRouter(routes);
