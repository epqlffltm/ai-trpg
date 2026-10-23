// web/apps/web/src/pages/trpg/room/round/DeclarationForm.tsx
// 선언 내기와 고치기. 글을 쓰고, 행동을 하나 붙이거나 붙이지 않는다(action/ActionFields.tsx).
// 행동의 대상(장면의 인물과 몬스터)은 장면을 읽어 고른다. 상태 패널의 단추가 행동의 칸을 채워 달라고 하면 받아 채운다.
// 보내면 서버가 라운드를 돌려준다. 하던 라운드 읽기를 멈추고 그 값으로 바로 바꾼다(roundQueries 의 replaceCurrentRound).
// 모두가 냈으면 닫기 시작한 라운드가 온다.
// 마감 전에는 남의 선언이 보이지 않는다. 맞출 것은 채팅으로 맞춘다.

import { Button } from '@ai-trpg/ui';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useId, useRef, useState, type FormEvent, type RefObject } from 'react';
import { declare } from '../../../../api/rounds';
import type { Declaration, TableDetail, TableMember } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { ActionFields } from './action/ActionFields';
import type { ActionContext } from './action/actionOptions';
import { useActionRequests } from './action/actionRequest';
import {
  DECLARATION_MAX,
  declarationHints,
  initialDeclarationDraft,
  toDeclarationUpdate,
  type DeclarationDraft,
} from './declarationForm';
import { tableQuery } from '../roomQueries';
import { replaceCurrentRound, roundsKey, sceneCastQuery } from './roundQueries';
import { describeDeclarationProblem, type RoundProblem } from './roundProblem';

type Props = {
  table: TableDetail;
  me: TableMember;
  mine: Declaration | undefined;
  onDone: () => void;
  onCancel?: (() => void) | undefined;
  /** 상태 패널의 부탁을 받아 칸을 채웠다. 낸 것을 보던 중이었으면 입력을 계속 연다 */
  onRequest?: () => void;
};

export function DeclarationForm({ table, me, mine, onDone, onCancel, onRequest }: Props) {
  const queryClient = useQueryClient();
  const contentId = useId();
  const contentRef = useRef<HTMLTextAreaElement>(null);
  const cast = useQuery(sceneCastQuery(table.id));
  const [draft, setDraft] = useState<DeclarationDraft>(() => initialDeclarationDraft(table.rules, mine));
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<RoundProblem | undefined>();
  const ctx: ActionContext = { table, me, cast: cast.data ?? null };
  const hints = declarationHints(draft, ctx);
  useRequestedAction(setDraft, contentRef, onRequest);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setProblem(undefined);
    try {
      await replaceCurrentRound(queryClient, table.id, await declare(table.id, toDeclarationUpdate(draft, ctx)));
      onDone();
    } catch (error) {
      const next = describeDeclarationProblem(error);
      setProblem(next);
      if (next.refresh) refreshAfterProblem();
      setBusy(false);
    }
  }

  /** 그 사이 바뀐 것(라운드, 장면, 내 돈과 소지품)을 다시 읽는다 */
  function refreshAfterProblem() {
    void queryClient.invalidateQueries({ queryKey: roundsKey(table.id) });
    void queryClient.invalidateQueries({ queryKey: tableQuery(table.id).queryKey });
  }

  return (
    <form className="declaration-form" onSubmit={submit} noValidate aria-label="선언">
      <ProblemNotice problem={problem} />
      <div className="ui-field">
        <label className="ui-field__label" htmlFor={contentId}>
          무엇을 하나요
        </label>
        <textarea
          ref={contentRef}
          id={contentId}
          className="ui-field__input declaration-form__content"
          rows={3}
          maxLength={DECLARATION_MAX}
          value={draft.content}
          onChange={(event) => setDraft((current) => ({ ...current, content: event.target.value }))}
          aria-invalid={hints.content && draft.content ? true : undefined}
        />
        <p className="ui-field__hint">마감 전에는 다른 사람의 선언이 보이지 않습니다. 함께 할 일은 채팅으로 맞춰 주세요.</p>
      </div>
      <ActionFields
        draft={draft.action}
        ctx={ctx}
        onChange={(changes) => setDraft((current) => ({ ...current, action: { ...current.action, ...changes } }))}
        error={draft.action.kind === 'none' ? null : hints.action}
      />
      {cast.isError ? <p className="hint">장면의 인물을 불러오지 못해 대상을 고르는 행동이 줄었습니다.</p> : null}
      <div className="form-actions">
        <Button type="submit" busy={busy} disabled={Object.keys(hints).length > 0}>
          {mine ? '고쳐 내기' : '선언하기'}
        </Button>
        {onCancel ? (
          <Button variant="quiet" onClick={onCancel}>
            그대로 두기
          </Button>
        ) : null}
      </div>
    </form>
  );
}

/** 상태 패널이 부탁한 행동으로 칸을 채우고, 글을 쓰는 칸으로 간다. 받은 부탁은 지운다 */
function useRequestedAction(
  setDraft: (update: (current: DeclarationDraft) => DeclarationDraft) => void,
  contentRef: RefObject<HTMLTextAreaElement | null>,
  onRequest: (() => void) | undefined,
) {
  const { pending, take } = useActionRequests();
  useEffect(() => {
    if (!pending) return;
    setDraft((current) => ({ ...current, action: { ...current.action, ...pending.patch } }));
    onRequest?.();
    take(pending.id);
    contentRef.current?.focus();
    // 부탁(pending)이 바뀔 때만 한다. onRequest 는 그릴 때마다 새로 만들어진다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, take, setDraft, contentRef]);
}
