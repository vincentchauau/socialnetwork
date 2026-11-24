import { tr } from "../i18n";
type WarningKind = "voice" | "webcam";

const SUBJECT: Record<WarningKind, { what: string; proof: string }> = {
  voice: { get what() { return tr("giong_noi_2"); }, get proof() { return tr("ban_ghi_am_giong"); } },
  webcam: { what: "webcam", get proof() { return tr("anh_video_khuon_mat"); } },
};

/** Cảnh báo trung thực: chưa có kiểm tra người thật. Chỉ nhắc đến cách đang dùng. */
export default function BiometricWarning({ kinds }: { kinds: WarningKind[] }) {
  const what = kinds.map((k) => SUBJECT[k].what).join(tr("va"));
  const proof = kinds.map((k) => SUBJECT[k].proof).join(tr("hoac"));
  return (
    <p role="note" className="text-sm text-line bg-solid border border-line rounded p-2 mb-2">
      {tr("luu_y_an_toan")} {what} {tr("chua_co_kiem_tra_nguoi_that")} {proof} {tr("cua_ban_co_the_vuot_qua")}
    </p>
  );
}
