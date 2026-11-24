import { apiFetch, apiForm } from "@sn/api";

/** One call a form makes to a service, as the person, before it is sent to the chat (a file never goes through the chat). */
export interface UploadStep {
  path: string;
  kind: "json" | "multipart";
  /** The fields of the form this call sends. */
  fields: string[];
  /** What an earlier call returned and this one also sends (the id of the item the picture belongs to). */
  extra?: string[];
  /** What to keep of the answer: name -> the key of the answer. */
  capture: Record<string, string>;
}

export interface UploadSpec {
  steps: UploadStep[];
  /** The kept values the chat is told when the form is sent. */
  send: string[];
}

type Value = string | number | boolean | string[] | File;

/** Only a path of the gateway for a service: a card is written by a program and never trusted to point anywhere else. */
export const isServicePath = (path: string): boolean => /^\/api\/[A-Za-z0-9/_.-]+$/.test(path) && !path.includes(".") && !path.includes("//");

function addTo(form: FormData, name: string, value: Value | undefined): void {
  if (value === undefined || value === "") return;
  if (value instanceof File) form.append(name, value);
  else if (Array.isArray(value)) value.forEach((item) => form.append(name, item));
  else form.append(name, String(value));
}

/** Makes the calls of a form in order and returns the values to tell the chat. Throws what the service said when one fails. */
export async function runUpload(spec: UploadSpec, values: Record<string, Value>): Promise<Record<string, unknown>> {
  const kept: Record<string, unknown> = {};
  for (const step of spec.steps) {
    if (!isServicePath(step.path)) throw new Error("This form points somewhere it should not");
    let answer: Record<string, unknown> | undefined;
    if (step.kind === "json") {
      const body: Record<string, Value> = {};
      for (const name of step.fields) if (values[name] !== undefined) body[name] = values[name];
      answer = await apiFetch<Record<string, unknown>>(step.path, { method: "POST", body: JSON.stringify(body) });
    } else {
      const form = new FormData();
      for (const name of step.fields) addTo(form, name, values[name]);
      for (const name of step.extra ?? []) addTo(form, name, kept[name] as Value);
      answer = await apiForm<Record<string, unknown>>(step.path, form);
    }
    for (const [name, key] of Object.entries(step.capture)) kept[name] = answer?.[key];
  }
  return Object.fromEntries(spec.send.map((name) => [name, kept[name]]));
}
