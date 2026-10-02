import { createBrowserRouter, type RouteObject } from 'react-router';
import { ForgotPage } from '../features/auth/ForgotPage';
import { LoginPage } from '../features/auth/LoginPage';
import { ResetPage } from '../features/auth/ResetPage';
import { SetupPage } from '../features/auth/SetupPage';
import { CalendarPage } from '../features/calendar/CalendarPage';
import { SettingsPage } from '../features/settings/SettingsPage';
import { AppShell } from './AppShell';
import { RequireAuth } from './RequireAuth';

export const routes: RouteObject[] = [
  { path: '/login', element: <LoginPage /> },
  { path: '/setup', element: <SetupPage /> },
  { path: '/forgot', element: <ForgotPage /> },
  { path: '/reset', element: <ResetPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        path: '/',
        element: <AppShell />,
        children: [
          { index: true, element: <CalendarPage /> },
          { path: 'settings', element: <SettingsPage /> },
        ],
      },
    ],
  },
];

export const createRouter = () => createBrowserRouter(routes);
