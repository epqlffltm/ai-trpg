// web/apps/web/src/pages/board/ReportButton.tsx
// 남의 글이나 댓글의 신고(A11). 누르면 창에서 사유(다섯 가운데 하나)와 설명(500자, 기타는 꼭)을 받는다.
// 접수하면 창에 "접수했습니다"를 남긴다. 누가 신고했는지는 운영자만 본다. 이미 신고했으면 서버의 409 문장("이미 신고했습니다.")을 보인다.

import { Button, Dialog, Notice, Radio } from '@ai-trpg/ui';
import { useMutation } from '@tanstack/react-query';
import { useCallback, useState, type FormEvent } from 'react';
import { reportBoardItem, type ReportTarget } from '../../api/board';
import type { BoardReportCreate } from '../../api/types';
import { ProblemNotice } from '../../components/ProblemNotice';
import { TextAreaField } from '../../components/TextAreaField';
import { EMPTY_REPORT, REPORT_DESCRIPTION_LIMIT, REPORT_REASONS, reportBody, reportDraftProblems, type ReportDraft } from './boardForm';
import { describeBoardWriteProblem } from './boardWriteProblem';

type Props = {
  target: ReportTarget;
  /** 단추에 읽히는 이름(무엇을 신고하는지) */
  ariaLabel: string;
};

export function ReportButton({ target, ariaLabel }: Props) {
  const [open, setOpen] = useState(false);
  const reporting = useMutation({ mutationFn: (body: BoardReportCreate) => reportBoardItem(target, body) });
  const close = useCallback(() => setOpen(false), []);

  function start() {
    reporting.reset();
    setOpen(true);
  }

  return (
    <>
      <Button variant="quiet" aria-label={ariaLabel} onClick={start}>
        신고
      </Button>
      <Dialog title={target.kind === 'post' ? '글 신고' : '댓글 신고'} open={open} onClose={close}>
        {reporting.isSuccess ? (
          <Notice tone="info">신고를 접수했습니다. 운영자가 살펴봅니다.</Notice>
        ) : (
          <ReportForm busy={reporting.isPending} error={reporting.error} onSubmit={(body) => reporting.mutate(body)} />
        )}
      </Dialog>
    </>
  );
}

type FormProps = { busy: boolean; error: Error | null; onSubmit: (body: BoardReportCreate) => void };

function ReportForm({ busy, error, onSubmit }: FormProps) {
  const [draft, setDraft] = useState<ReportDraft>(EMPTY_REPORT);
  const [touched, setTouched] = useState(false);
  const problems = reportDraftProblems(draft);
  const problem = error ? describeBoardWriteProblem(error, '신고') : undefined;

  function submit(event: FormEvent) {
    event.preventDefault();
    setTouched(true);
    const body = reportBody(draft);
    if (body && Object.keys(problems).length === 0) onSubmit(body);
  }

  return (
    <form onSubmit={submit} noValidate aria-label="신고">
      <ProblemNotice problem={problem} />
      <fieldset className="choice-list">
        <legend>사유</legend>
        {REPORT_REASONS.map((reason) => (
          <Radio
            key={reason.value}
            name="reason"
            label={reason.label}
            checked={draft.reason === reason.value}
            onChange={() => setDraft((current) => ({ ...current, reason: reason.value }))}
          />
        ))}
        {touched && problems.reason ? <p className="ui-field__error">{problems.reason}</p> : null}
      </fieldset>
      <TextAreaField
        label="설명"
        rows={4}
        maxLength={REPORT_DESCRIPTION_LIMIT}
        value={draft.description}
        onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))}
        error={(touched ? problems.description : undefined) ?? problem?.fields?.description}
        hint={`${draft.description.length} / ${REPORT_DESCRIPTION_LIMIT}자. 운영자만 봅니다.`}
      />
      <div className="actions">
        <Button type="submit" busy={busy}>
          신고하기
        </Button>
      </div>
    </form>
  );
}
