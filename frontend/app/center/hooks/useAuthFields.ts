"use client";

import { useState } from "react";

/**
 * Everything the user types or records across the tabs. It lives in the parent because a tab's panel may be
 * unmounted when another tab opens, and the bottom button needs the values of all of them.
 */
export function useAuthFields() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [audio, setAudio] = useState<Blob>();
  const [video, setVideo] = useState<Blob>();
  const [livenessToken, setLivenessToken] = useState<string>();
  const [googleToken, setGoogleToken] = useState<string>();
  const [totpCode, setTotpCode] = useState("");
  const [recoveryCode, setRecoveryCode] = useState("");
  const [needUsername, setNeedUsername] = useState(false); // only when the server asks (a very large system)
  const [recordingKey, setRecordingKey] = useState(0); // a new key empties the recorders

  function clearRecordings() {
    setAudio(undefined);
    setVideo(undefined);
    setLivenessToken(undefined);
    setRecordingKey((key) => key + 1);
  }

  /** A used or failed attempt must not leave secrets behind. */
  function clearSecrets() {
    setPassword("");
    setTotpCode("");
    setRecoveryCode("");
    clearRecordings();
  }

  return {
    username, setUsername, password, setPassword, email, setEmail,
    audio, setAudio, video, setVideo, livenessToken, setLivenessToken,
    googleToken, setGoogleToken, totpCode, setTotpCode, recoveryCode, setRecoveryCode,
    needUsername, setNeedUsername, recordingKey, clearRecordings, clearSecrets,
  };
}

export type AuthFields = ReturnType<typeof useAuthFields>;
