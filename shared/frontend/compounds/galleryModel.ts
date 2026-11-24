import { apiFetch } from "../api";
import registerBundles from "./gallery.locales.json";
import { registerScoped } from "../lib/i18n";
import type { Labels, Row, TableInfo } from "./crudModel";

export const galleryTr = registerScoped("gallery", registerBundles);

/** Which columns of the table a card shows and how the toolbar behaves. All column names come from `GET <api>/tables`. */
export interface GalleryConfig {
  /** The Columns menu lists every column of the table (the id, the title and the picture too). */
  allColumns?: boolean;
  /** The card leaves out its title and its picture (they are hidden from the Columns menu). */
  hideTitle?: boolean;
  hideImage?: boolean;
  title: string;
  subtitle?: string | string[];
  /** A status-like column drawn as a badge. */
  badge?: string;
  /** A media column: the thumbnail on top of the card. */
  image?: string;
  /** A long text column, clamped to 2 lines (not shown when it equals the title). */
  body?: string;
  /** Small columns (dates, counts, refs), written with the table's cell rules. */
  meta?: string[];
  /** Columns offered as filter chips; their values come from `GET <api>/<table>/suggest`. */
  filters?: string[];
  sort?: { column: string; label: string }[];
  pageSize?: number;
  cardMinWidth?: number;
  emptyText?: string;
  /** The column holding the owner of a row (e.g. `user_id`): admins get an "All users" switch and see the owner on each card. */
  ownerColumn?: string;
  /** When set, Add navigates here (client navigation) instead of opening the generic create form. */
  addHref?: string;
  addLabel?: string;
  /** When set, the title is editable in place; Enter saves `{values:{[renameColumn]: value}}` with PATCH `<api>/<table>/<pk>`, Escape cancels. */
  renameColumn?: string;
  /** Extra buttons on each card, before the generic Edit / Delete. */
  actions?: GalleryAction[];
  /** "media": the picture leads, the card keeps only the title and the buttons (no subtitle, body or facts). Default: the full card. */
  density?: "media";
  /** Cards in pages like a table (Previous / Next and a range), instead of a growing list. */
  paged?: boolean;
  /** Load the next page by itself when the end of the cards comes into view, instead of the "Load more" button. */
  infiniteScroll?: boolean;
  /** A yes/no fact in `meta` is shown only when it is no ("Is active" on every card says nothing; "Not active" does). */
  quietFlags?: boolean;
  /**
   * The grid as a person's own page and not as an editor: no Columns menu, boxes to pick cards appear only after "Select", and the texts below
   * (`searchPlaceholder`, `addLabel`) say what the things are in the words of the app.
   */
  friendly?: boolean;
  searchPlaceholder?: string;
  /** Plain cards for a person looking at their own rows: no selecting, no rows per page, no Columns menu. */
  simple?: boolean;
  /** Hide the generic Add button (the app brings its own create form through `createSlot`). */
  hideAdd?: boolean;
}

/** What an action may use when it runs. `reload` refreshes the page of cards. */
export interface GalleryActionContext {
  reload(): void;
  api: string;
  table: string;
}

/** One custom button of a card. A rejected `run` shows its message in the card (role=alert). */
export interface GalleryAction {
  key: string;
  label: string;
  icon?: string;
  run?: (row: Row, ctx: GalleryActionContext) => void | Promise<void>;
  /** A link instead of `run`: the button opens this address. */
  href?: (row: Row) => string;
  visible?: (row: Row) => boolean;
  kind?: "primary" | "secondary" | "danger";
  /** When set, a confirmation with this message comes before `run`. */
  confirm?: string;
}

export const DEFAULT_PAGE_SIZE = 20;
export const DEFAULT_CARD_MIN_WIDTH = 220;
export const SUGGEST_LIMIT = 20;

const cache = new Map<string, Promise<TableInfo[]>>();

/** Forgets the tables asked for so far (the tests change a table between two renders). */
export function resetGalleryTables(): void {
  cache.clear();
}

/** The tables of one api base, asked for once; a failure is an empty list (and is asked for again next time). */
export function loadGalleryTables(api: string): Promise<TableInfo[]> {
  const known = cache.get(api);
  if (known) return known;
  const pending = apiFetch<TableInfo[]>(`${api}/tables`)
    .then((tables) => (Array.isArray(tables) ? tables : []))
    .catch(() => {
      cache.delete(api);
      return [] as TableInfo[];
    });
  cache.set(api, pending);
  return pending;
}

/** The values a suggest answer holds: a list of texts, of {value}, or an object with `values` / `items` / `rows`. Anything else: none. */
export function suggestValues(answer: unknown): string[] {
  const list = Array.isArray(answer) ? answer : (answer as { values?: unknown; items?: unknown; rows?: unknown } | null)?.values ?? (answer as { items?: unknown })?.items ?? (answer as { rows?: unknown })?.rows;
  if (!Array.isArray(list)) return [];
  const out: string[] = [];
  for (const item of list) {
    const value = typeof item === "object" && item !== null ? (item as { value?: unknown }).value : item;
    if ((typeof value === "string" || typeof value === "number") && String(value) !== "") out.push(String(value));
  }
  return out;
}

