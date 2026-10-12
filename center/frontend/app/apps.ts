export interface AppLink {
  name: string;
  href: string;
  description: string;
}

/** Every app mounted behind the gateway. Add an entry here when a new app ships. */
export const APPS: readonly AppLink[] = [
  { name: "Chat", href: "/chat", description: "Talk in rooms in real time" },
];
