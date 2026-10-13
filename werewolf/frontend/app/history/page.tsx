"use client";

import AuthGate from "../AuthGate";
import HistoryView from "../components/HistoryView";

export default function HistoryPage() {
  return <AuthGate title="Lịch sử ván chơi">{() => <HistoryView />}</AuthGate>;
}
