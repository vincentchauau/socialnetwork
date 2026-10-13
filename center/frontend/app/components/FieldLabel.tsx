import { LABEL } from "./ui";

interface Props {
  htmlFor: string;
  text: string;
  /** Ghi chú ngắn cạnh nhãn, ví dụ "(thường + hoa + số + đặc biệt)". Không nằm trong nhãn để tên truy cập của ô giữ nguyên. */
  hint?: string;
  hintId?: string;
}

export default function FieldLabel({ htmlFor, text, hint, hintId }: Props) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-1 mb-1">
      <label htmlFor={htmlFor} className={`${LABEL} !mb-0`}>{text}</label>
      {hint && <span id={hintId} className="text-xs text-gray-600">{hint}</span>}
    </div>
  );
}
