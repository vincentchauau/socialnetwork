import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { LocaleProvider, registerBundles, tr } from "@sn/lib/i18n";
import { LanguageSwitcher } from "@sn/compounds/SiteSettings";

import center from "../../app/center/locales.json";
import chat from "../../app/chat/locales.json";
import face from "../../app/face/locales.json";
import market from "../../app/market/locales.json";
import jobs from "../../app/job/locales.json";
import werewolf from "../../app/werewolf/locales.json"; // the Werewolf is a part of the chat now
import shared from "../../../shared/frontend/locales/locales.json";

const APPS: Record<string, { vi: Record<string, string>; en: Record<string, string> }> = { center, chat, face, werewolf, market, jobs };
const placeholders = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe.each(Object.entries(APPS))("locales of %s", (_name, bundle) => {
  it("has an English text for every Vietnamese one, and no other", () => {
    expect(Object.keys(bundle.en).sort()).toEqual(Object.keys(bundle.vi).sort());
  });

  it("keeps the same {placeholders} in both languages", () => {
    for (const key of Object.keys(bundle.vi)) expect(placeholders(bundle.en[key]), key).toEqual(placeholders(bundle.vi[key]));
  });

  it("has no empty text", () => {
    for (const [locale, texts] of Object.entries({ vi: bundle.vi, en: bundle.en })) {
      for (const [key, text] of Object.entries(texts)) expect(text.trim(), `${locale}.${key}`).not.toBe("");
    }
  });
});

describe("the shared locales", () => {
  const flat = (node: unknown, prefix = ""): string[] =>
    Object.entries(node as Record<string, unknown>).flatMap(([key, value]) => (typeof value === "string" ? [prefix + key] : flat(value, `${prefix}${key}.`)));

  it("have the same keys in vi and en", () => {
    expect(flat(shared.en).sort()).toEqual(flat(shared.vi).sort());
  });
});

describe("tr", () => {
  beforeEach(() => localStorage.clear());

  it("follows the language switcher, filling {placeholders}", () => {
    registerBundles({ vi: { hello_name: "Xin chào {name}" }, en: { hello_name: "Hello {name}" } });
    function Page() {
      return <p>{tr("hello_name", { name: "Ann" })}</p>;
    }
    render(
      <LocaleProvider>
        <LanguageSwitcher locales={["vi", "en"]} label="lang" />
        <Page />
      </LocaleProvider>,
    );
    expect(screen.getByText("Xin chào Ann")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "lang" }), { target: { value: "en" } });
    expect(screen.getByText("Hello Ann")).toBeInTheDocument();
  });

  it("falls back to Vietnamese, then to the key, for a text the language lacks", () => {
    registerBundles({ vi: { only_vi: "chỉ có tiếng Việt" }, en: {} });
    localStorage.setItem("sn_locale", "en");
    function Page() {
      return (
        <p>
          {tr("only_vi")}|{tr("nowhere")}
        </p>
      );
    }
    render(
      <LocaleProvider>
        <Page />
      </LocaleProvider>,
    );
    expect(screen.getByText("chỉ có tiếng Việt|nowhere")).toBeInTheDocument();
  });
});

describe("trServer: texts the server wrote in Vietnamese", () => {
  it("translates known texts and patterns, and leaves everything else alone", async () => {
    const { trServer, trServerDeep } = await import("@sn/lib/i18n");
    registerBundles({ server: { exact: { "Sói": "Wolf", "bị treo cổ": "hanged" }, patterns: [[String.raw`^📊 (.+) bị treo cổ \((\d+) phiếu\)$`, "📊 {1} was hanged ({2} votes)"]] } });
    localStorage.setItem("sn_locale", "en");
    function Page() {
      return <p>{trServer("📊 Linh bị treo cổ (3 phiếu)")}|{trServer("Sói")}|{trServer("không biết")}|{JSON.stringify(trServerDeep({ a: ["Sói", { b: "bị treo cổ" }] }))}</p>;
    }
    render(
      <LocaleProvider>
        <Page />
      </LocaleProvider>,
    );
    expect(await screen.findByText('📊 Linh was hanged (3 votes)|Wolf|không biết|{"a":["Wolf",{"b":"hanged"}]}')).toBeInTheDocument();
  });

  it("changes nothing in Vietnamese", async () => {
    const { trServer } = await import("@sn/lib/i18n");
    function Page() {
      return <p>{trServer("Sói")}</p>;
    }
    localStorage.clear();
    render(
      <LocaleProvider>
        <Page />
      </LocaleProvider>,
    );
    expect(screen.getByText("Sói")).toBeInTheDocument();
  });
});
