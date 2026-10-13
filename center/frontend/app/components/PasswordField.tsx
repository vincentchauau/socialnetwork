import { INPUT, LABEL } from "./ui";
import PasswordChecklist from "./PasswordChecklist";
import { PASSWORD_EXAMPLE } from "../lib/auth";

interface Props {
  value: string;
  onChange: (value: string) => void;
  isRegister: boolean;
  label?: string;
}

export default function PasswordField({ value, onChange, isRegister, label = "Mật khẩu" }: Props) {
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
        placeholder={isRegister ? `vd: ${PASSWORD_EXAMPLE}` : "Mật khẩu"}
        aria-describedby={isRegister ? "password-hint" : undefined}
      />
      {isRegister && <PasswordChecklist id="password-hint" password={value} />}
    </>
  );
}
