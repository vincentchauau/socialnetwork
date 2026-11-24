"use client";

import { browserSupportsWebAuthn } from "@simplewebauthn/browser";
import { useEffect, useState } from "react";

/** Whether this browser can do WebAuthn; false on the server and on first render to keep hydration stable. */
export function usePasskeySupport(): boolean {
  const [supported, setSupported] = useState(false);
  useEffect(() => setSupported(browserSupportsWebAuthn()), []);
  return supported;
}
