"use client";

import { type InputHTMLAttributes, type ReactNode, useEffect, useRef } from "react";

export interface CheckBoxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "onChange" | "type"> {
  checked?: boolean;
  /** The "some but not all" state; the browser only exposes it as a property, so it is set in an effect. */
  indeterminate?: boolean;
  onChange?: (checked: boolean) => void;
  label?: ReactNode;
}

export function CheckBox({ checked, indeterminate = false, onChange, label, ...rest }: CheckBoxProps) {
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);

  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      <input {...rest} ref={ref} type="checkbox" checked={checked} onChange={(event) => onChange?.(event.target.checked)} />
      {label ? <span>{label}</span> : null}
    </label>
  );
}

export default CheckBox;
