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
        <RD.Overlay className="fixed inset-0 z-40 bg-ink-900/35 backdrop-blur-[3px] data-[state=closed]:animate-[fade-out_.2s_ease-in] data-[state=open]:animate-[fade-in_.25s_ease-out]" />
        <RD.Content className={clsx(
          "safe-bottom fixed inset-x-0 bottom-0 z-50 max-h-[92dvh] overflow-y-auto overscroll-contain rounded-t-[28px] bg-white px-5 pt-2.5 shadow-[var(--shadow-float)]",
          "data-[state=open]:animate-[sheet-in_.42s_var(--ease-out-expo)] data-[state=closed]:animate-[sheet-out_.25s_ease-in]",
          "sm:inset-auto sm:bottom-auto sm:left-1/2 sm:top-1/2 sm:w-full sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-[24px] sm:p-6",
          "sm:data-[state=open]:animate-[pop-in_.22s_ease-out] sm:data-[state=closed]:animate-[fade-out_.15s_ease-in]",
          wide ? "sm:max-w-2xl" : "sm:max-w-lg",
        )}>
          <div className="mx-auto mb-3 h-[5px] w-10 rounded-full bg-sand-300 sm:hidden" aria-hidden />
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <RD.Title className="display text-xl text-ink-900">{title}</RD.Title>
              {description && <RD.Description className="mt-1 text-[14px] text-ink-500">{description}</RD.Description>}
            </div>
            <RD.Close className="-mr-1.5 flex h-11 w-11 items-center justify-center rounded-full text-ink-400 hover:bg-sand-100 hover:text-ink-700 active:scale-90" aria-label="Close">
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
