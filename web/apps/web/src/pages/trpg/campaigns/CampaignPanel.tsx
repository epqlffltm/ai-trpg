// web/apps/web/src/pages/trpg/campaigns/CampaignPanel.tsx
// 테이블 방 옆의 캠페인(#481 B). 캠페인의 테이블이면 캠페인의 제목과 지금 편("2편: 지하 묘지 (2/3)")을 보인다.
// 모집 중에는 내가 넘겨받은 캐릭터를 한 줄로 보인다(시작하면 그 캐릭터의 시트를 받는다).
// 편이 끝나면 다음에 할 일: 방장은 다음 편을 열고(이 편의 정원으로), 다른 사람은 열기를 기다렸다가 들어간다. 마지막 편이면 마쳤다고 알린다.
// 캠페인의 테이블이 아니거나 읽지 못하면 아무것도 보이지 않는다(테이블 방은 캠페인 없이도 된다).

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import type { CampaignRun, TableDetail } from '../../../api/types';
import { ProblemNotice } from '../../../components/ProblemNotice';
import { tablePath } from '../tables/useEnterTable';
import { runOfTableQuery } from './runQueries';
import { carryLine, episodeLabel, episodeOfTable, nextStep, type NextStep } from './runView';
import { useJoinNext, useOpenNext } from './useRunActions';

type Props = { table: TableDetail; myId: string | undefined };

export function CampaignPanel({ table, myId }: Props) {
  const ended = table.status === 'ended';
  const query = useQuery(runOfTableQuery(table.id, ended));
  const run = query.data;
  if (!run) return null;
  const episode = episodeOfTable(run, table.id);
  if (!episode) return null;
  const step = nextStep(run, table.id, ended, myId);
  return (
    <section className="room-panel" aria-labelledby="campaign-panel-heading">
      <h2 id="campaign-panel-heading">캠페인 「{run.title}」</h2>
      <p>{episodeLabel(episode.position, episode.title, run.episodes.length)}</p>
      {table.status === 'recruiting' && run.my_carry ? (
        <p className="hint">넘겨받은 캐릭터: {carryLine(run.my_carry)}. 시작하면 이 캐릭터로 합니다.</p>
      ) : null}
      {step ? <Step run={run} step={step} capacity={table.capacity} /> : null}
    </section>
  );
}

function Step({ run, step, capacity }: { run: CampaignRun; step: NextStep; capacity: number }) {
  switch (step.kind) {
    case 'finished':
      return <Notice>캠페인을 마쳤습니다.</Notice>;
    case 'wait':
      return <p className="hint">방장이 다음 편을 열면 여기서 들어갈 수 있습니다.</p>;
    case 'open':
      return <OpenNext runId={run.id} capacity={capacity} />;
    case 'enter':
      return <EnterNext runId={run.id} tableId={step.tableId} />;
  }
}

function OpenNext({ runId, capacity }: { runId: string; capacity: number }) {
  const opening = useOpenNext(runId);
  return (
    <>
      <ProblemNotice problem={opening.problem} />
      <p className="hint">이 편과 같은 정원({capacity}명)으로 엽니다. 다른 설정은 열린 테이블에서 바꿀 수 있습니다.</p>
      <Button busy={opening.busy} onClick={() => void opening.open({ capacity })}>
        다음 편 열기
      </Button>
    </>
  );
}

function EnterNext({ runId, tableId }: { runId: string; tableId: string }) {
  const joining = useJoinNext(runId);
  return (
    <>
      <ProblemNotice problem={joining.problem} />
      <p className="hint">
        다음 편이 열렸습니다. 넘긴 캐릭터가 있으면 그 캐릭터로 앉습니다. 이미 앉았다면 <Link to={tablePath(tableId)}>다음 편으로</Link> 가세요.
      </p>
      <Button busy={joining.busy} onClick={() => void joining.join(tableId)}>
        다음 편에 들어가기
      </Button>
    </>
  );
}
