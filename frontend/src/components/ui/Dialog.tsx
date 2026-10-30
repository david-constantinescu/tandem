import * as RD from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { clsx } from "clsx";
import type { ReactNode } from "react";

export function Dialog({ open, onOpenChange, title, description, children, footer, wide }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: string; description?: ReactNode; children: ReactNode;
  footer?: ReactNode; wide?: boolean;
}) {
  return (
    <RD.Root open={open} onOpenChange={onOpenChange}>
      <RD.Portal>
        <RD.Overlay className="fixed inset-0 z-40 bg-ink-900/30 backdrop-blur-[2px]" />
        <RD.Content className={clsx(
          "fixed inset-x-0 bottom-0 z-50 max-h-[92vh] overflow-y-auto rounded-t-2xl bg-white p-5 shadow-[var(--shadow-lift)] sm:inset-auto sm:left-1/2 sm:top-1/2 sm:w-full sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl sm:p-6",
          wide ? "sm:max-w-2xl" : "sm:max-w-lg",
        )}>
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <RD.Title className="display text-xl text-ink-900">{title}</RD.Title>
              {description && <RD.Description className="mt-1 text-[14px] text-ink-500">{description}</RD.Description>}
            </div>
            <RD.Close className="rounded-lg p-1.5 text-ink-400 hover:bg-sand-100 hover:text-ink-700" aria-label="Close">
              <X className="h-4 w-4" />
            </RD.Close>
          </div>
          {children}
          {footer && <div className="mt-6 flex flex-wrap justify-end gap-2">{footer}</div>}
        </RD.Content>
      </RD.Portal>
    </RD.Root>
  );
}
