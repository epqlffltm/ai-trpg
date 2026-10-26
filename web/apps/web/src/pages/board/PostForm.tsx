// web/apps/web/src/pages/board/PostForm.tsx
// 글의 폼(A11). 제목(100자)과 본문(20000자). 본문은 글자 그대로 보인다(서식을 해석하지 않는다).
// 저장은 쓰는 쪽(쓰기, 고치기)이 한다. 칸의 문제는 처음 저장을 누른 뒤부터 보이고, 서버의 칸 문장(400 errors)은 늘 보인다.

import { Button, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import type { FormProblem } from '../../auth/problem';
import { ProblemNotice } from '../../components/ProblemNotice';
import { TextAreaField } from '../../components/TextAreaField';
import { POST_LIMITS, postDraftProblems, type PostDraft } from './boardForm';

type Props = {
  initial: PostDraft;
  submitLabel: string;
  busy: boolean;
  problem: FormProblem | undefined;
  /** 그만두면 돌아갈 곳 */
  cancelTo: string;
  onSubmit: (draft: PostDraft) => void;
};

export function PostForm({ initial, submitLabel, busy, problem, cancelTo, onSubmit }: Props) {
  const [draft, setDraft] = useState(initial);
  const [touched, setTouched] = useState(false);
  const problems = postDraftProblems(draft);
  const errorOf = (field: keyof PostDraft) => (touched ? problems[field] : undefined) ?? problem?.fields?.[field];

  function submit(event: FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (Object.keys(problems).length === 0) onSubmit(draft);
  }

  return (
    <form className="post-form" onSubmit={submit} noValidate aria-label="글">
      <ProblemNotice problem={problem} />
      <TextField
        label="제목"
        name="title"
        maxLength={POST_LIMITS.title}
        value={draft.title}
        onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))}
        error={errorOf('title')}
      />
      <TextAreaField
        label="본문"
        name="content"
        rows={14}
        maxLength={POST_LIMITS.content}
        value={draft.content}
        onChange={(event) => setDraft((current) => ({ ...current, content: event.target.value }))}
        error={errorOf('content')}
        hint={`${draft.content.length.toLocaleString('ko-KR')} / ${POST_LIMITS.content.toLocaleString('ko-KR')}자. 글자 그대로 보입니다.`}
      />
      <div className="form-actions">
        <Button type="submit" busy={busy}>
          {submitLabel}
        </Button>
        <Link to={cancelTo}>그만두기</Link>
      </div>
    </form>
  );
}
