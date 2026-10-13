interface Props {
  htmlFor: string;
  text: string;
  /** Short note next to the label; kept out of the label so the field's accessible name stays stable. */
  hint?: string;
  hintId?: string;
}

export default function FieldLabel({ htmlFor, text, hint, hintId }: Props) {
  return (
    <div className="ww-field-label">
      <label htmlFor={htmlFor}>{text}</label>
      {hint && (
        <span id={hintId} className="muted">
          {hint}
        </span>
      )}
    </div>
  );
}
