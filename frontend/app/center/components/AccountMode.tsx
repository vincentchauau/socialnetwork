"use client";

import { ReactNode, useCallback, useEffect, useState } from "react";

import { AccountChangesProvider, useAccountChanges } from "./AccountChanges";
import AccountTabContent from "./AccountTabContent";
import Alert from "@sn/elements/Alert";
import ChangeUsername from "./ChangeUsername";
import DeleteAccount from "./DeleteAccount";
import ProfileSection from "./ProfileSection";
import { PasswordConfirmField, PasswordConfirmProvider } from "./PasswordConfirm";
import { PRIMARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { AuthConfig, Me, errorText, loadMe } from "../lib/auth";
import { authTree, availableTabs, tabKey, tabOf } from "../lib/authTabs";
import { goTo } from "../lib/navigate";
import Button from "@sn/elements/Button";
import { TabPanel } from "@sn/compounds/SplitPanel";
import { tr } from "../i18n";

type State = { status: "loading" } | { status: "error"; text: string } | { status: "ready"; me: Me };

// The old anchors still work: they open the tab that holds the thing they pointed at.
const TAB_ALIASES: Record<string, string> = { "doi-mat-khau": tabKey("password"), "lien-ket-google": tabKey("google") };

const NOTHING_PENDING = tr("chua_co_thay_doi_nao_dien");

interface BodyProps {
  me: Me;
  config: AuthConfig;
  reload: () => Promise<void>;
}

/**
 * The tabs, then the account-wide blocks (sessions, the username with the password that confirms a change, delete) and the one
 * "Đổi tài khoản" button. Under the providers, so it can read the pending changes.
 */
function AccountBody({ me, config, reload }: BodyProps) {
  const [active, setActive] = useState(tabKey("password"));
  const [codes, setCodes] = useState<string[] | null>(null);
  const { pending, applyAll } = useAccountChanges();
  const batch = useAction();
  const [stopped, setStopped] = useState<string | null>(null);

  const tabs = availableTabs("account", config).map(tabKey);
  // The username form sits outside the tabs but is applied by the same button, after the tabs' changes.
  const order = [...tabs, "cach-profile", tabKey("username")];
  const waiting = order.filter((id) => id in pending);

  /** New recovery codes are shown once, in their own tab: go there. */
  function showCodes(next: string[] | null) {
    setCodes(next);
    if (next) setActive(tabKey("recovery"));
  }

  async function applyChanges() {
    setStopped(null);
    if (waiting.length === 0) return batch.fail(NOTHING_PENDING);
    await batch.run(async () => {
      const { applied, failed } = await applyAll(order);
      if (failed) {
        // The form shows its own error in its own tab: take the user there, and only point at it here.
        if (tabs.includes(failed)) setActive(failed);
        const before = applied.length > 0 ? tr("da_ap_dung_p0_thay_doi", { p0: applied.length }) : "";
        setStopped(tr("dung_o_p0_xem_thong_bao", { p0: pending[failed], before }));
        return;
      }
      return tr("da_ap_dung_p0_thay_doi_2", { p0: applied.length });
    });
  }

  const panels: Record<string, ReactNode> = {};
  for (const id of tabs) {
    panels[id] = <AccountTabContent tab={tabOf(id)} me={me} config={config} onDone={reload} codes={codes} onCodes={showCodes} />;
  }

  return (
    <>
      <TabPanel
        aria-label={tr("cai_dat_tai_khoan")}
        data={authTree("account", config)}
        panels={panels}
        activeKey={active}
        onChange={setActive}
        aliases={TAB_ALIASES}
      />

      <ProfileSection />
      <p className="text-sm"><a href="/user/cv" className="underline">{tr("cv_cua")}: {tr("cv_xem")}</a></p>
      <AccountTabContent tab="sessions" me={me} config={config} onDone={reload} codes={codes} onCodes={showCodes} />
      <ChangeUsername
        username={me.username}
        hasPassword={me.has_password}
        canRenameAfter={me.can_rename_after ?? null}
        onDone={reload}
        footer={me.has_password ? <PasswordConfirmField /> : undefined}
      />
      <DeleteAccount hasPassword={me.has_password} />

      <p className="text-sm text-line text-center">
        {waiting.length > 0 ? tr("thay_doi_dang_cho_p0", { p0: waiting.map((id) => pending[id]).join(", ") }) : NOTHING_PENDING}
      </p>
      <Button type="button" disabled={batch.busy} onClick={() => void applyChanges()} className={`${PRIMARY_BUTTON} mt-2`}>
        {batch.busy ? tr("dang_xu_ly") : tr("doi_tai_khoan")}
      </Button>
      <div className="text-center">
        <Alert className="mt-2">{batch.error}</Alert>
        <Alert tone="success" className="mt-2">{batch.message}</Alert>
        {stopped && <p role="status" className="text-sm">{stopped}</p>}
      </div>
    </>
  );
}

/** The "Đổi tài khoản" mode of the sign-in page: the signed-in user's methods, in the same tab layout, in place. */
export default function AccountMode({ config }: { config: AuthConfig }) {
  const [state, setState] = useState<State>({ status: "loading" });

  const reload = useCallback(async () => {
    try {
      const me = await loadMe();
      if (!me) return goTo("/user");
      setState({ status: "ready", me });
    } catch (caught) {
      setState({ status: "error", text: errorText(caught) });
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  if (state.status === "loading") return <p role="status" className="text-sm">{tr("dang_tai")}</p>;
  if (state.status === "error") {
    return (
      <>
        <Alert className="mt-2">{state.text}</Alert>
        <Button type="button" onClick={() => void reload()} className={`${PRIMARY_BUTTON} mt-2`}>
          {tr("thu_lai")}
        </Button>
      </>
    );
  }

  const { me } = state;
  return (
    <PasswordConfirmProvider>
      <AccountChangesProvider>
        {!config.email_enabled && <p className="text-sm text-line mb-2">Email: {me.email ?? tr("chua_co")}</p>}
        <AccountBody me={me} config={config} reload={reload} />
      </AccountChangesProvider>
    </PasswordConfirmProvider>
  );
}
