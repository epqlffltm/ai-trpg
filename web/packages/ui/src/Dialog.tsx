// web/packages/ui/src/Dialog.tsx
// 화면 위에 띄우는 창 하나(문서 보기 같은 것). 열리면 닫기 단추에 초점을 두고, Esc 나 바깥을 누르면 닫는다.
// 무엇을 보일지는 쓰는 쪽이 children 으로 넘긴다.
// 창 위에 창이 또 뜨면(청약철회를 묻는 창 위의 본인 확인 창 같은 것) Esc 는 맨 위의 창만 닫는다. 나중에 그린 창이 위에 있다.

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
  const backdropRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    closeRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && isTopmost(backdropRef.current)) onClose();
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => document.removeEventListener('keydown', closeOnEscape);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div ref={backdropRef} className="ui-dialog__backdrop" onClick={onClose}>
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

/** 떠 있는 창 가운데 맨 위(문서에서 마지막)의 것인가 */
function isTopmost(backdrop: HTMLDivElement | null): boolean {
  if (backdrop === null) return false;
  const backdrops = document.querySelectorAll('.ui-dialog__backdrop');
  return backdrops[backdrops.length - 1] === backdrop;
}
