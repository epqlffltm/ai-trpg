// web/apps/web/src/components/ToolDock.tsx
// 좁은 화면의 대화형 플레이 화면(chat 대화, story 장면) 맨 아래 단추 줄(Stitch 21·22번의 모바일). 왼쪽 열 창의 단추들.
// 누르면 그 창이 펼쳐진 채로 왼쪽 열이 아래에서 올라오는 시트로 열린다(CSS 가 띄운다). 같은 단추를 다시 누르면 닫는다.
// 모양은 테이블 방의 단추 줄(room-dock)과 같다. 넓은 화면에서는 CSS 가 숨긴다.

import { useCallback, useState } from 'react';

export type ToolDockState<T extends string> = {
  open: T | null;
  setOpen: (next: T | null) => void;
  sheet: boolean;
  /** 창 하나를 시트로 연다 */
  openTool: (tool: T) => void;
  closeSheet: () => void;
};

/** 펼친 창과 시트. 처음에는 first(맨 앞의 창)가 펼쳐져 있고 시트는 닫혀 있다 */
export function useToolDock<T extends string>(first: T | null): ToolDockState<T> {
  const [open, setOpen] = useState<T | null>(first);
  const [sheet, setSheet] = useState(false);
  const openTool = useCallback((tool: T) => {
    setOpen(tool);
    setSheet(true);
  }, []);
  const closeSheet = useCallback(() => setSheet(false), []);
  return { open, setOpen, sheet, openTool, closeSheet };
}

type Props<T extends string> = {
  /** 단추 줄의 이름(읽히는 이름) */
  label: string;
  tools: { id: T; label: string }[];
  dock: ToolDockState<T>;
};

export function ToolDock<T extends string>({ label, tools, dock }: Props<T>) {
  return (
    <nav className="room-dock" aria-label={label}>
      {tools.map((tool) => {
        const open = dock.sheet && dock.open === tool.id;
        return (
          <button
            key={tool.id}
            type="button"
            className="room-dock__button"
            aria-expanded={open}
            onClick={() => (open ? dock.closeSheet() : dock.openTool(tool.id))}
          >
            {tool.label}
          </button>
        );
      })}
    </nav>
  );
}
