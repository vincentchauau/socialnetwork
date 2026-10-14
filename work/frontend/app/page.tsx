"use client";

import AuthGate from "./AuthGate";
import WorkApp from "./components/WorkApp";

export default function Page() {
  return (
    <AuthGate title="Tệp & cơ sở dữ liệu">
      {(user) => <WorkApp isAdmin={user.role === "admin"} />}
    </AuthGate>
  );
}
