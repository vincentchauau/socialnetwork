import type { Metadata } from "next";
import ForgotPasswordForm from "../components/ForgotPasswordForm";

export default function ForgotPasswordPage() {
  return <ForgotPasswordForm />;
}

/** The page URL carries (or follows) a secret link: never send it as a Referer. */
export const metadata: Metadata = { referrer: "no-referrer" };
