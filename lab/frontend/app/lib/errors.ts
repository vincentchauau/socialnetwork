import { ApiError } from "@sn/api";

/** Vietnamese message for a failed lab call. A 503 carries the backend's own explanation. */
export function apiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.status) {
      case 401:
        return "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.";
      case 403:
        return "Yêu cầu bị từ chối (nguồn truy cập không hợp lệ).";
      case 422:
        return "Dữ liệu không hợp lệ. Hãy kiểm tra lại các ô nhập.";
      case 429:
        return "Bạn thao tác quá nhanh. Hãy đợi một lát rồi thử lại.";
      case 503:
        return error.message;
      default:
        if (error.status >= 500) return "Máy chủ đang gặp sự cố. Hãy thử lại sau.";
    }
  }
  return "Không kết nối được máy chủ. Hãy thử lại.";
}
