import { RefObject } from "react";

import FieldLabel from "./FieldLabel";
import { INPUT } from "./ui";

const USERNAME_HINT = "(thường + hoa + số)";
const USERNAME_EXAMPLE = "Username123";

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
      <FieldLabel htmlFor="username" text={required ? "Tên đăng nhập" : "Tên đăng nhập (không bắt buộc)"} hint={USERNAME_HINT} hintId="username-classes" />
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
        aria-describedby={optionalHint ? "username-hint username-classes" : "username-classes"}
        placeholder={USERNAME_EXAMPLE}
      />
      {optionalHint && (
        <p id="username-hint" className="text-xs text-gray-600 mb-2">
          {optionalHint}
        </p>
      )}
    </>
  );
}
