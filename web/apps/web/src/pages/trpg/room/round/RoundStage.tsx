// web/apps/web/src/pages/trpg/room/round/RoundStage.tsx
// 진행 중과 끝난 테이블의 가운데(B6 의 ③). 최근의 라운드들을 차례로 보이고, 맨 아래에 지금 라운드를 둔다.
// 더 앞의 라운드는 "앞의 라운드 더 보기"로 위에 잇는다(B10). 처음 누르면 그때의 첫 번호(anchor)에 최근의 라운드를 고정하고
// 그 앞을 쪽으로 읽는다. 고정하지 않으면 라운드가 늘 때 창이 밀려 사이가 빈다.
// 상태 패널(B7)은 옆에 있고(status/), 일어난 일은 그 탭이다(events/).
// 지금 라운드 바로 위에 서술을 막는 일의 알림을 둔다(events/RoomNotices).

import { Button, Notice } from '@ai-trpg/ui';
import { keepPreviousData, useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import type { TableDetail } from '../../../../api/types';
import { RoomNotices } from '../events/RoomNotices';
import { CurrentRound } from './CurrentRound';
import { EarlierRounds } from './EarlierRounds';
import type { NarrationPreview } from './preview';
import { RoundEntry } from './RoundEntry';
import { currentRoundQuery, earlierRoundsQuery, recentRoundsQuery } from './roundQueries';
import { hiddenBefore, mergeRounds, pastRounds } from './roundView';

type Props = {
  table: TableDetail;
  myId: string | undefined;
  preview: NarrationPreview | null;
  nameOfMember: (userId: string) => string;
};

export function RoundStage({ table, myId, preview, nameOfMember }: Props) {
  const [anchor, setAnchor] = useState<number | null>(null);
  const current = useQuery(currentRoundQuery(table.id));
  const recent = useQuery({ ...recentRoundsQuery(table.id, anchor), placeholderData: keepPreviousData });
  const earlier = useInfiniteQuery({ ...earlierRoundsQuery(table.id, anchor ?? 1), enabled: anchor !== null });

  if (current.isPending) return <p className="hint">라운드를 불러오는 중입니다.</p>;
  if (current.isError) {
    return (
      <Notice tone="error">
        라운드를 불러오지 못했습니다.{' '}
        <Button variant="quiet" onClick={() => void current.refetch()}>
          다시 시도
        </Button>
      </Notice>
    );
  }
  const earlierItems = anchor === null ? [] : (earlier.data?.pages.flatMap((page) => page.items) ?? []);
  const past = pastRounds(mergeRounds(earlierItems, recent.data?.items ?? []), current.data);
  const firstShown = past[0]?.number ?? current.data.number;

  function showEarlier() {
    if (anchor === null) setAnchor(firstShown);
    else if (earlier.isError && !earlier.data) void earlier.refetch();
    else void earlier.fetchNextPage();
  }

  return (
    <section className="story" aria-label="라운드">
      {table.status === 'ended' ? <Notice>끝난 테이블입니다. 채팅은 읽기만 할 수 있습니다.</Notice> : null}
      {recent.data ? <EarlierRounds hidden={hiddenBefore(firstShown)} busy={earlier.isFetching} failed={earlier.isError} onMore={showEarlier} /> : null}
      {recent.isError ? <p className="hint">지난 라운드를 불러오지 못했습니다.</p> : null}
      {past.map((round) => (
        <RoundEntry key={round.number} round={round} table={table} />
      ))}
      <RoomNotices table={table} currentRound={current.data.number} myId={myId} nameOfMember={nameOfMember} />
      <CurrentRound table={table} round={current.data} myId={myId} preview={preview} nameOfMember={nameOfMember} />
    </section>
  );
}
