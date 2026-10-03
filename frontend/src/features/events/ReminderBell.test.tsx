import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ReminderBell } from './ReminderBell';

describe('ReminderBell', () => {
  it('is labelled "Has reminder" when the event has reminders', () => {
    render(<ReminderBell event={{ reminders: [{ offset_minutes: 1440 }] }} />);
    expect(screen.getByRole('img', { name: 'Has reminder' })).toBeInTheDocument();
  });

  it('renders nothing without reminders', () => {
    const { container } = render(<ReminderBell event={{ reminders: [] }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
