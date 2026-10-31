import type { ReactNode } from "react";

/** Links the assistant writes open in a new tab, and only web or mail links become clickable (no javascript:, data:…). */
export const MD = {
  a: ({ href, children }: { href?: string; children?: ReactNode }) => {
    const safe = href && /^(https?:|mailto:|\/(?!\/))/i.test(href) ? href : undefined;
    if (!safe) return <span>{children}</span>;
    const external = /^https?:/i.test(safe);
    return <a href={safe} {...(external ? { target: "_blank", rel: "noopener noreferrer nofollow" } : {})}>{children}</a>;
  },
  img: () => null, // never load images named by a model or a document (they could leak what's on screen)
};
