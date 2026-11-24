import { ApiError } from "@sn/api";
import { tr } from "../i18n";

/** Vietnamese message for a failed getUserMedia / camera start. */
export function cameraErrorMessage(error: unknown): string {
  const name = error instanceof Error || (typeof error === "object" && error !== null && "name" in error)
    ? String((error as { name: unknown }).name)
    : "";
  switch (name) {
    case "NotAllowedError":
    case "SecurityError":
      return tr("ban_da_tu_choi_quyen_dung");
    case "NotFoundError":
    case "OverconstrainedError":
      return tr("khong_tim_thay_camera_tren_thiet");
    case "NotReadableError":
    case "AbortError":
      return tr("camera_dang_duoc_ung_dung_khac");
    case "UnsupportedError":
      return tr("trinh_duyet_nay_khong_ho_tro");
    case "WebglUnavailableError":
      return tr("trinh_duyet_nay_khong_bat_duoc");
    case "ModelLoadError":
      return tr("khong_tai_duoc_mo_hinh_nhan");
    default:
      return tr("khong_the_bat_camera_hay_thu");
  }
}

/** Vietnamese message for a failed backend call. */
export function apiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.status) {
      case 401:
        return tr("phien_dang_nhap_da_het_han");
      case 403:
        return tr("yeu_cau_bi_tu_choi_nguon");
      case 404:
        return tr("khong_tim_thay_ban_ghi_co");
      case 422:
        return tr("du_lieu_khong_hop_le_khong");
      case 429:
        return tr("ban_thao_tac_qua_nhanh_hay");
      default:
        if (error.status >= 500) return tr("may_chu_dang_gap_su_co");
    }
  }
  return tr("khong_ket_noi_duoc_may_chu");
}
