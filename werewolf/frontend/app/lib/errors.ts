import { ApiError } from "@sn/api";

/** Vietnamese text per HTTP status of the contract; the server's own `detail` (already Vietnamese) wins for 4xx rule errors. */
const STATUS_TEXT: Record<number, string> = {
  400: "Hành động không hợp lệ lúc này.",
  401: "Bạn cần đăng nhập lại.",
  403: "Bạn không có quyền làm việc này.",
  404: "Không tìm thấy phòng.",
  409: "Phòng không ở trạng thái phù hợp.",
  422: "Dữ liệu chưa hợp lệ, hãy kiểm tra lại.",
  429: "Bạn thao tác quá nhanh, hãy chờ một chút.",
  503: "Máy chủ đang đầy phòng, thử lại sau.",
};

const ORIGIN_TEXT = "Nguồn truy cập không được phép.";
const NETWORK_TEXT = "Không kết nối được máy chủ. Hãy thử lại.";
const GENERIC_TEXT = "Có lỗi xảy ra.";
/** Statuses whose generic wording is always preferred over the raw detail. */
const FIXED_STATUSES = new Set([401, 429, 503]);

function hasDetail(body: unknown): boolean {
  return typeof (body as { detail?: unknown } | undefined)?.detail === "string";
}

/** Maps any thrown value to a Vietnamese message for a toast. */
export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (FIXED_STATUSES.has(error.status)) return STATUS_TEXT[error.status];
    if (error.status === 403 && error.message === "Origin not allowed") return ORIGIN_TEXT;
    // 422 detail may be a validation reason in Vietnamese (setup) or a list (body): only a string is shown.
    if (hasDetail(error.body)) return error.message;
    return STATUS_TEXT[error.status] ?? GENERIC_TEXT;
  }
  if (error instanceof TypeError) return NETWORK_TEXT;
  return GENERIC_TEXT;
}

/** Text of a websocket `error` frame: the server message, already Vietnamese. */
export function frameErrorText(message: string): string {
  if (message === "Invalid message") return "Tin nhắn không hợp lệ.";
  return message || GENERIC_TEXT;
}
