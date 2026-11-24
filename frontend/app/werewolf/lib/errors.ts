import { ApiError } from "@sn/api";
import { tr } from "../i18n";

/** Vietnamese text per HTTP status of the contract; the server's own `detail` (already Vietnamese) wins for 4xx rule errors. */
const STATUS_TEXT: Record<number, string> = {
  get 400() { return tr("hanh_dong_khong_hop_le_luc"); },
  get 401() { return tr("ban_can_dang_nhap_lai"); },
  get 403() { return tr("ban_khong_co_quyen_lam_viec"); },
  get 404() { return tr("khong_tim_thay_phong"); },
  get 409() { return tr("phong_khong_o_trang_thai_phu"); },
  get 422() { return tr("du_lieu_chua_hop_le_hay"); },
  get 429() { return tr("ww_ban_thao_tac_qua_nhanh"); },
  get 503() { return tr("may_chu_dang_day_phong_thu"); },
};

const ORIGIN_TEXT = tr("nguon_truy_cap_khong_duoc_phep");
const NETWORK_TEXT = tr("khong_ket_noi_duoc_may_chu");
const GENERIC_TEXT = tr("co_loi_xay_ra");
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
  if (message === "Invalid message") return tr("tin_nhan_khong_hop_le");
  return message || GENERIC_TEXT;
}
