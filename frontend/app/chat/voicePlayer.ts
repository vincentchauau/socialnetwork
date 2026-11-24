"use client";

import { useSyncExternalStore } from "react";

import { CALL_FRAME_EVENT } from "./meetingRequest";
import type { SlideFrame, VoiceFrame } from "./protocol";

/**
 * What the virtual people say and show in a call: the sentences they read aloud (frames `voice`, PCM16 mono) are played one after the other, the
 * sentence on its way is the subtitle and the person who says it is the one who "speaks"; a slide (frame `slide`) stays until it is taken away.
 * It is one for the whole page: the socket of the room hands the frames to it (`CALL_FRAME_EVENT`). Whoever starts to talk can cut it short
 * (`interruptVoice`): what is on its way is dropped, and so are the sentences of the same answer that come later.
 */
export interface VoiceState {
  playing: boolean;
  speakingUserId: number | null;
  subtitle: { name: string; text: string } | null;
  slide: { userId: number; name: string; title: string; lines: string[] } | null;
}

const SUBTITLE_STAYS_MS = 4000;
const READ_MS_PER_CHAR = 55; // how long a sentence without a voice stays on screen
const MAX_IGNORED = 50;

let state: VoiceState = { playing: false, speakingUserId: null, subtitle: null, slide: null };
const listeners = new Set<() => void>();
let queue: VoiceFrame[] = [];
let running = false;
let context: AudioContext | null = null;
let current: AudioBufferSourceNode | null = null;
let hideTimer: number | undefined;
let currentId = ""; // the answer whose sentence is playing
const ignored: string[] = []; // answers that were cut short

function set(next: Partial<VoiceState>): void {
  state = { ...state, ...next };
  listeners.forEach((listener) => listener());
}

function playPcm(audio: string, rate: number): Promise<void> {
  return new Promise((resolve) => {
    try {
      const bytes = Uint8Array.from(atob(audio), (c) => c.charCodeAt(0));
      const pcm = new Int16Array(bytes.buffer, 0, bytes.length >> 1);
      context ??= new AudioContext();
      void context.resume(); // (a context made without a click can start suspended)
      const buffer = context.createBuffer(1, pcm.length, rate);
      const data = buffer.getChannelData(0);
      for (let i = 0; i < pcm.length; i++) data[i] = pcm[i] / 32768;
      const source = context.createBufferSource();
      source.buffer = buffer;
      source.connect(context.destination);
      source.onended = () => {
        current = null;
        resolve();
      };
      current = source;
      source.start();
      window.setTimeout(resolve, buffer.duration * 1000 + 1500); // (a page that may not play sound must not hold the queue)
    } catch {
      resolve();
    }
  });
}

const wait = (ms: number): Promise<void> => new Promise((resolve) => window.setTimeout(resolve, ms));

async function run(): Promise<void> {
  if (running) return;
  running = true;
  while (queue.length > 0) {
    const frame = queue.shift() as VoiceFrame;
    currentId = frame.id;
    window.clearTimeout(hideTimer);
    set({ playing: true, speakingUserId: frame.userId, subtitle: { name: frame.name, text: frame.text } });
    await (frame.pcm && frame.rate ? playPcm(frame.pcm, frame.rate) : wait(frame.text.length * READ_MS_PER_CHAR));
  }
  running = false;
  set({ playing: false, speakingUserId: null });
  hideTimer = window.setTimeout(() => set({ subtitle: null }), SUBTITLE_STAYS_MS);
}

function onFrame(event: Event): void {
  const frame = (event as CustomEvent<VoiceFrame | SlideFrame>).detail;
  if (frame.type === "slide") {
    set({ slide: frame.lines.length > 0 ? { userId: frame.userId, name: frame.name, title: frame.title, lines: frame.lines } : null });
    return;
  }
  if (ignored.includes(frame.id)) return;
  queue.push(frame);
  void run();
}

/** Starts to listen to the socket of the room for the call on screen; returns how to stop. */
export function startVoicePlayer(): () => void {
  window.addEventListener(CALL_FRAME_EVENT, onFrame);
  return () => {
    window.removeEventListener(CALL_FRAME_EVENT, onFrame);
    interruptVoice();
    set({ subtitle: null, slide: null });
  };
}

/** Somebody starts to talk: what is being read aloud stops, and so does the rest of that answer. */
export function interruptVoice(): void {
  for (const frame of queue) if (!ignored.includes(frame.id)) ignored.push(frame.id);
  if (running && currentId && !ignored.includes(currentId)) ignored.push(currentId); // (the sentences of this answer that are still to come)
  queue = [];
  try {
    current?.stop();
  } catch {
    // already ended
  }
  while (ignored.length > MAX_IGNORED) ignored.shift();
}

const subscribe = (listener: () => void): (() => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

export function useVoicePlayer(): VoiceState {
  return useSyncExternalStore(subscribe, () => state, () => state);
}

