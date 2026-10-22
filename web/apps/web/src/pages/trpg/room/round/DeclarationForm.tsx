// web/apps/web/src/pages/trpg/room/round/DeclarationForm.tsx
// 선언 내기와 고치기. 글을 쓰고, 판정을 붙이려면 능력과 난이도를 고른다. 판정의 눈은 라운드를 마감할 때 서버가 굴린다.
// 보내면 서버가 라운드를 돌려준다. 그 값으로 바로 바꾼다. 모두가 냈으면 닫기 시작한 라운드가 온다.
// 마감 전에는 남의 선언이 보이지 않는다. 맞출 것은 채팅으로 맞춘다.

import { Button, Checkbox, SelectField } from '@ai-trpg/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useId, useState, type FormEvent } from 'react';
import { declare } from '../../../../api/rounds';
import type { Declaration, Ruleset } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import {
  DECLARATION_MAX,
  declarationHints,
  hasOtherAction,
  initialDeclarationDraft,
  toDeclarationUpdate,
  type DeclarationDraft,
} from './declarationForm';
import { currentRoundQuery, roundsKey } from './roundQueries';
import { describeDeclarationProblem, type RoundProblem } from './roundProblem';

type Props = {
  tableId: string;
  rules: Ruleset;
  mine: Declaration | undefined;
  onDone: () => void;
  onCancel?: (() => void) | undefined;
};

export function DeclarationForm({ tableId, rules, mine, onDone, onCancel }: Props) {
  const queryClient = useQueryClient();
  const contentId = useId();
  const [draft, setDraft] = useState<DeclarationDraft>(() => initialDeclarationDraft(rules, mine));
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<RoundProblem | undefined>();
  const hints = declarationHints(draft, rules);

  function update(changes: Partial<DeclarationDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setProblem(undefined);
    try {
      queryClient.setQueryData(currentRoundQuery(tableId).queryKey, await declare(tableId, toDeclarationUpdate(draft)));
      onDone();
    } catch (error) {
      const next = describeDeclarationProblem(error);
      setProblem(next);
      if (next.refresh) void queryClient.invalidateQueries({ queryKey: roundsKey(tableId) });
      setBusy(false);
    }
  }

  return (
    <form className="declaration-form" onSubmit={submit} noValidate aria-label="선언">
      <ProblemNotice problem={problem} />
      <div className="ui-field">
        <label className="ui-field__label" htmlFor={contentId}>
          무엇을 하나요
        </label>
        <textarea
          id={contentId}
          className="ui-field__input declaration-form__content"
          rows={3}
          maxLength={DECLARATION_MAX}
          value={draft.content}
          onChange={(event) => update({ content: event.target.value })}
          aria-invalid={hints.content && draft.content ? true : undefined}
        />
        <p className="ui-field__hint">마감 전에는 다른 사람의 선언이 보이지 않습니다. 함께 할 일은 채팅으로 맞춰 주세요.</p>
      </div>
      <Checkbox
        label="판정 붙이기"
        description="능력과 난이도를 고르면 라운드를 마감할 때 서버가 주사위를 굴립니다. 한 라운드에 한 번입니다."
        checked={draft.withCheck}
        onChange={(event) => update({ withCheck: event.target.checked })}
      />
      {draft.withCheck ? <CheckInputs rules={rules} draft={draft} onChange={update} error={hints.check} /> : null}
      {hasOtherAction(mine) ? (
        <p className="hint">앞서 낸 선언의 행동은 여기서 고칠 수 없습니다. 다시 내면 그 행동은 빠집니다.</p>
      ) : null}
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

type CheckInputsProps = {
  rules: Ruleset;
  draft: DeclarationDraft;
  onChange: (changes: Partial<DeclarationDraft>) => void;
  error?: string | undefined;
};

/** 판정의 능력과 난이도. 난이도는 "보통(15)"처럼 목표값을 함께 보인다 */
function CheckInputs({ rules, draft, onChange, error }: CheckInputsProps) {
  return (
    <div className="ability-grid">
      <SelectField label="능력" value={draft.ability} onChange={(event) => onChange({ ability: event.target.value })}>
        {rules.abilities.map((ability) => (
          <option key={ability.key} value={ability.key}>
            {ability.name}
          </option>
        ))}
      </SelectField>
      <SelectField
        label="난이도"
        value={draft.difficulty}
        onChange={(event) => onChange({ difficulty: event.target.value })}
        error={error}
      >
        {rules.difficulties.map((difficulty) => (
          <option key={difficulty.key} value={difficulty.key}>
            {difficulty.name}({difficulty.target})
          </option>
        ))}
      </SelectField>
    </div>
  );
}
