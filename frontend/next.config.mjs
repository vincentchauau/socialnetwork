import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  // One app for the whole site: the center (folder app/center) at the root, every other app under /<slug>.
  output: "standalone",
  // Lets the app import ../shared/frontend and keeps it in the standalone trace.
  experimental: { externalDir: true },
  outputFileTracingRoot: path.join(here, ".."),
  // The pages of the center live in the folder `app/center`, and are still at the root of the site: /, /login, /account...
  // The Database app is the home page: /database is only the folder it lives in, so its old address leads to /.
  async redirects() {
    // The sign-in, the account and the profile are one page; the old addresses (also the links of the emails and of the QR codes) lead to it.
    return [
      { source: "/database", destination: "/", permanent: true },
      // Users is an app of the home page like the others: its own folder address leads to /.
      { source: "/center", destination: "/?app=center", permanent: false },
      { source: "/job", destination: "/?app=job", permanent: false },
      { source: "/market", destination: "/?app=market", permanent: false },
      { source: "/center/:path((?!user|forgot-password|reset-password|verify-email).+)", destination: "/", permanent: false },
      { source: "/login/:path*", destination: "/user/:path*", permanent: true },
      { source: "/account", destination: "/user", permanent: true },
      { source: "/profile", destination: "/user", permanent: true },
      // The market is done in the User pane of the home page (shop, cart, pay, orders, sell): its own pages are only the pages that pane opens.
      // Every app is done in the User pane of the home page, so the pages of the apps lead there. Left alone: the account pages and the
      // pages for people who have no account (the links of a shared file, a certificate to check).
      ...["face", "chat", "call", "werewolf", "roulette"].map((app) => ({ source: `/${app}/:path*`, destination: "/", permanent: false })),
      { source: "/admin/:path*", destination: "/", permanent: false }, // the tables of every app are the Database pane of `/`, for an admin
      { source: "/file", destination: "/", permanent: false },
      { source: "/file/:path((?!s/).+)", destination: "/", permanent: false },
    ];
  },
  async rewrites() {
    const pages = ["user", "forgot-password", "reset-password", "verify-email"];
    return [{ source: "/", destination: "/database" }, ...pages.map((page) => ({ source: `/${page}/:path*`, destination: `/center/${page}/:path*` }))];
  },
};

export default nextConfig;
