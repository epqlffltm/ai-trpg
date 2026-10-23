// web/apps/web/src/pages/operator/CharacterReportDetail.tsx
// 한 캐릭터의 신고 전부(처리한 것까지)와 처리, 숨기기. 신고한 사람은 서버가 싣지 않는다.
// 처리는 그 캐릭터의 열린 신고를 한꺼번에 한다. 받아들이면 숨긴다. 신고한 사람에게는 처리했다는 것만 알린다(결과는 싣지 않는다).

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { decideCharacterReports, setCharacterHidden } from '../../api/moderation';
import type { CharacterReport } from '../../api/types';
import { formatDateTime } from '../../format/dateTime';
import { DecisionForm } from './DecisionForm';
import { HiddenForm } from './HiddenForm';
import { outcomeLabel, reasonLabel } from './moderationPure';
import { characterReportsQuery } from './moderationQueries';
import { useModerationAction } from './useModerationAction';

type Props = { characterId: string; hidden: boolean };

export function CharacterReportDetail({ characterId, hidden }: Props) {
  const query = useQuery(characterReportsQuery(characterId));
  const deciding = useModerationAction();
  const hiding = useModerationAction();
  const [isHidden, setIsHidden] = useState(hidden);

  if (query.isPending) return <p aria-busy="true">불러오는 중</p>;
  if (query.isError) {
    return (
      <Notice tone="error">
        신고를 불러오지 못했습니다.{' '}
        <Button variant="quiet" onClick={() => void query.refetch()}>
          다시 시도
        </Button>
      </Notice>
    );
  }
  return (
    <div className="moderation-detail">
      <p className="hint">캐릭터 id {characterId}</p>
      <ol className="plain-list" aria-label="이 캐릭터의 신고">
        {query.data.map((report) => (
          <ReportLine key={report.id} report={report} />
        ))}
      </ol>
      <DecisionForm
        actionedLabel="받아들이고 숨기기"
        dismissedLabel="기각하고 그대로 두기"
        busy={deciding.busy}
        problem={deciding.problem}
        onDecide={async (input) => {
          const result = await deciding.run(() => decideCharacterReports(characterId, input));
          if (result) setIsHidden(result.hidden);
          return result !== null;
        }}
      >
        <p className="hint">열린 신고를 모두 한꺼번에 처리합니다. 신고한 사람에게는 처리했다는 것만 알립니다.</p>
      </DecisionForm>
      <HiddenForm
        hidden={isHidden}
        busy={hiding.busy}
        problem={hiding.problem}
        onChange={async (input) => {
          const result = await hiding.run(() => setCharacterHidden(characterId, input));
          if (result) setIsHidden(result.hidden);
          return result !== null;
        }}
      />
    </div>
  );
}

function ReportLine({ report }: { report: CharacterReport }) {
  return (
    <li className="moderation-report">
      <p>
        <strong>{reasonLabel(report.reason)}</strong> · {report.version}번째 판 · {outcomeLabel(report.outcome)}
      </p>
      {report.description ? <p className="moderation-report__text">{report.description}</p> : null}
      <p className="hint">{formatDateTime(report.created_at)}</p>
    </li>
  );
}
