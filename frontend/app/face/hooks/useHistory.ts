"use client";

import { useCallback, useEffect, useState } from "react";

import { notifyRecordsChanged } from "@sn/lib/recordsChanged";

import { faceApi } from "../lib/api";
import { apiErrorMessage } from "../lib/errors";
import type { Measurement, Scores } from "../lib/types";

export type HistoryStatus = "loading" | "ready" | "error";

export interface HistoryState {
  items: Measurement[];
  status: HistoryStatus;
  /** Message for a failed list load. */
  loadError: string | null;
  /** Message for a failed save / delete. */
  actionError: string | null;
  isSaving: boolean;
  /** True after a successful save, until the next action. */
  justSaved: boolean;
  reload: () => Promise<void>;
  save: (scores: Scores) => Promise<void>;
  remove: (id: Measurement["id"]) => Promise<void>;
  annotate: (id: Measurement["id"], note: string) => Promise<void>;
  removeAll: () => Promise<void>;
}

export function useHistory(): HistoryState {
  const [items, setItems] = useState<Measurement[]>([]);
  const [status, setStatus] = useState<HistoryStatus>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [justSaved, setJustSaved] = useState(false);

  const reload = useCallback(async () => {
    setStatus("loading");
    setLoadError(null);
    try {
      setItems(await faceApi.list());
      setStatus("ready");
    } catch (e) {
      setLoadError(apiErrorMessage(e));
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  /** Runs a mutation, clearing the previous action feedback and mapping errors to Vietnamese. */
  const act = useCallback(async (run: () => Promise<void>) => {
    setActionError(null);
    setJustSaved(false);
    try {
      await run();
    } catch (e) {
      setActionError(apiErrorMessage(e));
    }
  }, []);

  const save = useCallback(async (scores: Scores) => {
    setIsSaving(true);
    await act(async () => {
      const saved = await faceApi.save(scores);
      setItems((prev) => [saved, ...prev.filter((m) => m.id !== saved.id)]);
      setJustSaved(true);
      notifyRecordsChanged("measurements");
    });
    setIsSaving(false);
  }, [act]);

  const remove = useCallback((id: Measurement["id"]) => act(async () => {
    await faceApi.remove(id);
    setItems((prev) => prev.filter((m) => m.id !== id));
  }), [act]);

  const annotate = useCallback((id: Measurement["id"], note: string) => act(async () => {
    const changed = await faceApi.annotate(id, note);
    setItems((prev) => prev.map((m) => (m.id === id ? changed : m)));
  }), [act]);

  const removeAll = useCallback(() => act(async () => {
    await faceApi.removeAll();
    setItems([]);
  }), [act]);

  return { items, status, loadError, actionError, isSaving, justSaved, reload, save, remove, annotate, removeAll };
}
