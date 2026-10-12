"use client";

import BiometricSwitch from "./BiometricSwitch";
import BiometricWarning from "./BiometricWarning";
import { setBiometricLogin } from "../lib/auth";

interface Props {
  enabled: boolean;
  hasPassword: boolean;
  /** Cần đã lưu cả giọng nói và khuôn mặt. */
  ready: boolean;
  onDone: () => void | Promise<void>;
}

export const PASSWORDLESS_TITLE = "Đăng nhập không cần mật khẩu bằng giọng nói + khuôn mặt";

/** Công tắc đăng nhập không mật khẩu (cách đăng nhập riêng, mặc định tắt). */
export default function BiometricLoginToggle({ enabled, hasPassword, ready, onDone }: Props) {
  return (
    <BiometricSwitch
      id="passwordless"
      title={PASSWORDLESS_TITLE}
      enabled={enabled}
      hasPassword={hasPassword}
      canEnable={ready}
      requirement="Cần lưu đủ cả giọng nói và khuôn mặt trước khi bật."
      description="Mặc định tắt. Khi bật, bạn có thể đăng nhập chỉ bằng tên đăng nhập + khuôn mặt + giọng nói (để trống mật khẩu). Phải khớp cả hai, với ngưỡng nghiêm hơn, và bị khóa tạm sau nhiều lần sai. Có hay không bật, đăng nhập bằng mật khẩu vẫn đăng nhập bình thường."
      warning={<BiometricWarning />}
      enableLabel="Bật đăng nhập không mật khẩu"
      disableLabel="Tắt đăng nhập không mật khẩu"
      save={setBiometricLogin}
      onDone={onDone}
    />
  );
}
