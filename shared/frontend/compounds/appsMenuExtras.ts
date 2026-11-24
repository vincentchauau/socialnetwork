import { createContext } from "react";

/** One entry under an app in the Apps menu (a table the page lets the person pick). */
export interface AppsMenuItem {
  key: string;
  label: string;
  current: boolean;
  onSelect: () => void;
}

/** What a page adds to the Apps menu: for an app (`key` is its path name, e.g. "photo"), the things inside it to pick. */
export interface AppsMenuGroup {
  key: string;
  items: AppsMenuItem[];
  /** The app itself can be chosen (it may have no table): pressing its name does this instead of going to its page. */
  onSelectApp?: () => void;
  current?: boolean;
}

/** Null where the page adds nothing: the menu is then the plain list of apps. */
export const AppsMenuExtras = createContext<AppsMenuGroup[] | null>(null);
