// web/apps/web/src/pages/operator/inquiries/InquiryDetail.tsx
// 열린 문의 하나. 처음 열면 서버가 읽음으로 적는다(그래서 열고 나면 목록과 수를 다시 읽는다).
// 보낸 사람과 주소, 내용, 누가 처음 열었는지, 답(누가 답했는지, 답 메일이 어떻게 됐는지) 또는 답 쓰기, 지우기.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, type FormEvent } from 'react';
import { deleteInquiry, replyToInquiry, type AdminInquiry } from '../../../api/inquiryAdmin';
import type { FormProblem } from '../../../auth/problem';
import { ConfirmButton } from '../../../components/ConfirmButton';
import { TextAreaField } from '../../../components/TextAreaField';
import { formatDateTime } from '../../../format/dateTime';
import { categoryLabel } from '../../support/inquiryView';
import { ADMIN_INQUIRIES_KEY, adminInquiryQuery } from './inquiryBoxQueries';
import { boxProblemText, replyMailLine, senderLabel } from './inquiryBoxView';

// 답의 최대 길이(인증 서버의 support/models.py)
const REPLY_MAX = 5000;

export function InquiryDetail({ id, onDeleted }: { id: string; onDeleted: () => void }) {
  const queryClient = useQueryClient();
  const query = useQuery(adminInquiryQuery(id));
  const loadedId = query.data?.id;

  // 열면 읽음이 되므로 목록의 굵은 줄과 안 읽은 수를 다시 읽는다. 한 번만
  useEffect(() => {
    if (loadedId) void queryClient.invalidateQueries({ queryKey: [...ADMIN_INQUIRIES_KEY, 'list'] });
  }, [loadedId, queryClient]);

  if (query.isPending) return <p aria-busy="true">불러오는 중</p>;
  if (query.isError) return <Notice tone="error">{boxProblemText(query.error)}</Notice>;
  return <Opened inquiry={query.data} onDeleted={onDeleted} />;
}

function Opened({ inquiry, onDeleted }: { inquiry: AdminInquiry; onDeleted: () => void }) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();

  async function remove(): Promise<boolean> {
    setBusy(true);
    setProblem(undefined);
    try {
      await deleteInquiry(inquiry.id);
      queryClient.removeQueries({ queryKey: adminInquiryQuery(inquiry.id).queryKey });
      await queryClient.invalidateQueries({ queryKey: ADMIN_INQUIRIES_KEY });
      onDeleted();
      return true;
    } catch (error) {
      setProblem({ message: boxProblemText(error) });
      setBusy(false);
      return false;
    }
  }

  return (
    <article className="inquiry-detail" aria-labelledby="inquiry-detail-title">
      <header className="inquiry-detail__head">
        <h2 id="inquiry-detail-title">{inquiry.title}</h2>
        <ConfirmButton label="이 문의 지우기" title="이 문의를 지울까요?" confirm="지우기" busy={busy} problem={problem} onConfirm={remove}>
          <p>되돌릴 수 없습니다. 이미 보낸 답 메일은 그대로 갑니다.</p>
        </ConfirmButton>
      </header>
      <dl className="inquiry-detail__meta">
        <dt>보낸 사람</dt>
        <dd>
          {senderLabel(inquiry)}
          {inquiry.sender ? ` (${inquiry.email})` : ' (로그인하지 않음)'}
        </dd>
        <dt>종류</dt>
        <dd>{categoryLabel(inquiry.category)}</dd>
        <dt>보낸 때</dt>
        <dd>{formatDateTime(inquiry.created_at)}</dd>
        <dt>처음 연 사람</dt>
        <dd>{inquiry.read_at ? `${inquiry.read_by?.nickname ?? '(비운 계정)'} · ${formatDateTime(inquiry.read_at)}` : '아직 아무도 열지 않음'}</dd>
      </dl>
      <p className="inquiry-detail__body">{inquiry.body}</p>
      {inquiry.answered_at ? <Answered inquiry={inquiry} /> : <ReplyForm inquiry={inquiry} />}
    </article>
  );
}

function Answered({ inquiry }: { inquiry: AdminInquiry }) {
  return (
    <section className="inquiry-detail__reply" aria-label="보낸 답">
      <p className="hint">
        {inquiry.answered_by?.nickname ?? '(비운 계정)'}이(가) {formatDateTime(inquiry.answered_at as string)}에 답했습니다. {replyMailLine(inquiry)}
      </p>
      <p className="inquiry-detail__body">{inquiry.reply}</p>
    </section>
  );
}

function ReplyForm({ inquiry }: { inquiry: AdminInquiry }) {
  const queryClient = useQueryClient();
  const [reply, setReply] = useState('');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setProblem(null);
    try {
      const answered = await replyToInquiry(inquiry.id, reply.trim());
      queryClient.setQueryData(adminInquiryQuery(inquiry.id).queryKey, answered);
      await queryClient.invalidateQueries({ queryKey: [...ADMIN_INQUIRIES_KEY, 'list'] });
    } catch (error) {
      setProblem(boxProblemText(error));
      await queryClient.invalidateQueries({ queryKey: adminInquiryQuery(inquiry.id).queryKey });
    }
    setBusy(false);
  }

  return (
    <form className="inquiry-detail__form" onSubmit={submit} aria-label="답 쓰기">
      {problem ? <Notice tone="error">{problem}</Notice> : null}
      <TextAreaField
        label="답"
        rows={6}
        maxLength={REPLY_MAX}
        value={reply}
        onChange={(event) => setReply(event.target.value)}
        hint={`${inquiry.email} 로 메일을 보냅니다. 답은 한 번만 쓸 수 있습니다.`}
      />
      <Button type="submit" busy={busy} disabled={!reply.trim()}>
        답 보내기
      </Button>
    </form>
  );
}
