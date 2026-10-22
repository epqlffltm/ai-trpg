// web/apps/web/src/pages/trpg/room/TableRoom.tsx
// 테이블 방(B6)의 틀. 스트림을 붙잡고, 받은 것을 나눠 준다. 가운데는 테이블의 상태에 따라(모집 중, 진행 중, 끝남), 옆에는 앉은 사람과 채팅.
//
// 스트림에서 받은 것:
//   - 이벤트: 테이블을 묶어서 다시 읽는다(useBatchedRefetch). 이벤트로 값을 고치지 않는다
//   - 채팅: 읽어 둔 채팅에 번호 차례로 합친다. 그 사람의 "입력 중"을 지운다
//   - 입력 중: 5초 동안 보인다
//   - 멈춤: 끝났으면 테이블을 다시 읽고(끝난 판의 화면), 앉아 있지 않으면 다시 읽어 404 의 화면으로 간다
// 스트림이 열릴 때마다 테이블을 한 번 다시 읽는다. 처음 읽은 때와 붙은 때 사이, 끊겼던 동안의 변화를 놓치지 않게.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';
import type { ChatMessage, MessagePage, TableDetail } from '../../../api/types';
import { meQuery } from '../../../auth/queries';
import { usePublicNames } from '../../../hooks/usePublicNames';
import { ChatPanel } from './ChatPanel';
import { MemberList } from './MemberList';
import { RoomHeader } from './RoomHeader';
import { chatQuery, tableQuery } from './roomQueries';
import { mergeMessages } from './streamPolicy';
import { useBatchedRefetch } from './useBatchedRefetch';
import { useTableStream } from './useTableStream';
import { useTypingPeople } from './useTypingPeople';
import { RoomStage } from './RoomStage';

export function TableRoom({ table }: { table: TableDetail }) {
  const queryClient = useQueryClient();
  const chat = useQuery(chatQuery(table.id));
  const me = useQuery(meQuery());
  const typing = useTypingPeople();
  const refetchSoon = useBatchedRefetch(table.id);
  const messages = chat.data?.items ?? [];
  const nameOf = usePublicNames([table.members.map((member) => member.user_id), messages.map((message) => message.user_id)]);

  const appendChat = useCallback(
    (incoming: ChatMessage[]) => {
      queryClient.setQueryData<MessagePage>(chatQuery(table.id).queryKey, (current) =>
        current ? { ...current, items: mergeMessages(current.items, incoming) } : current,
      );
    },
    [queryClient, table.id],
  );

  const stream = useTableStream(table.id, chat.isSuccess ? chat.data.last_sequence : null, {
    onOpen: refetchSoon,
    onEvent: refetchSoon,
    onChat: (message) => {
      typing.remove(message.user_id);
      appendChat([message]);
    },
    onTyping: typing.add,
    onStop: () => void queryClient.invalidateQueries({ queryKey: tableQuery(table.id).queryKey }),
  });

  const myId = me.data?.public_id;
  return (
    <main className="page room">
      <RoomHeader table={table} stream={stream} />
      <div className="room__body">
        <div className="room__main">
          <RoomStage table={table} myId={myId} />
        </div>
        <div className="room__side">
          <MemberList members={table.members} myId={myId} nameOf={nameOf} />
          <ChatPanel
            table={table}
            chat={chat}
            members={table.members}
            nameOf={nameOf}
            typingIds={typing.userIds}
            onSent={(message) => appendChat([message])}
          />
        </div>
      </div>
    </main>
  );
}
