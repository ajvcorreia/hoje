/** Inline form-level error; always in the DOM so screen readers announce changes. */
export function FormError({ message }: { message: string | null | undefined }) {
  return (
    <div role="alert" className="text-sm text-danger">
      {message || null}
    </div>
  );
}
