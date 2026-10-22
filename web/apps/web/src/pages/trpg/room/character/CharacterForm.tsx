// web/apps/web/src/pages/trpg/room/character/CharacterForm.tsx
// 캐릭터 정하기(B5)의 입력. 이 테이블이 허용한 방식만 보인다(character_modes). 방식마다 칸이 다르다.
//   - pregen: 프리젠을 고른다
//   - custom: 이름과 설명만. 숫자는 시나리오의 기본 시트
//   - manual, point_buy, rolled: 이름과 설명, 능력치. 최대 HP 는 시작할 때 서버가 구한다(여기서는 어림)
// 보내면 서버가 테이블을 돌려준다. 그 값으로 바로 바꾼다. 실패가 테이블이 달라진 탓이면 다시 읽는다.

import { Button, Radio, TextField } from '@ai-trpg/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useId, useState, type FormEvent } from 'react';
import { setCharacter } from '../../../../api/tableRoom';
import type { CharacterMode, TableDetail, TableMember } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { characterModeLabel } from '../../labels';
import { tableQuery } from '../roomQueries';
import { AbilityInputs } from './AbilityInputs';
import {
  chosenAbilities,
  DESCRIPTION_MAX,
  draftHints,
  freshRoll,
  initialDraft,
  isPlayerMade,
  mayRoll,
  maxHpPreview,
  NAME_MAX,
  placeSlot,
  toCharacterUpdate,
  type CharacterDraft,
} from './characterForm';
import { describeCharacterProblem, type CharacterProblem } from './characterProblem';
import { PointBuyInputs } from './PointBuyInputs';
import { PregenPicker } from './PregenPicker';
import { RolledAssign } from './RolledAssign';
import { SheetStats } from './SheetStats';

const MODE_DESCRIPTIONS: Record<CharacterMode, string> = {
  pregen: '시나리오의 제작자가 만든 캐릭터를 가져옵니다.',
  custom: '이름과 설명을 쓰고, 숫자는 시나리오의 기본 시트를 받습니다.',
  manual: '능력치의 점수를 범위 안에서 직접 적습니다.',
  point_buy: '정해진 총점 안에서 능력치의 점수를 삽니다.',
  rolled: '서버가 주사위로 굴린 점수를 능력치에 하나씩 놓습니다.',
};

type Props = {
  table: TableDetail;
  member: TableMember;
  onDone: () => void;
  /** 정해 둔 캐릭터가 있으면 그대로 두고 닫는다 */
  onCancel?: (() => void) | undefined;
};

export function CharacterForm({ table, member, onDone, onCancel }: Props) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<CharacterDraft>(() => initialDraft(table, member));
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<CharacterProblem | undefined>();
  const roll = freshRoll(member);
  const hints = draftHints(draft, table, member.user_id, roll);

  function update(changes: Partial<CharacterDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setProblem(undefined);
    try {
      const saved = await setCharacter(table.id, toCharacterUpdate(draft, table.rules, roll));
      queryClient.setQueryData(tableQuery(table.id).queryKey, saved);
      onDone();
    } catch (error) {
      const next = describeCharacterProblem(error);
      setProblem(next);
      if (next.refresh) void queryClient.invalidateQueries({ queryKey: tableQuery(table.id).queryKey });
      setBusy(false);
    }
  }

  return (
    <form className="character-form" onSubmit={submit} noValidate aria-label="캐릭터 정하기">
      <ProblemNotice problem={problem} />
      {table.character_modes.length > 1 ? (
        <fieldset className="choice-list">
          <legend>만드는 방식</legend>
          {table.character_modes.map((mode) => (
            <Radio
              key={mode}
              name="character_mode"
              label={characterModeLabel(mode)}
              description={MODE_DESCRIPTIONS[mode]}
              checked={draft.mode === mode}
              onChange={() => update({ mode })}
            />
          ))}
        </fieldset>
      ) : (
        <p className="hint">만드는 방식: {characterModeLabel(draft.mode)}</p>
      )}
      {draft.mode === 'pregen' ? (
        <PregenPicker
          table={table}
          myId={member.user_id}
          selected={draft.pregenIndex}
          onSelect={(pregenIndex) => update({ pregenIndex })}
          error={hints.pregen}
        />
      ) : (
        <>
          <TextField
            label="이름"
            name="character_name"
            maxLength={NAME_MAX}
            value={draft.name}
            onChange={(event) => update({ name: event.target.value })}
            error={hints.name}
          />
          <DescriptionField value={draft.description} onChange={(description) => update({ description })} error={hints.description} />
          <ModeInputs table={table} member={member} draft={draft} onChange={update} />
          {hints.abilities ? <p className="ui-field__error">{hints.abilities}</p> : null}
        </>
      )}
      <div className="form-actions">
        <Button type="submit" busy={busy} disabled={Object.keys(hints).length > 0}>
          {member.character ? '이 캐릭터로 바꾸기' : '이 캐릭터로 정하기'}
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

type ModeInputsProps = {
  table: TableDetail;
  member: TableMember;
  draft: CharacterDraft;
  onChange: (changes: Partial<CharacterDraft>) => void;
};

/** 방식마다의 숫자. 기본 시트(custom)이거나 능력치의 입력과 최대 HP 의 어림 */
function ModeInputs({ table, member, draft, onChange }: ModeInputsProps) {
  const rules = table.rules;
  const roll = freshRoll(member);
  if (!isPlayerMade(draft.mode)) {
    const sheet = table.default_sheet;
    return sheet ? (
      <div className="character-numbers">
        <p className="waiting-room__label">받는 숫자(시나리오의 기본 시트)</p>
        <SheetStats rules={rules} abilities={sheet.abilities} maxHp={sheet.max_hp} />
      </div>
    ) : null;
  }
  const scores = chosenAbilities(draft, rules, roll);
  const maxHp = maxHpPreview(rules, table.player_made_hp, scores);
  return (
    <div className="character-numbers">
      <p className="waiting-room__label">
        능력치 <span className="hint">점수 {rules.score_min}~{rules.score_max}</span>
      </p>
      {draft.mode === 'manual' ? (
        <AbilityInputs rules={rules} scores={draft.manual} onChange={(manual) => onChange({ manual })} />
      ) : null}
      {draft.mode === 'point_buy' ? (
        <PointBuyInputs rules={rules} scores={draft.bought} onChange={(bought) => onChange({ bought })} />
      ) : null}
      {draft.mode === 'rolled' ? (
        <RolledAssign
          table={table}
          roll={roll}
          canRoll={mayRoll(member)}
          draft={draft}
          onPlace={(key, slot) => roll && onChange(placeSlot(draft, roll, key, slot))}
        />
      ) : null}
      {maxHp !== null ? (
        <p className="hint">최대 HP 는 시작할 때 정해집니다. 지금 점수로는 {maxHp}입니다.</p>
      ) : null}
    </div>
  );
}

function DescriptionField({
  value,
  onChange,
  error,
}: {
  value: string;
  onChange: (value: string) => void;
  error?: string | undefined;
}) {
  const id = useId();
  return (
    <div className="ui-field">
      <label className="ui-field__label" htmlFor={id}>
        설명(선택)
      </label>
      <textarea
        id={id}
        className="ui-field__input character-form__description"
        maxLength={DESCRIPTION_MAX}
        rows={3}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
      />
      {error ? (
        <p id={`${id}-error`} className="ui-field__error">
          {error}
        </p>
      ) : null}
    </div>
  );
}
