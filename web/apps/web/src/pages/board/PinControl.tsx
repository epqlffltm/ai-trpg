// web/apps/web/src/pages/board/PinControl.tsx
// 운영자의 고정과 풀기(A11). 고정은 창에서 날 수(1~365, 기본 7)를 정한다. 그날이 지나면 서버가 저절로 내린다.
// 이미 고정한 글은 "고정 기간 바꾸기"(다시 고정하면 기간을 새로 잡고 맨 위로 올린다)와 "고정 풀기". 한 게시판에 5개까지다(409).

import { Button, Dialog, TextField } from '@ai-trpg/ui';
import { useCallback, useState, type FormEvent } from 'react';
import type { Post } from '../../api/types';
import type { FormProblem } from '../../auth/problem';
import { ProblemNotice } from '../../components/ProblemNotice';
import { formatDateTime } from '../../format/dateTime';
import { parsePinDays, PIN_DAYS } from './boardForm';

type Props = {
  post: Post;
  busy: boolean;
  problem: FormProblem | undefined;
  onPin: (days: number | null) => Promise<boolean>;
};

export function PinControl({ post, busy, problem, onPin }: Props) {
  const [open, setOpen] = useState(false);
  const [days, setDays] = useState(String(PIN_DAYS.default));
  const [touched, setTouched] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const parsed = parsePinDays(days);

  function start() {
    setDays(String(PIN_DAYS.default));
    setTouched(false);
    setOpen(true);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (parsed !== null && (await onPin(parsed))) setOpen(false);
  }

  return (
    <>
      {post.pinned && post.pinned_until ? <p className="hint">{formatDateTime(post.pinned_until)}까지 고정</p> : null}
      <Button variant="quiet" onClick={start}>
        {post.pinned ? '고정 기간 바꾸기' : '고정'}
      </Button>
      {post.pinned ? (
        <Button variant="quiet" busy={busy && !open} onClick={() => void onPin(null)}>
          고정 풀기
        </Button>
      ) : null}
      {!open ? <ProblemNotice problem={problem} /> : null}
      <Dialog title="글 고정" open={open} onClose={close}>
        <form onSubmit={(event) => void submit(event)} noValidate aria-label="고정">
          <ProblemNotice problem={problem} />
          <TextField
            label="며칠 동안"
            type="number"
            inputMode="numeric"
            min={PIN_DAYS.min}
            max={PIN_DAYS.max}
            value={days}
            onChange={(event) => setDays(event.target.value)}
            error={touched && parsed === null ? `${PIN_DAYS.min}일부터 ${PIN_DAYS.max}일까지 적어 주세요.` : undefined}
          />
          <p className="hint">게시판의 첫 쪽 맨 위에 둡니다. 한 게시판에 5개까지입니다.</p>
          <div className="actions">
            <Button type="submit" busy={busy}>
              고정하기
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
