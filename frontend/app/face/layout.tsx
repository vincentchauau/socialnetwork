import type { Metadata } from "next";
import type { ReactNode } from "react";
import AppFrame from "../chat/dock/AppFrame";
import "./face.css";

export const metadata: Metadata = { title: "Đối xứng khuôn mặt · Social Network" };

export default function FaceLayout({ children }: { children: ReactNode }) {
  return (
    <AppFrame name="Face" app="face" css="app-face">{children}</AppFrame>
  );
}
