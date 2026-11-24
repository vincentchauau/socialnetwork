import type { Metadata } from "next";
import MagicLoginView from "../../components/MagicLoginView";

export default function MagicLoginPage() {
  return <MagicLoginView />;
}

/** The page URL carries (or follows) a secret link: never send it as a Referer. */
export const metadata: Metadata = { referrer: "no-referrer" };
