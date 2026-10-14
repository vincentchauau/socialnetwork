import { ApiError } from "@sn/api";

const BY_STATUS: Record<number, string> = {
  401: "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.",
  403: "Bạn không có quyền thực hiện thao tác này.",
  404: "Không tìm thấy mục yêu cầu.",
  409: "Tên này đã tồn tại. Hãy chọn tên khác.",
  413: "Tệp quá lớn hoặc vượt dung lượng cho phép.",
  422: "Dữ liệu không hợp lệ. Hãy kiểm tra lại.",
  429: "Bạn thao tác quá nhanh. Hãy thử lại sau ít phút.",
};

/** Vietnamese message for a failed call: the server's `detail` when it sent one, else a per-status text. */
export function errorText(error: unknown, fallback = "Đã xảy ra lỗi. Hãy thử lại."): string {
  if (!(error instanceof ApiError)) return fallback;
  const detail = (error.body as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string" && detail) return detail;
  return BY_STATUS[error.status] ?? fallback;
}
