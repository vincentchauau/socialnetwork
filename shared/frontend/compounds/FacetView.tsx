"use client";

import TreeView, { type TreeNode } from "./TreeView";

export interface Facet {
  name: string;
  count: number;
}

export interface FacetViewProps {
  /** Names the tree for people who cannot see it. */
  label: string;
  /** The text of the entry that clears the choice. */
  allLabel: string;
  facets: readonly Facet[];
  /** The chosen facet, "" for all. */
  value: string;
  onChange: (value: string) => void;
}

const ALL = "\u0000all";

/** The values of one filter with how many things each holds, as a tree to pick from (the categories of a shop, the tags of courses...). */
export default function FacetView({ label, allLabel, facets, value, onChange }: FacetViewProps) {
  const total = facets.reduce((sum, facet) => sum + facet.count, 0);
  const data: TreeNode[] = [
    { key: ALL, label: `${allLabel} (${total})`, icon: "apps" },
    ...facets.map((facet) => ({ key: facet.name, label: `${facet.name} (${facet.count})`, icon: "apps" })),
  ];
  return <TreeView data={data} aria-label={label} currentKey={value === "" ? ALL : value} onSelect={(key) => onChange(key === ALL ? "" : key)} alignLeaves />;
}
