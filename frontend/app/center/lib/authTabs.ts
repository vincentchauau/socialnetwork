import type { TreeNode } from "@sn/compounds/TreeView";

import type { AuthConfig } from "./auth";
import { tr } from "../i18n";

/** The two modes of the sign-in page. */
export type EntryMode = "login" | "register";
/** Plus the account page, which shows the same tabs for a signed-in user. */
export type AuthMode = EntryMode | "account";

/** Một cách xác thực = một tab. */
export type AuthTab =
  | "password" | "webcam" | "voice" | "totp" | "recovery" | "email" | "phone" | "google" | "passkey" | "qr"
  | "username" | "sessions"; // the account page only: sections above its button, not tabs

export const TAB_LABEL: Record<AuthTab, string> = {
  get password() { return tr("mat_khau"); },
  get webcam() { return tr("webcam_khuon_mat"); },
  get voice() { return tr("giong_noi"); },
  get totp() { return tr("ma_totp"); },
  get recovery() { return tr("ma_khoi_phuc"); },
  email: "Email",
  phone: "SMS",
  google: "Google",
  passkey: "Passkey",
  get qr() { return tr("ma_qr"); },
  get username() { return tr("ten_dang_nhap"); },
  get sessions() { return tr("phien_va_xoa_tai_khoan"); },
};

// The key doubles as the #hash of the tab. The prefix keeps it from matching an element id on the page (#password).
const KEY_PREFIX = "cach-";
export const tabKey = (tab: AuthTab): string => `${KEY_PREFIX}${tab}`;
export const tabOf = (key: string): AuthTab => key.slice(KEY_PREFIX.length) as AuthTab;

/** Which tabs a mode offers. Registration cannot use codes sent later (TOTP, SMS) or a QR approved by another device. */
export function availableTabs(mode: AuthMode, config: AuthConfig): AuthTab[] {
  const registering = mode === "register";
  const tabs: (AuthTab | false)[] = [
    "password",
    config.biometrics_enabled && "webcam",
    config.biometrics_enabled && "voice",
    !registering && "totp",
    !registering && "recovery",
    config.email_enabled && "email",
    !registering && config.phone_enabled && "phone",
    Boolean(config.google_client_id) && "google",
    "passkey",
    !registering && "qr",
  ];
  return tabs.filter((tab): tab is AuthTab => tab !== false);
}

const GROUPS: { key: string; label: string; tabs: AuthTab[] }[] = [
  { key: "sinh-trac-hoc", get label() { return tr("sinh_trac_hoc"); }, tabs: ["webcam", "voice"] },
  { key: "xac-thuc-2-buoc", get label() { return tr("xac_thuc_2_buoc"); }, tabs: ["totp", "recovery"] },
  { key: "email-sms", get label() { return tr("email_va_sms"); }, tabs: ["email", "phone"] },
  { key: "ben-ngoai", label: "Google, Passkey, QR", tabs: ["google", "passkey", "qr"] },
];

/** The tab tree: Password on its own, then the groups that still have a tab in this mode. */
export function authTree(mode: AuthMode, config: AuthConfig): TreeNode[] {
  const offered = new Set(availableTabs(mode, config));
  const leaf = (tab: AuthTab): TreeNode => ({ key: tabKey(tab), label: TAB_LABEL[tab] });
  const groups = GROUPS.flatMap((group) => {
    const children = group.tabs.filter((tab) => offered.has(tab)).map(leaf);
    return children.length > 0 ? [{ key: group.key, label: group.label, children }] : [];
  });
  return [leaf("password"), ...groups];
}

/** Tabs whose action is its own button inside the tab (a code to send, a QR to scan): the bottom button is not used there. */
export const SELF_ACTING_TABS: readonly AuthTab[] = ["email", "phone", "google", "qr"];
