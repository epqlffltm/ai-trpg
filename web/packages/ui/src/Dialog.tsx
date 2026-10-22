// web/packages/ui/src/Dialog.tsx
// 화면 위에 띄우는 창 하나(문서 보기 같은 것). 열리면 닫기 단추에 초점을 두고, Esc 나 바깥을 누르면 닫는다.
// 무엇을 보일지는 쓰는 쪽이 children 으로 넘긴다.

import { useEffect, useId, useRef, type ReactNode } from 'react';
import { Button } from './Button';

export type DialogProps = {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
};

export function Dialog({ title, open, onClose, children }: DialogProps) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    closeRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => document.removeEventListener('keydown', closeOnEscape);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="ui-dialog__backdrop" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="ui-dialog"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="ui-dialog__head">
          <h2 id={titleId} className="ui-dialog__title">
            {title}
          </h2>
          <Button ref={closeRef} variant="quiet" onClick={onClose}>
            닫기
          </Button>
        </header>
        <div className="ui-dialog__body">{children}</div>
      </div>
    </div>
  );
}
