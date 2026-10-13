import type { Metadata } from "next";
import QrApproveView from "../../components/QrApproveView";

export default function QrApprovePage() {
  return <QrApproveView />;
}

/** The URL fragment carries the request id: never send the page URL as a Referer. */
export const metadata: Metadata = { referrer: "no-referrer" };
