"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";

import { User, loadSession } from "@sn/api";
import { PostingSummary, EMPLOYMENT_LABELS, formatDate, formatSalary } from "./lib";

type Auth =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "error" }
  | { status: "signed-in"; user: User };

const NAV: { href: string; text: string }[] = [
  { href: "/", text: "Search" },
  { href: "/saved", text: "Saved" },
  { href: "/applications", text: "My applications" },
  { href: "/employer", text: "Employer" },
  { href: "/profile", text: "Profile" },
];

function Nav() {
  const pathname = usePathname();
  return (
    <nav aria-label="Jobs">
      <ul className="nav">
        {NAV.map(({ href, text }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <li key={href}>
              <Link href={href} aria-current={active ? "page" : undefined}>
                {text}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/** Page frame: resolves the session, then renders `children(user)` for signed-in users. */
export function Protected({
  title,
  children,
}: {
  title: string;
  children: (user: User) => ReactNode;
}) {
  const [auth, setAuth] = useState<Auth>({ status: "loading" });

  useEffect(() => {
    loadSession()
      .then((user) => setAuth(user ? { status: "signed-in", user } : { status: "anonymous" }))
      .catch(() => setAuth({ status: "error" }));
  }, []);

  if (auth.status === "loading") return <p className="muted">Loading…</p>;

  const home = <a href="/">← Home</a>;

  if (auth.status === "error") {
    return (
      <div className="stack">
        <h1>{title}</h1>
        <p role="alert" className="error">
          Could not reach the server. Please try again.
        </p>
        {home}
      </div>
    );
  }

  if (auth.status === "anonymous") {
    return (
      <div className="stack">
        <h1>{title}</h1>
        <p>
          Please <a href="/login">sign in</a> first.
        </p>
        {home}
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="row wrap between">
        {home}
        <span className="muted">Signed in as {auth.user.username}</span>
      </div>
      <Nav />
      <h1 style={{ margin: 0 }}>{title}</h1>
      {children(auth.user)}
    </div>
  );
}

export function Status({
  loading,
  error,
  empty,
  emptyText,
}: {
  loading: boolean;
  error: string | null;
  empty: boolean;
  emptyText: string;
}) {
  if (loading) return <p className="muted" role="status">Loading…</p>;
  if (error) return <p role="alert" className="error">{error}</p>;
  if (empty) return <p className="muted">{emptyText}</p>;
  return null;
}

export function JobCard({ job, children }: { job: PostingSummary; children?: ReactNode }) {
  const salary = formatSalary(job);
  const facts = [
    job.company,
    job.location || null,
    job.remote ? "Remote" : null,
    EMPLOYMENT_LABELS[job.employment_type],
    salary,
  ].filter((fact): fact is string => Boolean(fact));
  return (
    <li className="card stack">
      <h2>
        <Link href={`/job/${job.id}`}>{job.title}</Link>
      </h2>
      <p className="muted break" style={{ margin: 0 }}>
        {facts.join(" · ")}
      </p>
      {job.snippet && <p className="break" style={{ margin: 0 }}>{job.snippet}</p>}
      {job.tags.length > 0 && (
        <ul className="tags" aria-label="Tags">
          {job.tags.map((tag) => (
            <li key={tag} className="tag">{tag}</li>
          ))}
        </ul>
      )}
      <p className="muted" style={{ margin: 0 }}>
        Posted {formatDate(job.created_at)} by {job.owner_username}
        {job.status === "closed" && " · Closed"}
        {job.expired && " · Expired"}
        {job.applied && " · Applied"}
        {job.saved && " · Saved"}
      </p>
      {children}
    </li>
  );
}

export function Field({
  label,
  grow,
  children,
}: {
  label: string;
  grow?: boolean;
  children: ReactNode;
}) {
  return (
    <label className={grow ? "field grow" : "field"}>
      <span>{label}</span>
      {children}
    </label>
  );
}
