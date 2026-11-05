// web/apps/web/src/pages/trpg/room/RoomDock.tsx
// 좁은 화면의 테이블 방 맨 아래 단추 줄(Stitch 20번의 모바일). 창 넷(상태·장비, 소지품·돈, 퀘스트·지도, 일행·기록)과 "채팅".
// 누르면 그 내용이 아래에서 올라오는 시트로 열린다(시트는 TableRoom 의 왼쪽 열과 대화창을 CSS 가 띄운 것이다).
// 채팅 단추에는 대화창이 닫혀 있는 동안 온 새 말의 수를 띄운다. 넓은 화면에서는 CSS 가 숨긴다.
// 진행 중과 끝난 테이블에만 둔다(모집 중에는 창 넷이 없다).

import { STATUS_TABS } from './status/statusTabs';
import type { RoomDock as Dock } from './useRoomDock';

export function RoomDock({ dock }: { dock: Dock }) {
  return (
    <nav className="room-dock" aria-label="테이블 방의 단추 줄">
      {STATUS_TABS.map((entry) => {
        const open = dock.sheet === 'tools' && dock.statusOpen === entry.tab;
        return (
          <button
            key={entry.tab}
            type="button"
            className="room-dock__button"
            aria-expanded={open}
            onClick={() => (open ? dock.closeSheet() : dock.openTool(entry.tab))}
          >
            {entry.label}
          </button>
        );
      })}
      <button
        type="button"
        className="room-dock__button"
        aria-expanded={dock.sheet === 'chat'}
        aria-label={dock.unreadChat > 0 ? `채팅, 새 말 ${dock.unreadChat}개` : '채팅'}
        onClick={() => (dock.sheet === 'chat' ? dock.closeSheet() : dock.openChat())}
      >
        채팅
        {dock.unreadChat > 0 ? (
          <span className="room-talk__count" aria-hidden="true">
            {dock.unreadChat > 99 ? '99+' : dock.unreadChat}
          </span>
        ) : null}
      </button>
    </nav>
  );
}

/** 시트 맨 위의 닫기. 넓은 화면에서는 CSS 가 숨긴다 */
export function SheetClose({ onClose }: { onClose: () => void }) {
  return (
    <div className="room-sheet__head">
      <button type="button" className="room-sheet__close" onClick={onClose}>
        시트 닫기
      </button>
    </div>
  );
}
