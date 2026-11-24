import { useTranslation, type Bundle } from "../lib/i18n";
import locales from "./locales.json";

/** Every text of the shared site chrome and the home page, per locale: see locales.json. */
const LOCALES: Record<string, Bundle> = locales;

/** `t("site.greeting")` in the language chosen with the language switcher. */
export function useT() {
  return useTranslation(LOCALES);
}