/** The query of one page of cards. Sorting and filtering are sent as `sort` and `filter_<column>`. */
export function pageParams(opts: { search: string; offset: number; limit: number; sort: string; filters: Record<string, string> }): URLSearchParams {
  const params = new URLSearchParams({ q: opts.search, offset: String(opts.offset), limit: String(opts.limit) });
  if (opts.sort) params.set("sort", opts.sort);
  for (const [column, value] of Object.entries(opts.filters)) if (value) params.set(`filter_${column}`, value);
  return params;
}

/** The labels of an earlier page plus those of the next. */
export function mergeLabels(previous: Labels, next: Labels | undefined): Labels {
  const merged: Labels = { ...previous };
  for (const [column, texts] of Object.entries(next ?? {})) merged[column] = { ...merged[column], ...texts };
  return merged;
}

const TITLE_NAMES = ["title", "name", "caption", "username", "subject", "topic", "label"];
const BADGE_NAMES = ["status", "category", "kind", "type", "role", "level"];
const BODY_NAMES = ["description", "summary", "body", "content", "text", "prompt"];
const AUTO_META = 3;

/**
 * The cards of any table, worked out from its description alone (for a table nobody wrote a gallery for): a title column by its name, the first
 * picture column as the picture (the cards then lean on it), a status-like column as the badge, a long text as the body and a few facts.
 */
export function autoGalleryConfig(table: TableInfo): GalleryConfig {
  const open = table.columns.filter((column) => !column.secret && column.type !== "bytes" && column.type !== "json");
  const pick = (names: string[], used: Set<string>) => open.find((column) => !used.has(column.name) && names.includes(column.name.toLowerCase()))?.name;
  const used = new Set<string>();
  const take = (name: string | undefined) => {
    if (name) used.add(name);
    return name;
  };
  const image = take(table.columns.find((column) => column.media)?.name);
  const title = take(pick(TITLE_NAMES, used) ?? open.find((column) => !used.has(column.name) && (column.type === "string" || column.type === "text") && !table.pk.includes(column.name))?.name ?? table.pk[0] ?? open[0]?.name) ?? "id";
  const badge = take(pick(BADGE_NAMES, used));
  const body = take(open.find((column) => !used.has(column.name) && (column.type === "text" || BODY_NAMES.includes(column.name.toLowerCase())))?.name);
  const meta = image ? [] : open.filter((column) => !used.has(column.name) && !column.name.endsWith("_id")).slice(0, AUTO_META).map((column) => column.name);
  return { title, ...(image ? { image, density: "media" as const } : {}), ...(badge ? { badge } : {}), ...(body ? { body } : {}), meta, paged: true, cardMinWidth: image ? 180 : 260 };
}

export interface Placed {
  index: number;
  width: number;
  height: number;
}

const MIN_ASPECT = 0.5;
const MAX_ASPECT = 3;
const LAST_ROW_MIN_FILL = 0.6; // a last row this full is grown a little to fill the width ...
const LAST_ROW_MAX_GROW = 1.25; // ... but never taller than this many times the target, and a short one stays as it is

/**
 * Items of known proportions laid out in rows of one height, as a photo site does: every row is as wide as `width` (except the last, which keeps
 * the target height, or a little more when it is nearly full), and every item keeps its shape. `aspects` are width over height.
 */
export function justifiedRows(aspects: readonly number[], width: number, target: number, gap: number): Placed[][] {
  const rows: Placed[][] = [];
  let row: number[] = [];
  let sum = 0;
  const flush = (stretch: boolean) => {
    if (row.length === 0) return;
    const room = width - gap * (row.length - 1);
    const nearlyFull = sum * target + gap * (row.length - 1) >= width * LAST_ROW_MIN_FILL;
    const height = stretch ? room / sum : nearlyFull ? Math.min(room / sum, target * LAST_ROW_MAX_GROW) : target;
    rows.push(row.map((index) => ({ index, width: Math.max(1, Math.floor(clamp(aspects[index]) * height)), height: Math.round(height) })));
    row = [];
    sum = 0;
  };
  aspects.forEach((_, index) => {
    row.push(index);
    sum += clamp(aspects[index]);
    if (sum * target + gap * (row.length - 1) >= width) flush(true);
  });
  flush(false);
  return rows;
}

function clamp(aspect: number): number {
  const value = Number.isFinite(aspect) && aspect > 0 ? aspect : 1;
  return Math.min(MAX_ASPECT, Math.max(MIN_ASPECT, value));
}
