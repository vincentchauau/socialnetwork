import type { ButtonHTMLAttributes, CSSProperties, MouseEvent, Ref } from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";
/** The hover effect, see lib/button.css. `invert` is the default for filled buttons, a light tint for the others. */
export type ButtonEffect = "invert" | "sweep" | "tone" | "draw" | "underline" | "slide" | "lift" | "hard" | "ripple";
/** A result shown by a one-time animation: shake for an error, bounce for a success. */
export type ButtonStatus = "error" | "success";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  effect?: ButtonEffect;
  status?: ButtonStatus;
  loading?: boolean;
  loadingLabel?: string;
  /** React 19 passes `ref` to function components as a normal prop; callers need it to manage focus. */
  ref?: Ref<HTMLButtonElement>;
}

// md is the default padding of the stylesheet, so a class may change it; only the other sizes set it here.
const PADDING: Partial<Record<ButtonSize, string>> = { sm: "4px 10px", lg: "10px 18px" };

// Fills come from --solid-1 onward (--solid-0 is the page); text and borders are the line color. `primary` is the
// stylesheet's default (lib/button.css), so a class on the button may restyle it (a selected tab, say).
const VARIANT_STYLE: Record<ButtonVariant, CSSProperties> = {
  primary: {},
  secondary: { background: "var(--solid-2)", color: "var(--line)", borderColor: "color-mix(in srgb, var(--line) 30%, transparent)" },
  ghost: { background: "transparent", color: "var(--line)", borderColor: "transparent" },
  danger: { background: "var(--solid-3)", color: "var(--line)", borderColor: "var(--line)" },
};

const RIPPLE_MS = 650;

/** Adds a circle at the pointer that grows and fades; it removes itself. */
function addRipple(event: MouseEvent<HTMLButtonElement>): void {
  const button = event.currentTarget;
  const box = button.getBoundingClientRect();
  const size = Math.max(box.width, box.height);
  const ripple = document.createElement("span");
  ripple.className = "sn-ripple";
  ripple.setAttribute("aria-hidden", "true");
  ripple.style.cssText = `width:${size}px;height:${size}px;left:${event.clientX - box.left - size / 2}px;top:${event.clientY - box.top - size / 2}px`;
  button.appendChild(ripple);
  window.setTimeout(() => ripple.remove(), RIPPLE_MS);
}

export function Button({
  variant = "primary",
  size = "md",
  effect,
  status,
  onClick,
  loading = false,
  loadingLabel = "Loading…",
  disabled,
  children,
  style,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      data-variant={variant}
      data-effect={effect}
      data-status={status}
      onClick={(event) => {
        if (effect === "ripple") addRipple(event);
        onClick?.(event);
      }}
      style={{ ...(PADDING[size] ? { padding: PADDING[size] } : {}), ...VARIANT_STYLE[variant], ...style }}
    >
      {loading ? loadingLabel : children}
    </button>
  );
}

export default Button;
