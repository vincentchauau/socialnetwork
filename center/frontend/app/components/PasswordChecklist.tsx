import { MIN_PASSWORD, PASSWORD_EXAMPLE, passwordChecks } from "../lib/auth";

interface Props {
  id: string;
  password: string;
}

const ITEMS: { key: "lower" | "upper" | "digit" | "special"; label: string; example: string }[] = [
  { key: "lower", label: "Chữ thường", example: "a-z" },
  { key: "upper", label: "Chữ hoa", example: "A-Z" },
  { key: "digit", label: "Chữ số", example: "0-9" },
  { key: "special", label: "Ký tự đặc biệt", example: "! @ # $ % - _" },
];

/** Cần đủ 4 loại ký tự: hiện loại nào đã có (có dấu tích) và loại nào còn thiếu. */
export default function PasswordChecklist({ id, password }: Props) {
  const checks = passwordChecks(password);
  return (
    <div id={id} aria-live="polite" className="text-xs mb-2">
      <p className="text-gray-600 mb-1">
        Cần {MIN_PASSWORD} ký tự trở lên và đủ 4 loại ký tự, ví dụ <span className="font-mono">{PASSWORD_EXAMPLE}</span>
      </p>
      <ul aria-label="Các loại ký tự cần có" className="grid grid-cols-2 gap-x-3">
        {ITEMS.map(({ key, label, example }) => (
          <li key={key} className={checks[key] ? "text-green-700" : "text-gray-600"}>
            <span aria-hidden="true">{checks[key] ? "✓" : "○"} </span>
            {label} ({example}){checks[key] ? ": đã có" : ": chưa có"}
          </li>
        ))}
        <li className={checks.length ? "text-green-700" : "text-gray-600"}>
          <span aria-hidden="true">{checks.length ? "✓" : "○"} </span>
          Từ {MIN_PASSWORD} ký tự{checks.length ? ": đủ dài" : `: mới ${password.length}`}
        </li>
      </ul>
    </div>
  );
}
