// web/apps/web/src/pages/trpg/room/round/CurrentRound.tsx
// 지금 라운드. 장면(GM 의 서술)을 보이고, 상태에 따라 아래가 다르다.
//   - 선언을 받는 중: 마감까지 남은 시간, 아직 내지 않은 사람, 내 선언, 방장의 닫기
//   - 결과를 서술하는 중: 모두의 선언과 판정 결과를 먼저 보이고, 쓰이는 서술을 미리 보인다. 실패하면 방장이 다시 맡긴다
//   - 끝난 테이블의 마지막 라운드: 선언과 결과만
// 다음 라운드가 열린 것은 스트림의 이벤트로 알고 다시 읽는다.

import type { Round, TableDetail } from '../../../../api/types';
import { formatRemaining } from '../../../../hooks/useCountdown';
import { useNow } from '../../../../hooks/useNow';
import { CloseRoundButton } from './CloseRoundButton';
import { DeclarationList } from './DeclarationList';
import { DeclarationPanel } from './DeclarationPanel';
import { NarrationPreviewText } from './NarrationPreviewText';
import type { NarrationPreview } from './preview';
import { remainingSeconds, roundStatusLabel } from './roundView';

type Props = {
  table: TableDetail;
  round: Round;
  myId: string | undefined;
  preview: NarrationPreview | null;
  nameOfMember: (userId: string) => string;
};

export function CurrentRound({ table, round, myId, preview, nameOfMember }: Props) {
  const playing = table.status === 'playing';
  const isHost = myId !== undefined && table.host_id === myId;
  return (
    <article className="round round--current" aria-labelledby="current-round">
      <h3 id="current-round" className="round__number">
        라운드 {round.number} <span className="hint">· {roundStatusLabel(round.status)}</span>
      </h3>
      <p className="prose scene">{round.scene}</p>
      {round.status === 'open' && playing ? (
        <>
          <RoundDeadline deadlineAt={round.deadline_at} />
          <WaitingFor ids={round.waiting_for} nameOfMember={nameOfMember} />
          <DeclarationPanel tableId={table.id} round={round} rules={table.rules} myId={myId} />
          {isHost ? <CloseRoundButton tableId={table.id} round={round} /> : null}
        </>
      ) : (
        <DeclarationList round={round} rules={table.rules} />
      )}
      {round.status === 'closing' && playing ? (
        <>
          <NarrationPreviewText round={round} preview={preview} />
          {isHost && round.narration_failed_at ? <CloseRoundButton tableId={table.id} round={round} /> : null}
        </>
      ) : null}
    </article>
  );
}

/** 마감까지 남은 시간. 마감이 없으면 보이지 않는다. 지나면 서버가 곧 닫는다 */
function RoundDeadline({ deadlineAt }: { deadlineAt: string | null }) {
  const now = useNow(1000, deadlineAt !== null);
  const left = remainingSeconds(deadlineAt, now);
  if (left === null) return null;
  return <p className="round__deadline">{left > 0 ? `마감까지 ${formatRemaining(left)}` : '마감 시각이 지났습니다. 곧 닫힙니다.'}</p>;
}

function WaitingFor({ ids, nameOfMember }: { ids: string[]; nameOfMember: (userId: string) => string }) {
  if (ids.length === 0) return null;
  return <p className="hint">아직 선언하지 않은 사람: {ids.map(nameOfMember).join(', ')}</p>;
}
