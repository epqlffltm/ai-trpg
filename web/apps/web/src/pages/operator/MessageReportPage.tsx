// web/apps/web/src/pages/operator/MessageReportPage.tsx
// 대화 속 답의 신고 하나(E4, /operator/reports/messages/:reportId). 신고할 때 굳힌 답과 그 앞의 말을 본다.
//
// 보려면 까닭을 적는다. 서버는 볼 때마다 까닭과 함께 감사 기록(operator_reads)을 남긴다.
// 그래서 TanStack Query 로 읽지 않는다. 창을 다시 보거나 다시 붙을 때 저절로 다시 읽으면 기록이 쌓인다. 누를 때 한 번만 부른다.
// 처리는 신고 하나다. 캐릭터를 숨기는 것은 캐릭터의 신고(asset)에서 한다.

import { Button, Notice } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router';
import { decideMessageReport, readMessageReport } from '../../api/moderation';
import type { MessageReportDetail } from '../../api/types';
import { ProblemNotice } from '../../components/ProblemNotice';
import { formatDateTime } from '../../format/dateTime';
import { DecisionForm } from './DecisionForm';
import { outcomeLabel, reasonLabel, reasonProblem, speakerLabel } from './moderationPure';
import { ReasonField } from './ReasonField';
import { useModerationAction } from './useModerationAction';

export function MessageReportPage() {
  const { reportId = '' } = useParams();
  const [detail, setDetail] = useState<MessageReportDetail | null>(null);
  return (
    <main className="page page--medium">
      <p>
        <Link to="/operator/reports">신고 처리</Link>
      </p>
      <h1>대화 속 답의 신고</h1>
      {detail === null ? (
        <ReadGate reportId={reportId} onRead={setDetail} />
      ) : (
        <ReportView detail={detail} onHandled={setDetail} />
      )}
    </main>
  );
}

function ReadGate({ reportId, onRead }: { reportId: string; onRead: (detail: MessageReportDetail) => void }) {
  const reading = useModerationAction();
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | undefined>();

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found = reasonProblem(reason) ?? undefined;
    setError(found);
    if (found) return;
    const detail = await reading.run(() => readMessageReport(reportId, reason.trim()));
    if (detail) onRead(detail);
  }

  return (
    <form className="moderation-form" onSubmit={submit} noValidate>
      <p>사적인 대화의 글입니다. 보는 까닭을 적어야 열립니다. 열 때마다 감사 기록에 남습니다.</p>
      <ReasonField label="보는 까닭" value={reason} error={error} onChange={setReason} />
      <ProblemNotice problem={reading.problem} />
      <div className="actions">
        <Button type="submit" busy={reading.busy}>
          열기
        </Button>
      </div>
    </form>
  );
}

function ReportView({ detail, onHandled }: { detail: MessageReportDetail; onHandled: (next: MessageReportDetail) => void }) {
  const deciding = useModerationAction();
  return (
    <>
      <dl className="moderation-facts">
        <dt>사유</dt>
        <dd>{reasonLabel(detail.reason)}</dd>
        <dt>캐릭터</dt>
        <dd>
          {detail.character_name}({detail.character_version}번째 판, id {detail.character_id})
        </dd>
        <dt>모델</dt>
        <dd>{detail.model_slug ?? '모름'}</dd>
        <dt>신고한 때</dt>
        <dd>{formatDateTime(detail.created_at)}</dd>
        <dt>처리</dt>
        <dd>{outcomeLabel(detail.outcome)}</dd>
      </dl>
      {detail.description ? <p className="moderation-report__text">신고한 사람의 설명: {detail.description}</p> : null}
      <h2>앞의 말</h2>
      <ol className="plain-list moderation-context" aria-label="앞의 말">
        {detail.context.map((message, index) => (
          <li key={index}>
            <strong>{speakerLabel(message.role, detail.character_name)}</strong>
            <p className="moderation-report__text">{message.content}</p>
          </li>
        ))}
      </ol>
      <h2>신고된 답</h2>
      <blockquote className="moderation-quote">{detail.content}</blockquote>
      {detail.outcome === null ? (
        <DecisionForm
          actionedLabel="받아들임"
          dismissedLabel="기각"
          busy={deciding.busy}
          problem={deciding.problem}
          onDecide={async (input) => {
            const done = await deciding.run(() => decideMessageReport(detail.id, input));
            if (done === null) return false;
            onHandled({ ...detail, outcome: input.outcome, handled_at: new Date().toISOString() });
            return true;
          }}
        >
          <p className="hint">
            캐릭터를 숨기려면 <Link to="/operator/reports">캐릭터의 신고</Link>에서 숨깁니다. 신고한 사람에게는 처리했다는 것만
            알립니다.
          </p>
        </DecisionForm>
      ) : (
        <Notice tone="info">처리한 신고입니다.</Notice>
      )}
    </>
  );
}
