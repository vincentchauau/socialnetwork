"use client";

import { useEffect, useRef, useState } from "react";

import Button from "@sn/elements/Button";

import { chatApi } from "../api";
import { errorMessage } from "../errors";
import { tr } from "../i18n";
import { interruptVoice } from "../voicePlayer";
import { deviceProblem } from "./MediaCheck";

const SPEECH_LEVEL = 0.012; // of full scale: above this somebody is talking
const END_OF_TALK_MS = 1200; // quiet after the talk that ends the message
const NOTHING_HEARD_MS = 8000; // no talk at all for this long: it stops
const MOST_TALK_MS = 25000;
const LEAST_TALK_MS = 400;
const TARGET_RATE = 16000; // the sound is sent at about this rate (the browser's rate divided by a whole number)
const CHUNK = 4096;

/** `samples` at `rate` Hz, brought down to about `TARGET_RATE` by averaging groups of samples; returns the new samples and their rate. */
export function decimate(samples: Float32Array, rate: number): { pcm: Int16Array; rate: number } {
  const factor = Math.max(1, Math.round(rate / TARGET_RATE));
  const length = Math.floor(samples.length / factor);
  const pcm = new Int16Array(length);
  for (let i = 0; i < length; i++) {
    let sum = 0;
    for (let j = 0; j < factor; j++) sum += samples[i * factor + j];
    pcm[i] = Math.max(-1, Math.min(1, sum / factor)) * 32767;
  }
  return { pcm, rate: Math.round(rate / factor) };
}

function toBase64(pcm: Int16Array): string {
  const bytes = new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

/**
 * The Voice button next to the message box: press it, say the message, and it is sent when you stop talking (or press it again). The sound is made
 * into words by the server and written in the room as your message; the virtual people of the room answer it as they would a typed one. It works in
 * every browser (the sound is taken here, not recognised here), and nothing is kept.
 */
export default function VoiceButton({ slug, disabled }: { slug: string; disabled: boolean }) {
  const [state, setState] = useState<"idle" | "listening" | "sending">("idle");
  const [notice, setNotice] = useState<string | null>(null);
  const stopRef = useRef<(() => void) | null>(null); // drops the sound (the button goes away)
  const sendRef = useRef<(() => void) | null>(null); // sends what has been said so far

  useEffect(() => () => stopRef.current?.(), []);

  async function start() {
    setNotice(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch (caught) {
      setNotice(deviceProblem(caught, "mic"));
      return;
    }
    const context = new AudioContext();
    const source = context.createMediaStreamSource(stream);
    const processor = context.createScriptProcessor(CHUNK, 1, 1);
    const silent = context.createGain();
    silent.gain.value = 0;
    const chunks: Float32Array[] = [];
    let spoke = false;
    let lastTalk = performance.now();
    const began = performance.now();
    let finished = false;

    const finish = async (send: boolean) => {
      if (finished) return;
      finished = true;
      stopRef.current = null;
      sendRef.current = null;
      processor.disconnect();
      source.disconnect();
      stream.getTracks().forEach((track) => track.stop());
      const rate = context.sampleRate;
      void context.close();
      if (!send || !spoke) {
        setState("idle");
        if (send && !spoke) setNotice(tr("rm_khong_nghe_thay"));
        return;
      }
      const all = new Float32Array(chunks.reduce((n, c) => n + c.length, 0));
      let at = 0;
      for (const c of chunks) {
        all.set(c, at);
        at += c.length;
      }
      if (all.length / rate < LEAST_TALK_MS / 1000) {
        setState("idle");
        setNotice(tr("rm_khong_nghe_thay"));
        return;
      }
      setState("sending");
      try {
        const sound = decimate(all, rate);
        await chatApi.voiceMessage(slug, toBase64(sound.pcm), sound.rate);
      } catch (caught) {
        setNotice(errorMessage(caught));
      } finally {
        setState("idle");
      }
    };
    stopRef.current = () => void finish(false);
    sendRef.current = () => void finish(true);

    processor.onaudioprocess = (event) => {
      const input = event.inputBuffer.getChannelData(0);
      let sum = 0;
      for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
      const now = performance.now();
      if (Math.sqrt(sum / input.length) > SPEECH_LEVEL) {
        if (!spoke) interruptVoice(); // (you start to talk: what a virtual person is reading stops)
        spoke = true;
        lastTalk = now;
      }
      if (spoke) chunks.push(new Float32Array(input));
      const quiet = now - lastTalk;
      if ((spoke && quiet >= END_OF_TALK_MS) || now - began >= MOST_TALK_MS) void finish(true);
      else if (!spoke && now - began >= NOTHING_HEARD_MS) void finish(true);
    };
    source.connect(processor);
    processor.connect(silent);
    silent.connect(context.destination);
    setState("listening");
  }

  function press() {
    if (state === "idle") void start();
    else if (state === "listening") sendRef.current?.(); // pressed again: it is sent now
  }

  return (
    <span style={{ display: "inline-flex", flexDirection: "column", gap: 2 }}>
      <Button
        type="button"
        size="sm"
        variant={state === "listening" ? "primary" : "secondary"}
        aria-pressed={state === "listening"}
        disabled={disabled || state === "sending"}
        onClick={press}
      >
        {state === "listening" ? tr("rm_dang_nghe_gui") : state === "sending" ? tr("rm_dang_gui") : tr("rm_voice")}
      </Button>
      {notice && <span role="alert" className="cw-room-sub">{notice}</span>}
    </span>
  );
}
