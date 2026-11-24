"use client";

import type { ComponentProps } from "react";

import { useAccountChanges } from "./AccountChanges";
import Button from "@sn/elements/Button";

/**
 * A form's own "apply" button. Under the account page it is not drawn: the page's one "Đổi tài khoản" button applies
 * every filled tab. A hidden default button stays, so Enter in a field still submits the form.
 */
export default function ApplyButton(props: ComponentProps<typeof Button>) {
  const { batched } = useAccountChanges();
  if (!batched) return <Button type="submit" {...props} />;
  return (
    <Button type="submit" aria-hidden="true" tabIndex={-1} disabled={props.disabled} className="sr-only">
      {props.children}
    </Button>
  );
}
