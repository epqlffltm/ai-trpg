// web/apps/web/src/pages/trpg/studio/rulebooks/ProgressionFields.tsx
// 룰북의 성장(#286) 편집. 켜고 끄기, 레벨표(레벨 2 부터 줄마다 누적 경험치, 최대 HP 증가, 능력치 점수), 줄 더하기·지우기.
// 검사는 progressionForm.ts. 템플릿을 고르면 그 템플릿의 레벨표로 돌아간다.

import { Button, Checkbox, TextField } from '@ai-trpg/ui';
import { levelOf, MAX_LEVEL, MAX_LEVEL_ROWS, newLevelDraft, turnedOn, type LevelDraft, type ProgressionDraft } from './progressionForm';

type Props = {
  progression: ProgressionDraft;
  hints: Record<string, string>;
  onChange: (progression: ProgressionDraft) => void;
};

export function ProgressionFields({ progression, hints, onChange }: Props) {
  const { levels } = progression;
  const replace = (index: number, next: LevelDraft) => onChange({ ...progression, levels: levels.map((one, at) => (at === index ? next : one)) });
  return (
    <fieldset className="scenario-choices">
      <legend>성장</legend>
      <Checkbox
        label="캐릭터가 경험치를 모아 레벨이 오름"
        description="경험치는 시나리오가 줍니다(퀘스트의 보상, 몬스터, 사건). 레벨을 올리는 것은 엔진만 합니다."
        checked={progression.on}
        onChange={(event) => onChange(turnedOn(progression, event.target.checked))}
      />
      {progression.on ? (
        <>
          <p className="ui-field__hint">
            캐릭터는 레벨 1, 경험치 0 에서 시작합니다. 줄마다 그 레벨이 되는 누적 경험치와 오를 때 받는 것입니다. 받은 점수는 플레이어가 능력치에 놓습니다. 레벨 {MAX_LEVEL}까지 둡니다.
          </p>
          {levels.map((level, index) => (
            <LevelRow
              key={index}
              level={level}
              index={index}
              hint={(field) => hints[`level.${index}.${field}`]}
              onChange={(next) => replace(index, next)}
              onRemove={() => onChange({ ...progression, levels: levels.filter((_, at) => at !== index) })}
            />
          ))}
          {hints.progression ? <p className="ui-field__error">{hints.progression}</p> : null}
          <Button variant="quiet" disabled={levels.length >= MAX_LEVEL_ROWS} onClick={() => onChange({ ...progression, levels: [...levels, newLevelDraft(levels)] })}>
            레벨 더하기
          </Button>
        </>
      ) : null}
    </fieldset>
  );
}

type RowProps = {
  level: LevelDraft;
  index: number;
  hint: (field: string) => string | undefined;
  onChange: (level: LevelDraft) => void;
  onRemove: () => void;
};

/** 레벨표 한 줄 */
function LevelRow({ level, index, hint, onChange, onRemove }: RowProps) {
  const name = `레벨 ${levelOf(index)}`;
  const set = (changes: Partial<LevelDraft>) => onChange({ ...level, ...changes });
  return (
    <fieldset className="scenario-choices" aria-label={name}>
      <legend>{name}</legend>
      <div className="ability-grid">
        <TextField label="누적 경험치" inputMode="numeric" value={level.xp} onChange={(event) => set({ xp: event.target.value })} error={hint('xp')} />
        <TextField label="최대 HP 증가" inputMode="numeric" value={level.maxHp} onChange={(event) => set({ maxHp: event.target.value })} error={hint('max_hp')} />
        <TextField label="능력치 점수" inputMode="numeric" value={level.points} onChange={(event) => set({ points: event.target.value })} error={hint('points')} />
      </div>
      <Button variant="quiet" onClick={onRemove}>
        {name} 지우기
      </Button>
    </fieldset>
  );
}
