// web/apps/web/src/pages/trpg/room/round/RoundStage.tsx
// 진행 중과 끝난 테이블의 가운데(B6 의 ③). 최근의 라운드들을 차례로 보이고, 맨 아래에 지금 라운드를 둔다.
// 더 앞의 라운드는 지난 판 읽기(B10)가 보일 것이다. 상태 패널(B7)은 옆에 있고(status/), 일어난 일은 ④-2 다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import type { TableDetail } from '../../../../api/types';
import { CurrentRound } from './CurrentRound';
import type { NarrationPreview } from './preview';
import { RoundEntry } from './RoundEntry';
import { currentRoundQuery, recentRoundsQuery } from './roundQueries';
import { pastRounds } from './roundView';

type Props = {
  table: TableDetail;
  myId: string | undefined;
  preview: NarrationPreview | null;
  nameOfMember: (userId: string) => string;
};

export function RoundStage({ table, myId, preview, nameOfMember }: Props) {
  const current = useQuery(currentRoundQuery(table.id));
  const recent = useQuery(recentRoundsQuery(table.id));

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
  const past = pastRounds(recent.data?.items ?? [], current.data);
  return (
    <section className="story" aria-label="라운드">
      {table.status === 'ended' ? <Notice>끝난 테이블입니다. 채팅은 읽기만 할 수 있습니다.</Notice> : null}
      {recent.data && recent.data.total > recent.data.items.length ? (
        <p className="hint">앞의 라운드 {recent.data.total - recent.data.items.length}개는 아직 여기에 보이지 않습니다.</p>
      ) : null}
      {recent.isError ? <p className="hint">지난 라운드를 불러오지 못했습니다.</p> : null}
      {past.map((round) => (
        <RoundEntry key={round.number} round={round} rules={table.rules} />
      ))}
      <CurrentRound table={table} round={current.data} myId={myId} preview={preview} nameOfMember={nameOfMember} />
    </section>
  );
}
