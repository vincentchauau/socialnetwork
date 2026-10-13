"use client";

import AuthGate from "./AuthGate";
import HomeView from "./components/HomeView";

export default function HomePage() {
  return <AuthGate title="Ma Sói">{(user) => <HomeView user={user} />}</AuthGate>;
}
