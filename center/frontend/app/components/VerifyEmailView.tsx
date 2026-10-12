"use client";

import TokenConfirm from "./TokenConfirm";
import { PRIMARY_BUTTON } from "./ui";
import { verifyEmailToken } from "../lib/auth";

export default function VerifyEmailView() {
  return (
    <TokenConfirm
      title="Xác nhận email"
      intro="Bấm nút bên dưới để xác nhận địa chỉ email của bạn."
      button="Xác nhận email"
      missing="Liên kết không hợp lệ hoặc đã hết hạn."
      confirm={async (token) => void (await verifyEmailToken(token))}
      success={
        <>
          <p role="status" className="text-sm text-green-700 mb-2">Đã xác nhận email.</p>
          <a href="/account" className={`${PRIMARY_BUTTON} block text-center`}>Về trang tài khoản</a>
        </>
      }
      failure={
        <p role="alert" className="text-sm text-red-600 mb-2">
          Liên kết không hợp lệ hoặc đã hết hạn. Hãy yêu cầu gửi lại email xác minh trong trang Tài khoản.
        </p>
      }
    />
  );
}
