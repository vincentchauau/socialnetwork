"use client";

import { useState } from "react";

import TokenConfirm from "./TokenConfirm";
import { PRIMARY_BUTTON } from "./ui";
import { loginWithMagicLink } from "../lib/auth";
import { goTo, postLoginTarget } from "../lib/navigate";

/** Đăng nhập bằng liên kết trong email. Nếu cần xác minh thêm thì chuyển về /login kèm ghi chú. */
export default function MagicLoginView() {
  const [needsMfa, setNeedsMfa] = useState(false);

  return (
    <TokenConfirm
      title="Đăng nhập bằng email"
      intro="Bấm nút bên dưới để hoàn tất đăng nhập."
      button="Đăng nhập"
      missing="Liên kết không hợp lệ hoặc đã hết hạn."
      confirm={async (token) => {
        const result = await loginWithMagicLink(token);
        if (result.kind === "mfa") setNeedsMfa(true);
        else goTo(postLoginTarget());
      }}
      success={
        needsMfa ? (
          <>
            <p role="status" className="text-sm mb-2">
              Tài khoản này cần xác minh thêm. Hãy đăng nhập bằng mật khẩu hoặc mã email trên trang đăng nhập để hoàn tất.
            </p>
            <a href="/login" className={`${PRIMARY_BUTTON} block text-center`}>Về trang đăng nhập</a>
          </>
        ) : (
          <p role="status" className="text-sm text-green-700 mb-2">Đang chuyển hướng...</p>
        )
      }
      failure={
        <>
          <p role="alert" className="text-sm text-red-600 mb-2">Liên kết không hợp lệ hoặc đã hết hạn.</p>
          <a href="/login" className={`${PRIMARY_BUTTON} block text-center`}>Về trang đăng nhập</a>
        </>
      }
    />
  );
}
