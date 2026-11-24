"use client";

import { FormEvent, useEffect, useState } from "react";

import { apiFetch } from "@sn/api";
import { FacetGridView } from "@sn/compounds/SplitPanel";
import FacetView, { type Facet } from "@sn/compounds/FacetView";
import { GridView } from "@sn/compounds/GalleryView";
import Button from "@sn/elements/Button";
import { usePagedList } from "@sn/lib/hooks";
import { Field, JobTile, Status } from "./components";
import { API, EMPLOYMENT_LABELS, EmploymentType, LIMITS, JobDescriptionPage, JobDescriptionSummary, errorText } from "./lib";
import { tr } from "./i18n";
import Select from "@sn/elements/Select";
import TextBox from "@sn/elements/TextBox";

interface Filters {
  q: string;
  location: string;
  remote: "" | "true" | "false";
  type: "" | EmploymentType;
  min_salary: string;
  tag: string;
  skill: string;
}

const EMPTY_FILTERS: Filters = { q: "", location: "", remote: "", type: "", min_salary: "", tag: "", skill: "" };
const PAGE_SIZE = 20;

function buildQuery(filters: Filters, cursor: string | null): string {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
  for (const [key, value] of Object.entries(filters)) {
    if (value.trim()) params.set(key, value.trim());
  }
  if (cursor) params.set("cursor", cursor);
  return params.toString();
}

interface Facets {
  types: Facet[];
  locations: Facet[];
}

export default function JobSearch() {
  const [form, setForm] = useState<Filters>(EMPTY_FILTERS);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [facets, setFacets] = useState<Facets>({ types: [], locations: [] });
  const list = usePagedList<JobDescriptionSummary, string>(
    (cursor) => apiFetch<JobDescriptionPage>(`${API}/jobs?${buildQuery(filters, cursor)}`),
    [filters],
    (failure) => errorText(failure, tr("could_not_load_jobs")),
  );

  useEffect(() => {
    apiFetch<Facets>(`${API}/facets`).then(setFacets, () => undefined); // the trees are a help, not worth an error
  }, []);

  // A course that teaches a skill links here with `?skill=`.
  useEffect(() => {
    const skill = new URLSearchParams(window.location.search).get("skill");
    if (skill) apply({ ...EMPTY_FILTERS, skill });
  }, []);

  function apply(next: Filters) {
    setForm(next);
    setFilters(next);
  }

  function update<K extends keyof Filters>(key: K, value: Filters[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    setFilters(form);
  }

  // The employment types are told by the person's words, not by the codes the server keeps.
  const types = facets.types.map((facet) => ({ ...facet, name: EMPLOYMENT_LABELS[facet.name as EmploymentType] ?? facet.name }));
  const codeOf = (label: string) => (Object.entries(EMPLOYMENT_LABELS).find(([, text]) => text === label)?.[0] ?? label) as Filters["type"];

  const filtersPane = (
    <div className="stack">
      <FacetView label={tr("type")} allLabel={tr("any")} facets={types} value={filters.type ? (EMPLOYMENT_LABELS[filters.type] ?? filters.type) : ""} onChange={(label) => apply({ ...form, type: label ? codeOf(label) : "" })} />
      <FacetView label={tr("location")} allLabel={tr("any")} facets={facets.locations} value={filters.location} onChange={(location) => apply({ ...form, location })} />
      <form className="stack" onSubmit={submit} role="search" aria-label={tr("search_jobs")}>
        <Field label={tr("keywords")}>
          <TextBox type="search" maxLength={LIMITS.query} value={form.q} onChange={(e) => update("q", e.target.value)} />
        </Field>
        <Field label={tr("work_mode")}>
          <Select value={form.remote} onChange={(e) => update("remote", e.target.value as Filters["remote"])}>
            <option value="">{tr("any")}</option>
            <option value="true">{tr("remote")}</option>
            <option value="false">{tr("on_site")}</option>
          </Select>
        </Field>
        <Field label={tr("minimum_salary")}>
          <TextBox type="number" min={0} inputMode="numeric" value={form.min_salary} onChange={(e) => update("min_salary", e.target.value)} />
        </Field>
        <Field label={tr("tag")}>
          <TextBox value={form.tag} maxLength={30} onChange={(e) => update("tag", e.target.value)} />
        </Field>
        <Field label={tr("skill")}>
          <TextBox value={form.skill} maxLength={60} onChange={(e) => update("skill", e.target.value)} />
        </Field>
        <div className="row wrap">
          <button type="submit" hidden aria-hidden="true" tabIndex={-1} />
          <Button variant="secondary" type="button" onClick={() => apply(EMPTY_FILTERS)}>{tr("reset")}</Button>
        </div>
      </form>
    </div>
  );

  return (
    <FacetGridView name="jobs" filtersLabel={tr("filters")} resultsLabel={tr("search_results")} filters={filtersPane}>
      <div className="stack">
        <Status loading={list.loading} error={list.error} empty={list.items.length === 0} emptyText={tr("no_jobs_match_your_search")} />
        {!list.loading && <GridView items={list.items} itemKey={(job) => job.id} renderItem={(job) => <JobTile job={job} />} label={tr("search_results")} minColumnWidth={320} gap={12} />}
        {!list.loading && list.hasMore && (
          <Button variant="secondary" onClick={list.loadMore} disabled={list.loadingMore}>
            {list.loadingMore ? tr("loading") : tr("load_more")}
          </Button>
        )}
      </div>
    </FacetGridView>
  );
}

