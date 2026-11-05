// web/apps/web/src/pages/chat/conversation/ChatDock.tsx
// 좁은 화면의 chat 대화 맨 아래 단추 줄(Stitch 21번의 모바일). 왼쪽 열의 창(지도·이동, 소지품·건네기, 상대의 차림·기억, 페르소나·모델)의 단추.
// 누르면 그 창이 펼쳐진 채로 왼쪽 열이 아래에서 올라오는 시트로 열린다(CSS 가 띄운다). 같은 단추를 다시 누르면 닫는다.
// 말 쓰기는 늘 보이므로 채팅 단추는 없다. 모양은 테이블 방의 단추 줄(room-dock)과 같다. 넓은 화면에서는 CSS 가 숨긴다.

import { useCallback, useState } from 'react';
import { chatToolLabel, type ChatTool } from './ChatTools';

export type ChatDockState = {
  open: ChatTool | null;
  setOpen: (next: ChatTool | null) => void;
  sheet: boolean;
  /** 창 하나를 시트로 연다 */
  openTool: (tool: ChatTool) => void;
  closeSheet: () => void;
};

/** 펼친 창과 시트. 처음에는 first(맨 앞의 창)가 펼쳐져 있고 시트는 닫혀 있다 */
export function useChatDock(first: ChatTool | null): ChatDockState {
  const [open, setOpen] = useState<ChatTool | null>(first);
  const [sheet, setSheet] = useState(false);
  const openTool = useCallback((tool: ChatTool) => {
    setOpen(tool);
    setSheet(true);
  }, []);
  const closeSheet = useCallback(() => setSheet(false), []);
  return { open, setOpen, sheet, openTool, closeSheet };
}

export function ChatDock({ tools, dock }: { tools: ChatTool[]; dock: ChatDockState }) {
  return (
    <nav className="room-dock" aria-label="대화의 단추 줄">
      {tools.map((tool) => {
        const open = dock.sheet && dock.open === tool;
        return (
          <button
            key={tool}
            type="button"
            className="room-dock__button"
            aria-expanded={open}
            onClick={() => (open ? dock.closeSheet() : dock.openTool(tool))}
          >
            {chatToolLabel(tool)}
          </button>
        );
      })}
    </nav>
  );
}
