import type { SVGAttributes } from "react";

const PATHS: Record<string, string> = {
  apps: "M4 4h6v6H4V4zm10 0h6v6h-6V4zM4 14h6v6H4v-6zm10 0h6v6h-6v-6z",
  users: "M12 12a4 4 0 100-8 4 4 0 000 8zm-7 8a7 7 0 0114 0H5z",
  home: "M3 11l9-8 9 8v9a1 1 0 01-1 1h-5v-6H9v6H4a1 1 0 01-1-1v-9z",
  admin: "M12 2l7 4v6c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V6l7-4z",
  gallery: "M4 5h16v14H4V5zm2 12l4-5 3 3 3-4 4 6H6z",
  chat: "M4 4h16v11H8l-4 4V4z",
  health: "M12 21s-7-4.6-9.5-9C.7 8.4 2 4.5 6 4a5 5 0 016 3 5 5 0 016-3c4 .5 5.3 4.4 3.5 8-2.5 4.4-9.5 9-9.5 9z",
  menu: "M4 7h16M4 12h16M4 17h16",
  close: "M6 6l12 12M18 6L6 18",
  folder: "M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z",
  file: "M6 3h8l5 5v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5a2 2 0 012-2zm8 0v5h5",
};

export const ICON_NAMES = Object.keys(PATHS);

export interface IconProps extends SVGAttributes<SVGSVGElement> {
  name: string;
  size?: number;
}

/** Stroke icon that takes its color from the surrounding text. Unknown names render nothing. */
export function Icon({ name, size = 16, ...rest }: IconProps) {
  const path = PATHS[name];
  if (!path) return null;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      <path d={path} />
    </svg>
  );
}

export default Icon;
