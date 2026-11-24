import { SECTION } from "./ui";
import { tr } from "../i18n";
import Link from "next/link";

/** Đăng nhập bằng mã QR: không có gì để cấu hình, chỉ chỉ cách dùng. Thiết bị đang đăng nhập này là bên duyệt. */
export default function QrMethod() {
  return (
    <section aria-label={tr("dang_nhap_bang_ma_qr")} className={SECTION}>
      <h2 className="font-bold mb-1">{tr("dang_nhap_bang_ma_qr")}</h2>
      <p className="text-sm mb-2">
        {tr("tren_thiet_bi_khac_mo_trang")}
      </p>
      <Link href="/user" className="text-sm text-line underline">{tr("mo_trang_dang_nhap")}</Link>
    </section>
  );
}
