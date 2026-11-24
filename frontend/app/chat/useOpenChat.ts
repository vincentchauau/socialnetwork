"use client";

import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

import { type Person, chatApi } from "./api";
import { socialError } from "./errors";

/** "Message": open the private chat with a person (made if there was none) and go to it in the chat. */
export function useOpenChat(): { message: (person: Person) => Promise<void>; error: string | null } {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const message = useCallback(
    async (person: Person) => {
      setError(null);
      try {
        const room = await chatApi.openDm(person.user_id);
        router.push(`/chat/#room=${encodeURIComponent(room.slug)}`);
      } catch (caught) {
        setError(socialError(caught));
      }
    },
    [router],
  );
  return { message, error };
}
