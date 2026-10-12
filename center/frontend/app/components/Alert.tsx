/** Live region that is always mounted so screen readers announce the text when it appears. */
export default function Alert({ text, ok = false }: { text: string | null; ok?: boolean }) {
  return (
    <div
      role={ok ? "status" : "alert"}
      aria-live={ok ? "polite" : "assertive"}
      className={`mt-2 text-sm font-semibold ${ok ? "text-green-700" : "text-red-600"}`}
      hidden={!text}
    >
      {text}
    </div>
  );
}
