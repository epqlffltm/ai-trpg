// web/apps/web/src/pages/story/studio/WorldEndingsTab.tsx
// 세계관의 엔딩 탭(D7). 엔딩마다 이름, 시작(고백 성공, 고백 실패, 기한, 이벤트)과 그 대상, 조건, 장면 지시, 계정에 남기기, 힌트.
// 시작이 일어나면 그 시작의 엔딩을 위에서부터 맞춰 보고 조건이 맞는 첫 엔딩을 고른다. 시작마다 조건이 빈 엔딩이 하나는 있어야 게시된다.
// 인물, 이벤트, 장소, 물건, 시간대는 저장된 것에서 고른다. 고백의 대상은 고백할 수 있는 인물이다.

import { Button, Checkbox, SelectField, TextField } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import type { StoryWorldDetail } from '../../../api/storyWorlds';
import { CharacterForm as StudioForm } from '../../chat/studio/characters/CharacterForm';
import { newKey } from '../../chat/studio/characters/keys';
import { ConditionsEditor } from './ConditionsEditor';
import { savedChoices, type Choice, type ConditionChoices } from './conditionsForm';
import {
  addEnding,
  changeEnding,
  ENDING_NAME_MAX,
  endingDrafts,
  ENDINGS_MAX,
  endingsHints,
  hasEndingsHints,
  HINT_MAX,
  moveEndingUp,
  removeEnding,
  toEndingsBody,
  TRIGGER_LABELS,
  triggerTargets,
  type EndingDraft,
  type EndingHints,
  type TriggerKind,
} from './endingsForm';
import { SceneEditor } from './SceneEditor';
import { useWorldSave } from './useWorldSave';
import { labelOr } from './worldLabels';
import { castCharactersQuery } from './worldQueries';

export function WorldEndingsTab({ world }: { world: StoryWorldDetail }) {
  const [endings, setEndings] = useState<EndingDraft[]>(() => endingDrafts(world));
  const saving = useWorldSave(world.id);
  const characters = useQuery(castCharactersQuery());
  const names = (characters.data?.items ?? []).map((character) => ({ id: character.id, name: character.name }));
  const choices = savedChoices(world, names, world.events.map((event) => ({ id: event.id, name: event.name })));
  const confessable = choices.cast.filter((member) => world.cast.some((entry) => entry.id === member.id && entry.confession));
  const hints = endingsHints(endings, choices, confessable);

  async function submit() {
    const saved = await saving.save(toEndingsBody(endings));
    if (saved) setEndings(endingDrafts(saved));
  }

  return (
    <StudioForm label="엔딩" busy={saving.busy} problem={saving.problem} saved={saving.saved} blocked={hasEndingsHints(hints)} onSubmit={() => void submit()}>
      <p className="hint">
        고백, 기한, 이벤트 같은 시작이 일어나면 그 시작의 엔딩을 위에서부터 맞춰 보고 조건이 맞는 첫 엔딩을 고릅니다. 시작마다 조건이 빈 엔딩이 하나는 있어야 게시합니다.
        못 본 엔딩은 이름 대신 "???"와 힌트가 보입니다.
      </p>
      {endings.length === 0 ? <p>아직 엔딩이 없습니다.</p> : null}
      <ol className="plain-list" aria-label="엔딩">
        {endings.map((ending, index) => (
          <EndingItem
            key={ending.id}
            ending={ending}
            index={index}
            choices={choices}
            confessable={confessable}
            hints={hints[ending.id] as EndingHints}
            update={(change) => setEndings((current) => changeEnding(current, ending.id, change))}
            onUp={() => setEndings((current) => moveEndingUp(current, index))}
            onRemove={() => setEndings((current) => removeEnding(current, ending.id))}
          />
        ))}
      </ol>
      <p>
        <Button variant="secondary" disabled={endings.length >= ENDINGS_MAX} onClick={() => setEndings((current) => addEnding(current, newKey('ending', current.map((ending) => ending.id))))}>
          엔딩 더하기
        </Button>{' '}
        <span className="hint">
          {endings.length} / {ENDINGS_MAX}
        </span>
      </p>
    </StudioForm>
  );
}

type ItemProps = {
  ending: EndingDraft;
  index: number;
  choices: ConditionChoices;
  confessable: Choice[];
  hints: EndingHints;
  update: (change: (ending: EndingDraft) => EndingDraft) => void;
  onUp: () => void;
  onRemove: () => void;
};

function EndingItem({ ending, index, choices, confessable, hints, update, onUp, onRemove }: ItemProps) {
  const label = labelOr(ending.name, `엔딩 ${index + 1}`);
  const targets = triggerTargets(ending.trigger, confessable, choices.events);
  return (
    <li className="scenario-opening">
      <h3>{label}</h3>
      <TextField label={`엔딩 ${index + 1}의 이름`} maxLength={ENDING_NAME_MAX} value={ending.name} onChange={(change) => update((current) => ({ ...current, name: change.target.value }))} error={hints.name} />
      <SelectField label={`${label}의 시작`} value={ending.trigger} onChange={(change) => update((current) => ({ ...current, trigger: change.target.value as TriggerKind }))}>
        {Object.entries(TRIGGER_LABELS).map(([value, text]) => (
          <option key={value} value={value}>
            {text}
          </option>
        ))}
      </SelectField>
      {ending.trigger !== 'deadline' ? (
        <SelectField label={`${label}의 시작의 대상`} value={ending.target} onChange={(change) => update((current) => ({ ...current, target: change.target.value }))} error={hints.target}>
          <option value="">고르지 않음</option>
          {targets.map((target, at) => (
            <option key={target.id} value={target.id}>
              {labelOr(target.name, `${at + 1}번째`)}
            </option>
          ))}
        </SelectField>
      ) : null}
      {ending.trigger !== 'deadline' && ending.trigger !== 'event' && confessable.length === 0 ? <p className="hint">인물 탭에서 고백할 수 있는 인물을 먼저 저장해 주세요.</p> : null}
      <ConditionsEditor prefix={label} draft={ending.when} choices={choices} hints={hints.when} onChange={(when) => update((current) => ({ ...current, when }))} emptyText="조건이 없으면 이 시작에서 늘 고를 수 있는 엔딩입니다." />
      <SceneEditor prefix={label} scene={ending.scene} cast={choices.cast} hint={hints.scene} onChange={(scene) => update((current) => ({ ...current, scene }))} />
      <Checkbox label={`${label}을(를) 계정의 기록에 남긴다`} checked={ending.unlock} onChange={(change) => update((current) => ({ ...current, unlock: change.target.checked }))} description="남기는 엔딩만 '엔딩 n/m'에 셉니다." />
      <TextField label={`${label}의 힌트(선택)`} maxLength={HINT_MAX} value={ending.hint} onChange={(change) => update((current) => ({ ...current, hint: change.target.value }))} error={hints.hint} />
      <div className="form-actions">
        <Button variant="quiet" aria-label={`${label}을(를) 위로`} disabled={index === 0} onClick={onUp}>
          위로
        </Button>
        <Button variant="quiet" aria-label={`${label} 지우기`} onClick={onRemove}>
          엔딩 지우기
        </Button>
      </div>
    </li>
  );
}
