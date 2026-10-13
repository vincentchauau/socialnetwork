"use client";

import AuthGate from "./AuthGate";
import LabApp from "./components/LabApp";

export default function LabPage() {
  return <AuthGate title="Phòng thí nghiệm">{() => <LabApp />}</AuthGate>;
}
