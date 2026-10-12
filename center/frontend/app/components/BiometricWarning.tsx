export default function BiometricWarning() {
  return (
    <p role="note" className="text-sm text-amber-800 bg-amber-50 border border-amber-300 rounded p-2 mb-2">
      Lưu ý an toàn: ứng dụng chưa có kiểm tra người thật. Ai có bản ghi âm giọng và ảnh/video khuôn mặt của bạn có thể
      vượt qua. Chỉ bật nếu bạn chấp nhận rủi ro này.
    </p>
  );
}
