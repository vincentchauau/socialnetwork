import type { InputHTMLAttributes, Ref, TextareaHTMLAttributes } from "react";

import { BG, BORDER, FG } from "../lib/theme";

// React 19 passes `ref` as a normal prop (the callers focus or measure the field through it).
type SingleLineProps = InputHTMLAttributes<HTMLInputElement> & { multiline?: false; rows?: never; ref?: Ref<HTMLInputElement> };
type MultiLineProps = TextareaHTMLAttributes<HTMLTextAreaElement> & { multiline: true; rows?: number; ref?: Ref<HTMLTextAreaElement> };

export type TextBoxProps = SingleLineProps | MultiLineProps;

const FIELD_STYLE = {
  padding: 8,
  borderRadius: 6,
  border: `1px solid ${BORDER}`,
  background: BG,
  color: FG,
  font: "inherit",
} as const;

/** One text field: an <input> by default, a <textarea> with `multiline`. */
export function TextBox(props: TextBoxProps) {
  if (props.multiline) {
    const { multiline: _multiline, rows = 3, style, ...rest } = props;
    return <textarea {...rest} rows={rows} style={{ ...FIELD_STYLE, ...style }} />;
  }
  const { multiline: _multiline, style, ...rest } = props;
  return <input {...rest} style={{ ...FIELD_STYLE, ...style }} />;
}

export default TextBox;
