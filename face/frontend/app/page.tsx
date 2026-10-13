"use client";

import AuthGate from "./AuthGate";
import FaceApp from "./components/FaceApp";

export default function FacePage() {
  return <AuthGate title="Phân tích đối xứng khuôn mặt">{() => <FaceApp />}</AuthGate>;
}
