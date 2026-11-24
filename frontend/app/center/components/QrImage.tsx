"use client";

import { useEffect, useState } from "react";
import QRCode from "qrcode";

interface Props {
  value: string;
  alt: string;
  failureText: string;
}

/** The QR is drawn in the browser (SVG data URL): the content never goes to a third-party service. */
export default function QrImage({ value, alt, failureText }: Props) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    QRCode.toString(value, { type: "svg", margin: 1, width: 192 })
      .then((svg) => !cancelled && setSrc(`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [value]);

  if (failed) return <p role="note" className="text-sm text-line mb-2">{failureText}</p>;
  if (!src) return null;
  return <img src={src} alt={alt} width={192} height={192} className="mx-auto mb-2 border" />;
}
