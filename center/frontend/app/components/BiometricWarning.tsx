export type WarningKind = "voice" | "webcam";

const SUBJECT: Record<WarningKind, { what: string; proof: string }> = {
  voice: { what: "giọng nói", proof: "bản ghi âm giọng" },
  webcam: { what: "webcam", proof: "ảnh/video khuôn mặt" },
};

/** Cảnh báo trung thực: chưa có kiểm tra người thật. Chỉ nhắc đến cách đang dùng. */
export default function BiometricWarning({ kinds }: { kinds: WarningKind[] }) {
  const what = kinds.map((k) => SUBJECT[k].what).join(" và ");
  const proof = kinds.map((k) => SUBJECT[k].proof).join(" hoặc ");
  return (
    <p role="note" className="text-sm text-amber-800 bg-amber-50 border border-amber-300 rounded p-2 mb-2">
      Lưu ý an toàn: {what} chưa có kiểm tra người thật. Ai có {proof} của bạn có thể vượt qua. Chỉ dùng nếu bạn chấp
      nhận rủi ro này.
    </p>
  );
}
