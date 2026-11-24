"use client";

import { type ReactNode, createContext, useContext, useState } from "react";

import { INPUT, LABEL } from "./ui";
import { tr } from "../i18n";
import TextBox from "@sn/elements/TextBox";

interface PasswordConfirmValue {
  password: string;
  setPassword: (password: string) => void;
}

const PasswordConfirmContext = createContext<PasswordConfirmValue | null>(null);

/** One "type your password again" field for a whole page: every action below reads the password from it. */
export function PasswordConfirmProvider({ children }: { children: ReactNode }) {
  const [password, setPassword] = useState("");
  return <PasswordConfirmContext.Provider value={{ password, setPassword }}>{children}</PasswordConfirmContext.Provider>;
}

/**
 * The password an action sends to prove it is the owner. Under a PasswordConfirmProvider it is the page's one field
 * (`isShared`: the action draws no field of its own); on its own it keeps a local value and draws its field.
 */
export function usePasswordProof(): PasswordConfirmValue & { isShared: boolean } {
  const shared = useContext(PasswordConfirmContext);
  const [local, setLocal] = useState("");
  return shared ? { ...shared, isShared: true } : { password: local, setPassword: setLocal, isShared: false };
}

/** The page's one password field; it renders nothing outside a provider. */
export function PasswordConfirmField() {
  const shared = useContext(PasswordConfirmContext);
  if (!shared) return null;
  return (
    <div className="text-left mb-4">
      <label htmlFor="proof-password" className={LABEL}>{tr("nhap_lai_mat_khau_de_xac")}</label>
      <TextBox id="proof-password" type="password" value={shared.password} autoComplete="current-password"
             onChange={(event) => shared.setPassword(event.target.value)} className={INPUT} />
    </div>
  );
}
