"use client";

import { useContext, useEffect, useMemo, useState } from "react";

import { LanguageSwitcher, ThemePicker } from "../compounds/SiteSettings";
import { LocaleProvider, useLocale } from "../lib/i18n";
import { useFramed } from "../lib/hooks";
import { NAV_NODES } from "../lib/nav";
import { useSession } from "../lib/useSession";
import { useT } from "../locales";
import Select from "../elements/Select";
import { AppsMenuExtras } from "../compounds/appsMenuExtras";
import { CHAT_API, apiFetch } from "../api";
import { BORDER } from "../lib/theme";

const SITE_LOCALES = ["vi", "en"];
const SITE_LOCALE_NAMES: Record<string, string> = { vi: "Tiếng Việt", en: "English" };

/**
 * The top bar of an app: the name of the page at the left, and the greeting, language and theme beside it (the list of apps is under Activities → All apps in a room). `href` is the page's own link, to mark it in the list. In a page that has its own
 * LocaleProvider (the center app) the bar shares it; otherwise the bar has its own.
 */
export default function SiteBar({ name, href }: { name: string; href: string }) {
  return (
    <LocaleProvider>
      <Bar href={href} />
    </LocaleProvider>
  );
}

function Bar({ href }: { href: string }) {
  const { t } = useT();
  const { locale } = useLocale();
  const auth = useSession();
  // The tab title follows the language: "<page> · <site>", or the site alone where the app has no title of its own.
  const slug = href.split("/")[1] ?? "";
  const own = t(`titles.${slug}`);
  const title = own === `titles.${slug}` ? t("site.brand") : `${own} · ${t("site.brand")}`;
  useEffect(() => {
    document.title = title;
  }, [title]);
  // <html lang> follows the shared locale, also when it was chosen in another app or tab.
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  // The apps: every app of the menu, then the groups that are not in it. The one open is the one with a current group or item.
  const extras = useContext(AppsMenuExtras);
  const apps = useMemo(() => {
    const listed = NAV_NODES.map((app) => ({
      label: app.label,
      href: app.href ?? "/",
      group: extras?.find((candidate) => app.href === `/${candidate.key}`),
    }));
    const unlisted = (extras ?? [])
      .filter((group) => !NAV_NODES.some((app) => app.href === `/${group.key}`))
      .map((group) => ({ label: group.key, href: "/", group }));
    return [...listed, ...unlisted];
  }, [extras]);
  const open = apps.find((app) => app.group && (app.group.current || app.group.items.some((item) => item.current)));
  if (useFramed()) return null;
  return (
    <nav aria-label={t("site.nav")} style={{ display: "flex", flexWrap: "nowrap", overflowX: "auto", justifyContent: "center", alignItems: "center", gap: 16, padding: "8px 12px" }}>
      <div>
        <Select
          id="sn-apps"
          aria-label={t("site.apps")}
          value={open?.label ?? ""}
          onChange={(event) => {
            const pick = apps.find((app) => app.label === event.target.value);
            if (!pick) return;
            if (pick.group?.onSelectApp) pick.group.onSelectApp();
            else window.location.assign(pick.href);
          }}
        >
          {!open ? <option value="">{t("site.apps")}</option> : null}
          {apps.map((app) => (
            <option key={app.label} value={app.label}>{app.label}</option>
          ))}
        </Select>
      </div>
      <UnreadBadge />
      {auth.status === "signed-in" ? (
        <span style={{ color: "inherit", fontSize: "0.9rem", whiteSpace: "nowrap" }}>
          {t("site.greeting")}, {auth.user.username}
        </span>
      ) : null}
      <LanguageSwitcher locales={SITE_LOCALES} names={SITE_LOCALE_NAMES} label={t("site.language")} />
      <div>
        <ThemePicker inline expanded labels={{ theme: t("site.theme"), color: t("site.themeColor"), count: t("site.themeCount") }} />
      </div>
    </nav>
  );
}

const POLL_MS = 60_000;

interface Summary {
  messages: number;
  requests: number;
  notices: number;
}

/** What waits for a signed-in person in the chat (unread messages, requests to write, notices), as a number next to the name of the page. */
function UnreadBadge() {
  const auth = useSession();
  const { t } = useT();
  const [waiting, setWaiting] = useState(0);
  const signedIn = auth.status === "signed-in";

  useEffect(() => {
    if (!signedIn) return;
    let current = true;
    const look = () =>
      apiFetch<Summary>(`${CHAT_API}/inbox/summary`).then(
        (summary) => current && setWaiting((summary?.messages ?? 0) + (summary?.requests ?? 0) + (summary?.notices ?? 0)),
        () => undefined, // the chat is not there (or not reachable): no number, and the page goes on
      );
    void look();
    const timer = setInterval(look, POLL_MS);
    window.addEventListener("focus", look);
    return () => {
      current = false;
      clearInterval(timer);
      window.removeEventListener("focus", look);
    };
  }, [signedIn]);

  if (waiting <= 0) return null;
  return (
    <a
      href="/chat"
      aria-label={`${t("site.inbox")}: ${t("site.inboxWaiting").replace("{n}", String(waiting))}`}
      style={{ marginLeft: 8, fontSize: "0.8rem", fontWeight: 700, color: "inherit", textDecoration: "none", border: `1px solid ${BORDER}`, borderRadius: 999, padding: "1px 8px" }}
    >
      💬 {waiting > 99 ? "99+" : waiting}
    </a>
  );
}
