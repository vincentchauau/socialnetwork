"use client";

import TokenConfirm from "./TokenConfirm";
import { PRIMARY_BUTTON } from "./ui";
import { verifyEmailToken } from "../lib/auth";
import { tr } from "../i18n";
import Link from "next/link";

export default function VerifyEmailView() {
  return (
    <TokenConfirm
      title={tr("xac_nhan_email")}
      intro={tr("bam_nut_ben_duoi_de_xac")}
      button={tr("xac_nhan_email")}
      missing={tr("lien_ket_khong_hop_le_hoac")}
      confirm={async (token) => void (await verifyEmailToken(token))}
      success={
        <>
          <p role="status" className="text-sm text-line mb-2">{tr("da_xac_nhan_email")}</p>
          <Link href="/user" className={`${PRIMARY_BUTTON} block text-center`}>{tr("ve_trang_tai_khoan")}</Link>
        </>
      }
      failure={
        <p role="alert" className="text-sm text-line mb-2">
          {tr("lien_ket_khong_hop_le_hoac_2")}
        </p>
      }
    />
  );
}
