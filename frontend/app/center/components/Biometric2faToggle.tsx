"use client";

import BiometricSwitch from "./BiometricSwitch";
import { setBiometric2fa } from "../lib/auth";
import { tr } from "../i18n";

interface Props {
  enabled: boolean;
  hasPassword: boolean;
  /** Cần đã lưu ít nhất một mẫu (giọng nói hoặc khuôn mặt). */
  ready: boolean;
  onDone: () => void | Promise<void>;
}

const SECOND_FACTOR_TITLE = tr("yeu_cau_giong_noi_khuon_mat");

/** Công tắc xác minh thêm sau bước mật khẩu/Google (mặc định tắt). */
export default function Biometric2faToggle({ enabled, hasPassword, ready, onDone }: Props) {
  return (
    <BiometricSwitch
      id="second-factor"
      title={SECOND_FACTOR_TITLE}
      enabled={enabled}
      hasPassword={hasPassword}
      canEnable={ready}
      requirement={tr("can_luu_it_nhat_mot_mau")}
      description={tr("mac_dinh_tat_khi_bat_sau")}
      warning={
        <p role="note" className="text-sm text-line bg-solid border border-line rounded p-2 mb-2">
          {tr("neu_may_ghi_am_hoac_webcam")}
        </p>
      }
      enableLabel={tr("bat_yeu_cau_xac_minh_sinh")}
      disableLabel={tr("tat_yeu_cau_xac_minh_sinh")}
      save={setBiometric2fa}
      onDone={onDone}
    />
  );
}
