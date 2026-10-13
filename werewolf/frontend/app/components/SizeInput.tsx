import { useEffect, useRef, useState } from "react";

import { clampCount } from "../lib/setup";

interface Props {
  id: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}

/** Whole-number input: applies a valid number while typing, snaps into [min, max] when you leave the field. */
export default function SizeInput({ id, value, min, max, onChange }: Props) {
  const [text, setText] = useState(String(value));
  const focused = useRef(false);
  // An answer that arrives while you are still typing must not overwrite what you typed.
  useEffect(() => {
    if (!focused.current) setText(String(value));
  }, [value]);

  return (
    <input
      id={id}
      className="ww-size"
      value={text}
      inputMode="numeric"
      maxLength={2}
      onFocus={(event) => {
        focused.current = true;
        event.currentTarget.select();
      }}
      onChange={(event) => {
        const digits = event.target.value.replace(/\D/g, "").slice(0, 2);
        setText(digits);
        const n = parseInt(digits, 10);
        if (n >= min && n <= max) onChange(n);
      }}
      onBlur={() => {
        focused.current = false;
        const n = parseInt(text, 10);
        const fixed = Number.isFinite(n) ? clampCount({ minPlayers: min, maxPlayers: max }, n) : value;
        setText(String(fixed));
        if (fixed !== value) onChange(fixed);
      }}
    />
  );
}
