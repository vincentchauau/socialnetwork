import FieldLabel from "./FieldLabel";
import { INPUT } from "./ui";
import PasswordChecklist from "./PasswordChecklist";
import { PASSWORD_EXAMPLE } from "../lib/auth";
import { tr } from "../i18n";
import TextBox from "@sn/elements/TextBox";

interface Props {
  value: string;
  onChange: (value: string) => void;
  isRegister: boolean;
  label?: string;
}

export default function PasswordField({ value, onChange, isRegister, label = tr("mat_khau") }: Props) {
  return (
    <>
      <FieldLabel htmlFor="password" text={label} hint={tr("thuong_hoa_so_dac_biet")} hintId="password-classes" />
      <TextBox
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
