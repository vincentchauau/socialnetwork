import type { Metadata } from "next";
import VerifyEmailView from "../components/VerifyEmailView";

export default function VerifyEmailPage() {
  return <VerifyEmailView />;
}

/** The page URL carries (or follows) a secret link: never send it as a Referer. */
export const metadata: Metadata = { referrer: "no-referrer" };
