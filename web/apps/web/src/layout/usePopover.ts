// web/apps/web/src/layout/usePopover.ts
// 위쪽 줄의 펼침 창(알림, 프로필 메뉴) 하나의 열림. 단추로 열고 닫는다. 창 밖을 누르거나 Esc 를 누르면 닫힌다.
// 창과 단추를 감싼 요소(ref) 안을 누른 것은 밖이 아니다.

import { useCallback, useEffect, useRef, useState } from 'react';

export function usePopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    function onPointerDown(event: PointerEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false);
    }
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const toggle = useCallback(() => setOpen((before) => !before), []);
  const close = useCallback(() => setOpen(false), []);
  return { open, toggle, close, ref };
}
