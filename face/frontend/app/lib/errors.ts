import { ApiError } from "@sn/api";

/** Vietnamese message for a failed getUserMedia / camera start. */
export function cameraErrorMessage(error: unknown): string {
  const name = error instanceof Error || (typeof error === "object" && error !== null && "name" in error)
    ? String((error as { name: unknown }).name)
    : "";
  switch (name) {
    case "NotAllowedError":
    case "SecurityError":
      return "Bạn đã từ chối quyền dùng camera. Hãy cho phép camera trong cài đặt trình duyệt rồi thử lại.";
    case "NotFoundError":
    case "OverconstrainedError":
      return "Không tìm thấy camera trên thiết bị này.";
    case "NotReadableError":
    case "AbortError":
      return "Camera đang được ứng dụng khác sử dụng hoặc không thể mở.";
    case "UnsupportedError":
      return "Trình duyệt này không hỗ trợ camera. Hãy dùng trình duyệt mới hơn và kết nối HTTPS.";
    case "WebglUnavailableError":
      return "Trình duyệt này không bật được WebGL (thường gặp trong trình duyệt tích hợp của VS Code hoặc khi tắt tăng tốc phần cứng). Hãy mở trang bằng Chrome hoặc Edge bên ngoài VS Code và bật tăng tốc phần cứng.";
    case "ModelLoadError":
      return "Không tải được mô hình nhận diện khuôn mặt. Hãy tải lại trang và thử lại.";
    default:
      return "Không thể bật camera. Hãy thử lại.";
  }
}

/** Vietnamese message for a failed backend call. */
export function apiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.status) {
      case 401:
        return "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.";
      case 403:
        return "Yêu cầu bị từ chối (nguồn truy cập không hợp lệ).";
      case 404:
        return "Không tìm thấy bản ghi (có thể đã bị xoá).";
      case 422:
        return "Dữ liệu không hợp lệ, không thể lưu.";
      case 429:
        return "Bạn thao tác quá nhanh. Hãy đợi một lát rồi thử lại.";
      default:
        if (error.status >= 500) return "Máy chủ đang gặp sự cố. Hãy thử lại sau.";
    }
  }
  return "Không kết nối được máy chủ. Hãy thử lại.";
}
