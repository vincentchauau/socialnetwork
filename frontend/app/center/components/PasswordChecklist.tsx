import { MIN_PASSWORD, PASSWORD_EXAMPLE, passwordChecks } from "../lib/auth";
import { tr } from "../i18n";

interface Props {
  id: string;
  password: string;
}

const ITEMS: { key: "lower" | "upper" | "digit" | "special"; label: string; example: string }[] = [
  { key: "lower", get label() { return tr("chu_thuong"); }, example: "a-z" },
  { key: "upper", get label() { return tr("chu_hoa"); }, example: "A-Z" },
  { key: "digit", get label() { return tr("chu_so"); }, example: "0-9" },
  { key: "special", get label() { return tr("ky_tu_dac_biet"); }, example: "! @ # $ % - _" },
];

/** Cần đủ 4 loại ký tự: hiện loại nào đã có (có dấu tích) và loại nào còn thiếu. */
export default function PasswordChecklist({ id, password }: Props) {
  const checks = passwordChecks(password);
  return (
    <div id={id} aria-live="polite" className="text-xs mb-2">
      <p className="text-line mb-1">
        {tr("can")} {MIN_PASSWORD} {tr("ky_tu_tro_len_va_du")} <span className="font-mono">{PASSWORD_EXAMPLE}</span>
      </p>
      <ul aria-label={tr("cac_loai_ky_tu_can_co")} className="grid grid-cols-2 gap-x-3">
        {ITEMS.map(({ key, label, example }) => (
          <li key={key} className={checks[key] ? "text-line" : "text-line"}>
            <span aria-hidden="true">{checks[key] ? "✓" : "○"} </span>
            {label} ({example}){checks[key] ? tr("da_co") : tr("chua_co_2")}
          </li>
        ))}
        <li className={checks.length ? "text-line" : "text-line"}>
          <span aria-hidden="true">{checks.length ? "✓" : "○"} </span>
          {tr("tu")} {MIN_PASSWORD} {tr("ky_tu")}{checks.length ? tr("du_dai") : tr("moi_p0", { p0: password.length })}
        </li>
      </ul>
    </div>
  );
}
