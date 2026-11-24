import type { Metadata } from "next";
import ResetPasswordForm from "../components/ResetPasswordForm";

export default function ResetPasswordPage() {
  return <ResetPasswordForm />;
}

/** The page URL carries (or follows) a secret link: never send it as a Referer. */
export const metadata: Metadata = { referrer: "no-referrer" };
