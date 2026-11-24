import type { CSSProperties, ElementType, HTMLAttributes } from "react";

import { BORDER, SURFACE } from "../lib/theme";

export interface CardProps extends HTMLAttributes<HTMLElement> {
  /** The element it is: a `div` unless the content is an article, a section, a list item, a form... */
  as?: "div" | "article" | "section" | "li" | "form" | "details" | "aside";
  /** Lay the children out in a column with a gap between them. */
  stack?: boolean;
}

const CARD_STYLE: CSSProperties = {
  border: `1px solid ${BORDER}`,
  borderRadius: 8,
  padding: 16,
  background: SURFACE,
};

/** A bordered panel on the surface color. It carries its own style, so it looks right without theme.css. */
export function Card({ as = "div", stack = false, style, children, ...rest }: CardProps) {
  const Tag = as as ElementType;
  const layout: CSSProperties = stack ? { display: "flex", flexDirection: "column", gap: 12 } : {};
  return (
    <Tag {...rest} style={{ ...CARD_STYLE, ...layout, ...style }}>
      {children}
    </Tag>
  );
}

export default Card;
