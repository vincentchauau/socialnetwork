"use client";

import { KeyboardEvent, useRef } from "react";

export type Method = "password" | "google" | "voice" | "webcam" | "passkey";

export const METHOD_LABEL: Record<Method, string> = {
  password: "Mật khẩu",
  google: "Google",
  voice: "Giọng nói",
  webcam: "Webcam (khuôn mặt)",
  passkey: "Passkey",
};

interface Props {
  methods: Method[];
  value: Method;
  disabled?: boolean;
  onChange: (method: Method) => void;
}

/** Bộ chọn một cách đăng nhập (tablist): phím mũi tên, Home, End đổi tab. */
export default function MethodTabs({ methods, value, disabled, onChange }: Props) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKeyDown(event: KeyboardEvent, index: number) {
    const last = methods.length - 1;
    const target =
      event.key === "ArrowRight" ? (index === last ? 0 : index + 1)
      : event.key === "ArrowLeft" ? (index === 0 ? last : index - 1)
      : event.key === "Home" ? 0
      : event.key === "End" ? last
      : -1;
    if (target < 0) return;
    event.preventDefault();
    onChange(methods[target]);
    refs.current[methods[target]]?.focus();
  }

  return (
    <div role="tablist" aria-label="Cách đăng nhập" className="flex gap-1 mb-4">
      {methods.map((method, index) => {
        const selected = method === value;
        return (
          <button
            key={method}
            ref={(node) => { refs.current[method] = node; }}
            type="button"
            role="tab"
            id={`tab-${method}`}
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            disabled={disabled}
            onClick={() => onChange(method)}
            onKeyDown={(event) => onKeyDown(event, index)}
            className={`flex-1 px-2 py-2 rounded border text-sm font-medium disabled:opacity-50 ${
              selected ? "bg-blue-600 text-white border-blue-600" : "bg-white text-gray-900"
            }`}
          >
            {METHOD_LABEL[method]}
          </button>
        );
      })}
    </div>
  );
}
