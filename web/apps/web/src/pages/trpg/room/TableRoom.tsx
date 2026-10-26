// web/apps/web/src/pages/trpg/room/TableRoom.tsx
// 테이블 방(B6)의 틀. 스트림을 붙잡고, 받은 것을 나눠 준다. 가운데는 테이블의 상태에 따라(모집 중, 진행 중, 끝남),
// 옆에는 방장의 운영(방장에게만), 앉은 사람(모집 중) 또는 상태 패널(B7, 진행 중과 끝남), 채팅.
//
// 스트림에서 받은 것:
//   - 이벤트: 일어난 일에 더하고, 테이블과 라운드를 묶어서 다시 읽는다(useBatchedRefetch). 이벤트로 값을 고치지 않는다.
//     서술 값이 걸리거나 잡히거나 풀리는 일이면 머리의 잔액(A6)도 다시 읽는다(wallet/walletView.ts 의 WALLET_EVENTS)
//   - 채팅: 읽어 둔 채팅에 번호 차례로 합친다. 그 사람의 "입력 중"을 지운다
//   - 입력 중: 5초 동안 보인다
//   - 서술의 미리 보기: 조각을 이어 둔다(round/preview.ts). 서술이 끝났다는 이벤트가 오면 지운다
//   - 멈춤: 끝났으면 테이블을 다시 읽고(끝난 판의 화면), 앉아 있지 않으면 다시 읽어 404 의 화면으로 간다
// 스트림이 열릴 때마다 테이블을 한 번 다시 읽는다. 처음 읽은 때와 붙은 때 사이, 끊겼던 동안의 변화를 놓치지 않게.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';
import type { ChatMessage, EventPage, MessagePage, TableDetail, TableEvent } from '../../../api/types';
import { meQuery } from '../../../auth/queries';
import { usePublicNames } from '../../../hooks/usePublicNames';
import { ChatPanel } from './ChatPanel';
import { displayName, MemberList } from './MemberList';
import { FriendlyFirePanel } from './FriendlyFirePanel';
import { HostPanel } from './host/HostPanel';
import { RoomHeader } from './RoomHeader';
import { ActionRequestProvider } from './round/action/actionRequest';
import { applyPreview, ENDS_PREVIEW, type NarrationPreview } from './round/preview';
import { chatQuery, eventsQuery, tableQuery } from './roomQueries';
import { mergeEvents, mergeMessages } from './streamPolicy';
import { useBatchedRefetch } from './useBatchedRefetch';
import { useTableStream } from './useTableStream';
import { useTypingPeople } from './useTypingPeople';
import { WALLET_KEY } from '../../wallet/walletQueries';
import { changesWallet } from '../../wallet/walletView';
import { RoomStage } from './RoomStage';
import { MyHpStrip } from './status/MyHpStrip';
import { StatusPanel } from './status/StatusPanel';

export function TableRoom({ table }: { table: TableDetail }) {
  const queryClient = useQueryClient();
  const chat = useQuery(chatQuery(table.id));
  const events = useQuery(eventsQuery(table.id));
  const me = useQuery(meQuery());
  const typing = useTypingPeople();
  const refetchSoon = useBatchedRefetch(table.id);
  const [preview, setPreview] = useState<NarrationPreview | null>(null);
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

  const appendEvent = useCallback(
    (event: TableEvent) => {
      queryClient.setQueryData<EventPage>(eventsQuery(table.id).queryKey, (current) =>
        current ? { ...current, items: mergeEvents(current.items, [event]) } : current,
      );
    },
    [queryClient, table.id],
  );

  const start = chat.isSuccess && !events.isPending ? { messages: chat.data.last_sequence, events: events.data?.last_sequence ?? null } : null;
  const stream = useTableStream(table.id, start, {
    onOpen: refetchSoon,
    onEvent: (event: TableEvent) => {
      if (ENDS_PREVIEW.has(event.type)) setPreview(null);
      appendEvent(event);
      if (changesWallet(event.type)) void queryClient.invalidateQueries({ queryKey: WALLET_KEY });
      refetchSoon();
    },
    onChat: (message) => {
      typing.remove(message.user_id);
      appendChat([message]);
    },
    onTyping: typing.add,
    onPreview: (chunk) => setPreview((current) => applyPreview(current, chunk)),
    onStop: () => void queryClient.invalidateQueries({ queryKey: tableQuery(table.id).queryKey }),
  });

  const myId = me.data?.public_id;
  return (
    <ActionRequestProvider>
      <main className="page room">
        <RoomHeader table={table} stream={stream} />
        <div className="room__body">
          <div className="room__main">
            {table.status === 'playing' ? <MyHpStrip table={table} myId={myId} /> : null}
            <RoomStage
              table={table}
              myId={myId}
              preview={preview}
              nameOfMember={(userId) => displayName(userId, table.members, nameOf)}
            />
          </div>
          <div className="room__side">
            <HostPanel table={table} myId={myId} nameOfMember={(userId) => displayName(userId, table.members, nameOf)} />
            <FriendlyFirePanel
              table={table}
              myId={myId}
              nameOfMember={(userId) => displayName(userId, table.members, nameOf)}
            />
            {table.status === 'recruiting' ? (
              <MemberList members={table.members} myId={myId} nameOf={nameOf} />
            ) : (
              <StatusPanel table={table} myId={myId} nameOf={nameOf} />
            )}
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
    </ActionRequestProvider>
  );
}
