// web/apps/web/src/pages/board/CommentForm.tsx
// 댓글 한 칸의 폼(A11). 새 댓글, 답글, 고치기가 함께 쓴다. 2000자까지, 빈칸만은 받지 않는다.
// 보내기는 쓰는 쪽이 한다. 성공하면 새 글은 칸을 비우고, 그만두기가 있으면(답글, 고치기) 닫는다.

import { Button } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import type { FormProblem } from '../../auth/problem';
import { ProblemNotice } from '../../components/ProblemNotice';
import { TextAreaField } from '../../components/TextAreaField';
import { COMMENT_LIMIT, commentProblem } from './boardForm';

type Props = {
  label: string;
  initial?: string;
  submitLabel: string;
  busy: boolean;
  problem: FormProblem | undefined;
  onSubmit: (content: string) => Promise<boolean>;
  onCancel?: () => void;
};

export function CommentForm({ label, initial = '', submitLabel, busy, problem, onSubmit, onCancel }: Props) {
  const [content, setContent] = useState(initial);
  const [touched, setTouched] = useState(false);
  const local = touched ? commentProblem(content) : null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (commentProblem(content) !== null) return;
    if (!(await onSubmit(content))) return;
    setTouched(false);
    if (onCancel) onCancel();
    else setContent('');
  }

  return (
    <form className="comment-form" onSubmit={(event) => void submit(event)} noValidate>
      <ProblemNotice problem={problem && !problem.fields?.content ? problem : undefined} />
      <TextAreaField
        label={label}
        rows={3}
        maxLength={COMMENT_LIMIT}
        value={content}
        onChange={(event) => setContent(event.target.value)}
        error={local ?? problem?.fields?.content}
        hint={`${content.length.toLocaleString('ko-KR')} / ${COMMENT_LIMIT.toLocaleString('ko-KR')}자`}
      />
      <div className="form-actions">
        <Button type="submit" busy={busy}>
          {submitLabel}
        </Button>
        {onCancel ? (
          <Button variant="quiet" onClick={onCancel}>
            그만두기
          </Button>
        ) : null}
      </div>
    </form>
  );
}
