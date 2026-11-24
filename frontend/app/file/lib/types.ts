export interface Entry {
  name: string;
  type: "folder" | "file";
  size: number;
  modifiedAt: string;
}

export interface Listing {
  path: string;
  entries: Entry[];
  /** How many there are in the folder (the list can be cut short). */
  total?: number;
  usage: { usedBytes: number; quotaBytes: number };
}

/** An item of the trash: what was deleted, where it was and when. */
export interface TrashEntry {
  id: string;
  name: string;
  parent: string;
  type: "file" | "folder";
  size: number;
  deletedAt: number;
}

/** A link that gives one file to anybody who has it. */
export interface ShareEntry {
  token: string;
  path: string;
  page: string;
  size?: number;
  createdAt: number;
  expiresAt: number | null;
}

/** A file or folder found by its name, with the folder it is in. */
export interface FoundEntry {
  name: string;
  parent: string;
  type: "file" | "folder";
  size: number;
}

/** An earlier version of a file: what it was before it was replaced. */
export interface VersionEntry {
  id: string;
  size: number;
  savedAt: number;
}
