"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { tr } from "../i18n";

export const RECORD_MS = 5000;
export const EMPTY_RECORDING_HELP =
  tr("ban_ghi_rong_khong_nhan_duoc");
const FALLBACK_MIME = "application/octet-stream";

interface Options {
  constraints: MediaStreamConstraints;
  onRecorded: (blob: Blob) => void;
  /** MIME type used when the browser does not report one (for example "audio/webm"). */
  fallbackMime?: string;
}

const deviceError = (e: unknown) =>
  e instanceof Error ? tr("khong_truy_cap_duoc_thiet_bi", { p0: e.message }) : tr("khong_truy_cap_duoc_thiet_bi_2");

/** Records RECORD_MS then returns a Blob. Always stops tracks and revokes URLs on finish, failure or unmount. */
export function useMediaRecorder({ constraints, onRecorded, fallbackMime = FALLBACK_MIME }: Options) {
  const [isRecording, setRecording] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [recordedBytes, setRecordedBytes] = useState<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const urlRef = useRef<string | null>(null);
  const isMountedRef = useRef(true);
  const isBusyRef = useRef(false); // asking permission or recording: blocks overlapping start() calls
  const onRecordedRef = useRef(onRecorded);

  useEffect(() => {
    onRecordedRef.current = onRecorded;
  }, [onRecorded]);

  const release = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (isMountedRef.current) setStream(null);
  }, []);

  const replaceUrl = useCallback((next: string | null) => {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    urlRef.current = next;
    if (isMountedRef.current) setPreviewUrl(next);
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      const recorder = recorderRef.current;
      if (recorder && recorder.state !== "inactive") {
        recorder.onstop = null; // unmounted: no more setState / onRecorded
        recorder.stop();
      }
      release();
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    };
  }, [release]);

  const fail = useCallback(
    (message: string) => {
      release();
      isBusyRef.current = false;
      if (isMountedRef.current) {
        setRecording(false);
        setError(message);
      }
    },
    [release],
  );

  const start = useCallback(async () => {
    if (isBusyRef.current) return;
    isBusyRef.current = true;
    setError(null);
    setRecordedBytes(null);
    replaceUrl(null);
    let media: MediaStream;
    try {
      media = await navigator.mediaDevices.getUserMedia(constraints);
    } catch (e) {
      fail(deviceError(e));
      return;
    }
    if (!isMountedRef.current) {
      media.getTracks().forEach((t) => t.stop()); // unmounted while waiting for permission
      isBusyRef.current = false;
      return;
    }
    try {
      streamRef.current = media;
      setStream(media);
      const recorder = new MediaRecorder(media);
      recorderRef.current = recorder;
      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data);
      };
      recorder.onerror = () => fail(tr("ghi_bi_gian_doan_hay_thu"));
      recorder.onstop = () => {
        release();
        isBusyRef.current = false;
        setRecording(false);
        const blob = new Blob(chunks, { type: recorder.mimeType || fallbackMime });
        if (blob.size === 0) {
          setError(EMPTY_RECORDING_HELP);
          setRecordedBytes(0);
          return;
        }
        setRecordedBytes(blob.size);
        replaceUrl(URL.createObjectURL(blob));
        onRecordedRef.current(blob);
      };
      // No timeslice: Chrome would write WebM without a duration.
      recorder.start();
      setRecording(true);
      timerRef.current = setTimeout(() => {
        if (recorder.state !== "inactive") recorder.stop();
      }, RECORD_MS);
    } catch (e) {
      fail(deviceError(e));
    }
  }, [constraints, fail, fallbackMime, release, replaceUrl]);

  return { isRecording, previewUrl, error, stream, start, recordedBytes };
}
