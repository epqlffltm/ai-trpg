// web/apps/web/src/pages/trpg/room/useRoomDock.ts
// 테이블 방의 왼쪽 열 창 넷이 무엇을 펼쳤는지와, 좁은 화면의 아래 단추 줄(RoomDock)이 연 시트, 채팅 단추의 새 말 수.
// 넓은 화면에서는 시트가 보이지 않는다(CSS). 그래도 같은 상태를 쓴다. 창 넷의 펼침은 넓고 좁음과 상관없이 하나다.

import { useCallback, useState } from 'react';
import type { ChatMessage } from '../../../api/types';
import type { StatusTab } from './status/statusTabs';

/** 좁은 화면에서 아래에서 올라오는 시트. tools 는 왼쪽 열(창 넷과 그 아래 칸), chat 은 대화창 */
export type RoomSheet = 'tools' | 'chat';

export type RoomDock = {
  statusOpen: StatusTab | null;
  setStatusOpen: (next: StatusTab | null) => void;
  sheet: RoomSheet | null;
  /** 창 넷의 하나를 시트로 연다 */
  openTool: (tab: StatusTab) => void;
  openChat: () => void;
  closeSheet: () => void;
  unreadChat: number;
  /** 스트림으로 온 채팅을 센다(대화창 시트가 닫혀 있고 남이 쓴 것만) */
  countChat: (message: ChatMessage, myId: string | undefined) => void;
};

export function useRoomDock(): RoomDock {
  const [statusOpen, setStatusOpen] = useState<StatusTab | null>('mine');
  const [sheet, setSheet] = useState<RoomSheet | null>(null);
  const [unreadChat, setUnreadChat] = useState(0);

  const openTool = useCallback((tab: StatusTab) => {
    setStatusOpen(tab);
    setSheet('tools');
  }, []);
  const openChat = useCallback(() => {
    setSheet('chat');
    setUnreadChat(0);
  }, []);
  const closeSheet = useCallback(() => setSheet(null), []);
  const countChat = useCallback(
    (message: ChatMessage, myId: string | undefined) => setUnreadChat((count) => nextUnreadChat(count, message, myId, sheet === 'chat')),
    [sheet],
  );

  return { statusOpen, setStatusOpen, sheet, openTool, openChat, closeSheet, unreadChat, countChat };
}

/** 채팅 단추의 새 말 수. 대화창을 보고 있지 않을 때 남이 쓴 것만 센다 */
export function nextUnreadChat(current: number, message: ChatMessage, myId: string | undefined, viewing: boolean): number {
  if (viewing || myId === undefined || message.user_id === myId) return current;
  return current + 1;
}
