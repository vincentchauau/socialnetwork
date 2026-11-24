import type { HTMLAttributes } from "react";

export type AlertTone = "error" | "success" | "info";

export interface AlertProps extends Omit<HTMLAttributes<HTMLDivElement>, "role"> {
  tone?: AlertTone;
}

const TONE_COLOR: Record<AlertTone, string> = {
  error: "var(--line)",
  success: "var(--line, inherit)",
  info: "inherit",
};

/**
 * A message announced to screen readers: errors with role="alert" (assertive), the other tones with
 * role="status" (polite). It is always rendered, so the announcement happens when text appears in it;
 * with nothing to show it stays in the page but hidden.
 */
export function Alert({ tone = "error", children, style, ...rest }: AlertProps) {
  const isError = tone === "error";
  const empty = children === null || children === undefined || children === false || children === "";
  return (
    <div
      {...rest}
      role={isError ? "alert" : "status"}
      aria-live={isError ? "assertive" : "polite"}
      hidden={empty}
      style={{ margin: 0, fontSize: 14, fontWeight: 600, color: TONE_COLOR[tone], ...style }}
    >
      {children}
    </div>
  );
}

export default Alert;
