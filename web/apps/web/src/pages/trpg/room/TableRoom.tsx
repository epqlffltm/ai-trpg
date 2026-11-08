// web/apps/web/src/pages/trpg/room/TableRoom.tsx
// 테이블 방(B6)의 틀. 스트림을 붙잡고, 받은 것을 나눠 준다. 배치는 Stitch 20번을 따른다(넓은 화면).
//   - 가운데(가장 넓게): 테이블의 상태에 따라(모집 중, 진행 중, 끝남) 대기실이나 라운드
//   - 머리(테이블 줄) 바로 아래: 방장이 "테이블 관리"를 펼쳤을 때 방장의 운영(host/HostPanel)
//   - 왼쪽 열: 앉은 사람(모집 중) 또는 창 넷(B7, 진행 중과 끝남), 그 아래 캠페인의 편(캠페인의 테이블에만, #481 B), 동료 피해
//   - 맨 아래(가로로 긴 칸): 대화창. 탭 둘 "채팅"(판 채팅)과 "쪽지"(내 쪽지함, 안 읽은 수)
// 좁은 화면에서는 가운데가 화면을 채운다. 진행 중과 끝난 테이블은 맨 아래 단추 줄(RoomDock)로 왼쪽 열과 대화창을
// 아래에서 올라오는 시트로 연다(useRoomDock). 모집 중에는 가운데, 왼쪽 열, 채팅의 차례로 위아래다.
// 차례와 시트는 CSS 가 정하고 문서의 차례는 가운데가 먼저다.
//
// 스트림에서 받은 것:
//   - 이벤트: 일어난 일에 더하고, 테이블과 라운드를 묶어서 다시 읽는다(useBatchedRefetch). 이벤트로 값을 고치지 않는다.
//     서술 값이 걸리거나 잡히거나 풀리는 일이면 머리의 잔액(A6)도 다시 읽는다(wallet/walletView.ts 의 WALLET_EVENTS)
//   - 채팅: 읽어 둔 채팅에 번호 차례로 합친다. 그 사람의 "입력 중"을 지운다
//   - 쪽지: 읽어 둔 쪽지함에 번호 차례로 합친다. 쪽지 탭을 보고 있지 않으면 나에게 온 것을 안 읽은 수로 센다
//   - 입력 중: 5초 동안 보인다
//   - 서술의 미리 보기: 조각을 이어 둔다(round/preview.ts). 서술이 끝났다는 이벤트가 오면 지운다
//   - 장면 그림이 바뀜(scene_snapshot, #983): 그림 목록을 다시 읽는다(snapshots/)
//   - 멈춤: 끝났으면 테이블을 다시 읽고(끝난 판의 화면), 앉아 있지 않으면 다시 읽어 404 의 화면으로 간다
// 스트림이 열릴 때마다 테이블을 한 번 다시 읽는다. 처음 읽은 때와 붙은 때 사이, 끊겼던 동안의 변화를 놓치지 않게.
// 장르 테마(Stitch 23~33번): main 에 data-genre 를 단다. 장르는 시나리오의 소개에서 읽는다(useTableGenre).

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';
import type { ChatMessage, EventPage, MessagePage, TableDetail, TableEvent, Whisper, WhisperPage } from '../../../api/types';
import { meQuery } from '../../../auth/queries';
import { CampaignPanel } from '../campaigns/CampaignPanel';
import { usePublicNames } from '../../../hooks/usePublicNames';
import { ChatPanel } from './ChatPanel';
import { displayName, MemberList } from './MemberList';
import { FriendlyFirePanel } from './FriendlyFirePanel';
import { canManageTable, HostPanel } from './host/HostPanel';
import { SheetClose } from '../../../components/SheetClose';
import { RoomDock } from './RoomDock';
import { RoomHeader } from './RoomHeader';
import { RoomTalk, type TalkTab } from './RoomTalk';
import { ActionRequestProvider } from './round/action/actionRequest';
import { applyPreview, ENDS_PREVIEW, type NarrationPreview } from './round/preview';
import { tableSnapshotsKey } from './snapshots/useTableSnapshots';
import { chatQuery, eventsQuery, tableQuery, whispersQuery } from './roomQueries';
import { mergeEvents, mergeMessages, mergeWhispers, nextUnreadWhispers } from './streamPolicy';
import { useBatchedRefetch } from './useBatchedRefetch';
import { useRoomDock } from './useRoomDock';
import { useTableStream } from './useTableStream';
import { useTableGenre } from './useTableGenre';
import { useTypingPeople } from './useTypingPeople';
import { WALLET_KEY } from '../../wallet/walletQueries';
import { changesWallet } from '../../wallet/walletView';
import { RoomStage } from './RoomStage';
import { MyHpStrip } from './status/MyHpStrip';
import { StatusPanel } from './status/StatusPanel';
import { WhisperPanel } from './WhisperPanel';
import { DicePanel } from './DicePanel';

