"use client";

import { useParams } from "next/navigation";

import AuthGate from "../../AuthGate";
import RoomView from "../../components/RoomView";

export default function RoomPage() {
  const params = useParams<{ id: string }>();
  const code = String(params.id ?? "").toUpperCase();
  return <AuthGate title="Ma Sói">{() => <RoomView code={code} />}</AuthGate>;
}
