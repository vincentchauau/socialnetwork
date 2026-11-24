import type { SelectHTMLAttributes } from "react";

import { BG, BORDER, FG } from "../lib/theme";

export type SelectProps = SelectHTMLAttributes<HTMLSelectElement>;

const FIELD_STYLE = {
  padding: "6px 8px",
  borderRadius: 6,
  border: `1px solid ${BORDER}`,
  background: BG,
  color: FG,
  font: "inherit",
} as const;

/** A native <select>, styled like the other fields. Pass the <option>s as children. */
export function Select({ style, children, ...rest }: SelectProps) {
  return (
    <select {...rest} style={{ ...FIELD_STYLE, ...style }}>
      {children}
    </select>
  );
}

export default Select;
