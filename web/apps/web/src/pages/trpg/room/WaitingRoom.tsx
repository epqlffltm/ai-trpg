// web/apps/web/src/pages/trpg/room/WaitingRoom.tsx
// 모집 중인 테이블의 대기실. 방장은 초대 코드를 보고 나누며, 모두 캐릭터를 정하면 시작한다.
// 시작이 되면 서버가 테이블을 돌려준다. 그 값으로 바로 바꾸고, 다른 사람은 스트림의 이벤트(table_started)로 다시 읽는다.
// 캐릭터를 정하는 화면(B5)은 다음이다. 지금은 누가 정했는지만 보인다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { startTable } from '../../../api/tableRoom';
import type { TableDetail } from '../../../api/types';
import type { FormProblem } from '../../../auth/problem';
import { ProblemNotice } from '../../../components/ProblemNotice';
import { everyoneHasCharacter } from './MemberList';
import { tableQuery } from './roomQueries';
import { describeStartProblem } from './roomProblem';

export function WaitingRoom({ table, myId }: { table: TableDetail; myId: string | undefined }) {
  const isHost = table.members.some((member) => member.user_id === myId && member.is_host);
  const mine = table.members.find((member) => member.user_id === myId);
  return (
    <section className="waiting-room" aria-labelledby="waiting-heading">
      <h2 id="waiting-heading">모집 중</h2>
      {table.invite_code ? <InviteCode code={table.invite_code} /> : null}
      {mine && !mine.character ? (
        <Notice>캐릭터를 정해야 시작할 수 있습니다. 캐릭터를 정하는 화면은 준비 중입니다.</Notice>
      ) : null}
      <h3 className="waiting-room__label">시작하는 장면</h3>
      <p className="prose opening">{table.opening}</p>
      {isHost ? <StartButton table={table} /> : <p className="hint">모두 캐릭터를 정하면 방장이 시작합니다.</p>}
    </section>
  );
}

/** 방장에게만 오는 초대 코드. 눌러 복사한다(복사가 막힌 브라우저면 글을 고른다) */
function InviteCode({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <p className="invite-code">
      초대 코드 <code>{code}</code>
      <Button variant="quiet" onClick={() => void copy()}>
        {copied ? '복사했습니다' : '복사'}
      </Button>
    </p>
  );
}

function StartButton({ table }: { table: TableDetail }) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();
  const ready = everyoneHasCharacter(table.members);

  async function start() {
    setBusy(true);
    setProblem(undefined);
    try {
      queryClient.setQueryData(tableQuery(table.id).queryKey, await startTable(table.id));
    } catch (error) {
      setProblem(describeStartProblem(error));
    }
    setBusy(false);
  }

  return (
    <div className="start">
      <ProblemNotice problem={problem} />
      <Button busy={busy} disabled={!ready} onClick={start}>
        시작하기
      </Button>
      {ready ? null : <p className="hint">캐릭터를 정하지 않은 사람이 있습니다.</p>}
    </div>
  );
}
