"use client";

import { ChangeEvent, CSSProperties, InputHTMLAttributes, ReactNode, useId } from "react";
import TextBox from "../elements/TextBox";
import Button from "../elements/Button";

export interface LabelTextBoxProps {
  label: string;
  name: string;
  value: string | number | null | undefined;
  onChange?: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => void;
  type?: "text" | "textarea";
  rows?: number;
  required?: boolean;
  disabled?: boolean;
  readOnly?: boolean;
  minWidth?: string;
  placeholder?: string;
  /** The `type` of a single-line input (`password` masks it). */
  inputType?: string;
  /** Tooltip of the label (e.g. the raw column name). */
  title?: string;
  /** Shown after the label, outside it (a lock, a caption). */
  adornment?: ReactNode;
  /** Font size of the label in px; default 12. */
  labelSize?: number;
  /** Extra style of the input. */
  fieldStyle?: CSSProperties;
  /** Extra attributes of a single-line input (combobox roles, key handlers). */
  inputProps?: InputHTMLAttributes<HTMLInputElement>;
  /** Drawn right below the single-line input, inside a positioned box (a suggestion list). */
  afterInput?: ReactNode;
  /** The id of the input; generated when omitted. */
  id?: string;
}

/** Labelled text input or textarea. The label is tied to the field, so it is clickable and read by screen readers. */
export function LabelTextBox({
  label,
  name,
  value,
  onChange,
  type = "text",
  rows = 2,
  required = false,
  disabled = false,
  readOnly = false,
  minWidth = "120px",
  placeholder,
  inputType,
  title,
  adornment,
  labelSize = 12,
  fieldStyle,
  inputProps,
  afterInput,
  id: givenId,
}: LabelTextBoxProps) {
  const generated = useId();
  const id = givenId ?? generated;
  const common = { id, name, value: String(value ?? ""), disabled, readOnly, required, placeholder, style: { width: "100%", ...fieldStyle } };

  return (
    <div style={{ flex: 1, minWidth }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
        <label htmlFor={id} title={title} style={{ fontSize: labelSize, fontWeight: 600 }}>
          {label}
        </label>
        {adornment}
      </div>
      {type === "textarea" ? (
        <TextBox {...common} multiline rows={rows} onChange={onChange} />
      ) : (
        <div style={{ position: "relative" }}>
          <TextBox {...inputProps} {...common} type={inputType} onChange={onChange} />
          {afterInput}
        </div>
      )}
    </div>
  );
}

export default LabelTextBox;

export interface NumberBoxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "onChange" | "value" | "min" | "max" | "step"> {
  value?: number;
  onChange?: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  /** Show the ▲▼ buttons (the browser's own spinner is hidden when they are shown). */
  controls?: boolean;
  incrementLabel?: string;
  decrementLabel?: string;
}

function clamp(value: number, min?: number, max?: number): number {
  const lower = min === undefined ? value : Math.max(min, value);
  return max === undefined ? lower : Math.min(max, lower);
}

export function NumberBox({
  value,
  onChange,
  min,
  max,
  step = 1,
  controls = true,
  incrementLabel = "Increase",
  decrementLabel = "Decrease",
  style,
  className,
  ...rest
}: NumberBoxProps) {
  const bump = (direction: 1 | -1) => onChange?.(clamp((value ?? 0) + direction * step, min, max));

  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <TextBox
        {...rest}
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange?.(Number(event.target.value))}
        className={controls ? `${className ?? ""} sn-numberbox-no-spin`.trim() : className}
        style={{ width: 100, padding: "6px 8px", ...style }}
      />
      {controls && (
        <>
          <style>{`
            .sn-numberbox-no-spin::-webkit-outer-spin-button,
            .sn-numberbox-no-spin::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
            .sn-numberbox-no-spin { -moz-appearance: textfield; }
          `}</style>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <Button type="button" variant="secondary" aria-label={incrementLabel} style={{ padding: "0 6px" }} onClick={() => bump(1)}>
              ▲
            </Button>
            <Button type="button" variant="secondary" aria-label={decrementLabel} style={{ padding: "0 6px" }} onClick={() => bump(-1)}>
              ▼
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