export function TableRoom({ table }: { table: TableDetail }) {
  const queryClient = useQueryClient();
  const chat = useQuery(chatQuery(table.id));
  const events = useQuery(eventsQuery(table.id));
  const whispers = useQuery(whispersQuery(table.id));
  const me = useQuery(meQuery());
  const typing = useTypingPeople();
  const genre = useTableGenre(table.scenario_id);
  const refetchSoon = useBatchedRefetch(table.id);
  const [preview, setPreview] = useState<NarrationPreview | null>(null);
  const [managing, setManaging] = useState(false);
  const [talkTab, setTalkTab] = useState<TalkTab>('chat');
  const [unreadWhispers, setUnreadWhispers] = useState(0);
  const dock = useRoomDock();
  const docked = table.status !== 'recruiting';
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

  const appendWhisper = useCallback(
    (incoming: Whisper[]) => {
      queryClient.setQueryData<WhisperPage>(whispersQuery(table.id).queryKey, (current) =>
        current ? { ...current, items: mergeWhispers(current.items, incoming) } : current,
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

  const myId = me.data?.public_id;
  const start =
    chat.isSuccess && !events.isPending && !whispers.isPending
      ? { messages: chat.data.last_sequence, events: events.data?.last_sequence ?? null, whispers: whispers.data?.last_sequence ?? null }
      : null;
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
      dock.countChat(message, myId);
    },
    onWhisper: (whisper) => {
      appendWhisper([whisper]);
      setUnreadWhispers((count) => nextUnreadWhispers(count, whisper, myId, talkTab === 'whisper'));
    },
    onTyping: typing.add,
    onPreview: (chunk) => setPreview((current) => applyPreview(current, chunk)),
    onSnapshot: () => void queryClient.invalidateQueries({ queryKey: tableSnapshotsKey(table.id) }),
    onStop: () => void queryClient.invalidateQueries({ queryKey: tableQuery(table.id).queryKey }),
  });

  function chooseTalkTab(tab: TalkTab) {
    setTalkTab(tab);
    if (tab === 'whisper') setUnreadWhispers(0);
  }

  return (
    <ActionRequestProvider>
      <main className={docked ? 'page room room--docked' : 'page room'} data-sheet={dock.sheet ?? undefined} data-genre={genre}>
        <RoomHeader
          table={table}
          stream={stream}
          manage={canManageTable(table, myId) ? { open: managing, toggle: () => setManaging((open) => !open) } : null}
        />
        {managing ? <HostPanel table={table} myId={myId} nameOfMember={(userId) => displayName(userId, table.members, nameOf)} /> : null}
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
            {docked ? <SheetClose onClose={dock.closeSheet} /> : null}
            {table.status === 'recruiting' ? (
              <MemberList members={table.members} myId={myId} nameOf={nameOf} />
            ) : (
              <StatusPanel table={table} myId={myId} nameOf={nameOf} open={dock.statusOpen} onOpenChange={dock.setStatusOpen} />
            )}
            <CampaignPanel table={table} myId={myId} />
            <FriendlyFirePanel
              table={table}
              myId={myId}
              nameOfMember={(userId) => displayName(userId, table.members, nameOf)}
            />
          </div>
          <div className="room__chat">
            {docked ? <SheetClose onClose={dock.closeSheet} /> : null}
            <RoomTalk
              tab={talkTab}
              onTab={chooseTalkTab}
              unreadWhispers={unreadWhispers}
              chat={
                <ChatPanel
                  table={table}
                  chat={chat}
                  members={table.members}
                  nameOf={nameOf}
                  typingIds={typing.userIds}
                  onSent={(message) => appendChat([message])}
                />
              }
              whisper={
                <WhisperPanel table={table} whispers={whispers} myId={myId} nameOf={nameOf} onSent={(whisper) => appendWhisper([whisper])} />
              }
              dice={
                <DicePanel table={table} events={events} myId={myId} nameOfMember={(userId) => displayName(userId, table.members, nameOf)} />
              }
            />
          </div>
        </div>
        {docked ? <RoomDock dock={dock} /> : null}
      </main>
    </ActionRequestProvider>
  );
}
