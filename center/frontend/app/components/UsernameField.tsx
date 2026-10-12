import { RefObject } from "react";

import { INPUT, LABEL } from "./ui";

interface Props {
  value: string;
  onChange: (value: string) => void;
  inputRef?: RefObject<HTMLInputElement>;
  /** Mặc định bắt buộc; đặt false khi hệ thống có thể tự nhận/tạo tên. */
  required?: boolean;
  optionalHint?: string;
}

export default function UsernameField({ value, onChange, inputRef, required = true, optionalHint }: Props) {
  return (
    <>
      <label htmlFor="username" className={LABEL}>{required ? "Tên đăng nhập" : "Tên đăng nhập (không bắt buộc)"}</label>
      <input
        id="username"
        ref={inputRef}
        name="username"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={INPUT}
        required={required}
        aria-required={required}
        minLength={3}
        maxLength={32}
        autoComplete="username"
        aria-describedby="username-hint"
        placeholder="vd: nguyenvan"
      />
      <p id="username-hint" className="text-xs text-gray-600 mb-2">
        {optionalHint ? `${optionalHint} ` : ""}
        3-32 ký tự: chữ thường a-z, số, dấu chấm, gạch dưới, gạch ngang (không dùng @).
      </p>
    </>
  );
}
