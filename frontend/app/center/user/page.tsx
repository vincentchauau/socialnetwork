"use client";

import { useEffect } from "react";

import LoginFlow from "../components/LoginFlow";
import { useSession } from "@sn/lib/useSession";

/** /user: the sign-in for a visitor. A signed-in person has the account in the User pane of the home page (the same screen as the apps), so it leads there. */
export default function LoginPage() {
  const session = useSession();
  useEffect(() => {
    if (session.status === "signed-in") window.location.replace("/?app=center");
  }, [session.status]);
  if (session.status === "signed-in") return null;
  return <LoginFlow />;
}
