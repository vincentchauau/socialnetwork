import FieldLabel from "./FieldLabel";
import { INPUT } from "./ui";
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
      <FieldLabel htmlFor="password" text={label} hint="(thường + hoa + số + đặc biệt)" hintId="password-classes" />
      <input
        id="password"
        type="password"
        name="password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={INPUT}
        required
        autoComplete={isRegister ? "new-password" : "current-password"}
        placeholder={PASSWORD_EXAMPLE}
        aria-describedby={isRegister ? "password-classes password-hint" : "password-classes"}
      />
      {isRegister && <PasswordChecklist id="password-hint" password={value} />}
    </>
  );
}
