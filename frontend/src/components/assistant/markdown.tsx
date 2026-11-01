import type { ReactNode } from "react";

/** linkurile scrise de asistent se deschid in tab nou si doar cele web sau de mail se pot apasa (fara javascript:, data:...) */
export const MD = {
  a: ({ href, children }: { href?: string; children?: ReactNode }) => {
    const safe = href && /^(https?:|mailto:|\/(?!\/))/i.test(href) ? href : undefined;
    if (!safe) return <span>{children}</span>;
    const external = /^https?:/i.test(safe);
    return <a href={safe} {...(external ? { target: "_blank", rel: "noopener noreferrer nofollow" } : {})}>{children}</a>;
  },
  img: () => null, // nu incarcam niciodata imagini indicate de un model sau de un document (ar putea da afara ce e pe ecran)
};
