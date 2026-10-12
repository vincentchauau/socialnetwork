"use client";

import BiometricSwitch from "./BiometricSwitch";
import { setBiometric2fa } from "../lib/auth";

interface Props {
  enabled: boolean;
  hasPassword: boolean;
  /** Cần đã lưu ít nhất một mẫu (giọng nói hoặc khuôn mặt). */
  ready: boolean;
  onDone: () => void | Promise<void>;
}

export const SECOND_FACTOR_TITLE = "Yêu cầu giọng nói/khuôn mặt sau khi đăng nhập bằng mật khẩu hoặc Google";

/** Công tắc xác minh thêm sau bước mật khẩu/Google (mặc định tắt). */
export default function Biometric2faToggle({ enabled, hasPassword, ready, onDone }: Props) {
  return (
    <BiometricSwitch
      id="second-factor"
      title={SECOND_FACTOR_TITLE}
      enabled={enabled}
      hasPassword={hasPassword}
      canEnable={ready}
      requirement="Cần lưu ít nhất một mẫu (giọng nói hoặc khuôn mặt) trước khi bật."
      description="Mặc định tắt. Khi bật, sau khi nhập đúng mật khẩu hoặc đăng nhập Google, bạn phải quay thêm một đoạn để xác minh: mọi mẫu đã lưu đều phải khớp. Cảnh báo: nếu mất thiết bị ghi âm, webcam hỏng hoặc giọng/khuôn mặt thay đổi, bạn có thể bị khóa khỏi tài khoản. Hãy chắc chắn trước khi bật."
      warning={
        <p role="note" className="text-sm text-amber-800 bg-amber-50 border border-amber-300 rounded p-2 mb-2">
          Nếu máy ghi âm hoặc webcam không dùng được, bạn sẽ không đăng nhập được khi tính năng này đang bật.
        </p>
      }
      enableLabel="Bật yêu cầu xác minh sinh trắc học"
      disableLabel="Tắt yêu cầu xác minh sinh trắc học"
      save={setBiometric2fa}
      onDone={onDone}
    />
  );
}
