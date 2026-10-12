import { INPUT, LABEL } from "./ui";
import { MIN_PASSWORD } from "../lib/auth";

interface Props {
  value: string;
  onChange: (value: string) => void;
  isRegister: boolean;
  label?: string;
}

export default function PasswordField({ value, onChange, isRegister, label = "Mật khẩu" }: Props) {
  const longEnough = value.length >= MIN_PASSWORD;
  return (
    <>
      <label htmlFor="password" className={LABEL}>{label}</label>
      <input
        id="password"
        type="password"
        name="password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={INPUT}
        required
        autoComplete={isRegister ? "new-password" : "current-password"}
        placeholder="Ít nhất 8 ký tự"
        aria-describedby={isRegister ? "password-hint" : undefined}
      />
      {isRegister && (
        <p id="password-hint" aria-live="polite" className={`text-xs mb-2 ${longEnough ? "text-green-700" : "text-gray-600"}`}>
          {longEnough ? "Mật khẩu đủ dài." : `Cần ít nhất ${MIN_PASSWORD} ký tự (đã nhập ${value.length}).`}
        </p>
      )}
    </>
  );
}
