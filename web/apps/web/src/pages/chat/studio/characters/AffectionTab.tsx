// web/apps/web/src/pages/chat/studio/characters/AffectionTab.tsx
// 캐릭터의 호감도 탭(C6): 쓰는지, 보이는 방식, 처음 값, 모델이 답 하나에 바꿀 수 있는 크기, 단계, 오르내리는 규칙.
// 규칙의 대상은 저장한 물건과 장소에서 고른다(지도·물건 탭에서 저장하지 않은 것은 아직 나오지 않는다).
// 단계의 이름을 바꾸면 그 이름을 가리키는 이벤트 씬은 게시 점검이 잡는다.

import { Button, Checkbox, SelectField, TextField } from '@ai-trpg/ui';
import { useState } from 'react';
import type { AssetAffectionDisplay, AssetCharacterDetail, AssetTriggerKind } from '../../../../api/types';
import {
  addRule,
  addStage,
  affectionDraft,
  affectionHints,
  CHANGE_MAX,
  changeRule,
  changeStage,
  hasAffectionHints,
  newAffectionDraft,
  removeRule,
  removeStage,
  RULES_MAX,
  STAGE_NAME_MAX,
  STAGES_MAX,
  targetsPlace,
  toAffectionBody,
  type AffectionDraft,
  type AffectionHints,
} from './affectionForm';
import { CharacterForm } from './CharacterForm';
import { newKey } from './keys';
import { useCharacterSave } from './useCharacterSave';

const DISPLAYS: Record<AssetAffectionDisplay, string> = { number: '숫자와 게이지', stage: '단계 이름과 게이지(숫자는 보이지 않는다)' };
const TRIGGERS: Record<AssetTriggerKind, string> = { give_item: '물건을 건넸다', use_item: '물건을 썼다', reach_place: '장소에 갔다' };

type Update = (change: (draft: AffectionDraft) => AffectionDraft) => void;
type Choice = { id: string; name: string };

export function AffectionTab({ character }: { character: AssetCharacterDetail }) {
  const [draft, setDraft] = useState<AffectionDraft>(() => affectionDraft(character));
  const saving = useCharacterSave(character.id);
  const hints = affectionHints(draft);
  const update: Update = (change) => setDraft(change);
  const places = character.places.map((place, index) => ({ id: place.id, name: place.name || `장소 ${index + 1}` }));
  const items = character.items.map((item, index) => ({ id: item.id, name: item.name || `물건 ${index + 1}` }));

  async function submit() {
    const saved = await saving.save(toAffectionBody(draft));
    if (saved) setDraft(affectionDraft(saved));
  }

  function toggle(enabled: boolean) {
    update((current) => (enabled && current.stages.length === 0 ? newAffectionDraft() : { ...current, enabled }));
  }

  return (
    <CharacterForm
      label="호감도"
      busy={saving.busy}
      problem={saving.problem}
      saved={saving.saved}
      blocked={hasAffectionHints(hints)}
      onSubmit={() => void submit()}
    >
      <Checkbox
        label="호감도를 쓴다"
        description="대화하는 동안 0~100 의 값 하나가 오르내리고, 단계에 따라 캐릭터의 태도와 이벤트 씬이 바뀝니다."
        checked={draft.enabled}
        onChange={(event) => toggle(event.target.checked)}
      />
      {draft.enabled ? <AffectionFields draft={draft} hints={hints} update={update} places={places} items={items} /> : null}
    </CharacterForm>
  );
}

type FieldsProps = { draft: AffectionDraft; hints: AffectionHints; update: Update; places: Choice[]; items: Choice[] };

function AffectionFields({ draft, hints, update, places, items }: FieldsProps) {
  return (
    <>
      <SelectField
        label="보이는 방식"
        value={draft.display}
        onChange={(event) => update((current) => ({ ...current, display: event.target.value as AssetAffectionDisplay }))}
      >
        {Object.entries(DISPLAYS).map(([display, label]) => (
          <option key={display} value={display}>
            {label}
          </option>
        ))}
      </SelectField>
      <TextField
        label="처음 값(0~100)"
        inputMode="numeric"
        value={draft.start}
        onChange={(event) => update((current) => ({ ...current, start: event.target.value }))}
        error={hints.start}
      />
      <TextField
        label={`모델이 답 하나에 바꿀 수 있는 크기(0~${CHANGE_MAX})`}
        inputMode="numeric"
        value={draft.modelStep}
        onChange={(event) => update((current) => ({ ...current, modelStep: event.target.value }))}
        error={hints.modelStep}
      />
      <p className="hint">대화의 흐름을 보고 모델이 제안하는 변화의 상한입니다. 0 이면 아래 규칙만 호감도를 바꿉니다.</p>
      <StagesSection draft={draft} hints={hints} update={update} />
      <RulesSection draft={draft} hints={hints} update={update} places={places} items={items} />
    </>
  );
}

function StagesSection({ draft, hints, update }: { draft: AffectionDraft; hints: AffectionHints; update: Update }) {
  return (
    <fieldset className="scenario-choices">
      <legend>단계</legend>
      <p className="hint">값이 경계 이상이면 그 단계입니다. 첫 단계는 0 에서 시작하고, 아래로 갈수록 경계가 커집니다.</p>
      <ol className="plain-list" aria-label="단계">
        {draft.stages.map((stage, index) => (
          <li key={index} className="scenario-opening">
            <TextField
              label={`단계 ${index + 1}의 이름`}
              maxLength={STAGE_NAME_MAX}
              value={stage.name}
              onChange={(event) => update((current) => changeStage(current, index, { name: event.target.value }))}
            />
            <TextField
              label={`단계 ${index + 1}의 경계(0~100)`}
              inputMode="numeric"
              value={stage.at}
              onChange={(event) => update((current) => changeStage(current, index, { at: event.target.value }))}
              error={hints.stages[index]}
            />
            {draft.stages.length > 1 ? (
              <div className="form-actions">
                <Button variant="quiet" aria-label={`단계 ${index + 1} 지우기`} onClick={() => update((current) => removeStage(current, index))}>
                  지우기
                </Button>
              </div>
            ) : null}
          </li>
        ))}
      </ol>
      <p>
        <Button variant="secondary" disabled={draft.stages.length >= STAGES_MAX} onClick={() => update(addStage)}>
          단계 더하기
        </Button>{' '}
        <span className="hint">
          {draft.stages.length} / {STAGES_MAX}
        </span>
      </p>
    </fieldset>
  );
}

function RulesSection({ draft, hints, update, places, items }: FieldsProps) {
  return (
    <fieldset className="scenario-choices">
      <legend>오르내리는 규칙</legend>
      <p className="hint">사용자가 그 행동을 하면 정한 만큼 바뀝니다(0~100 안에서). 대상은 저장한 물건과 장소에서 고릅니다.</p>
      {draft.rules.length === 0 ? <p>규칙이 없습니다.</p> : null}
      <ol className="plain-list" aria-label="규칙">
        {draft.rules.map((rule, index) => {
          const choices = targetsPlace(rule.kind) ? places : items;
          return (
            <li key={rule.id} className="scenario-opening">
              <SelectField
                label={`규칙 ${index + 1}의 행동`}
                value={rule.kind}
                onChange={(event) => update((current) => changeRule(current, rule.id, { kind: event.target.value as AssetTriggerKind }))}
              >
                {Object.entries(TRIGGERS).map(([kind, label]) => (
                  <option key={kind} value={kind}>
                    {label}
                  </option>
                ))}
              </SelectField>
              <SelectField
                label={`규칙 ${index + 1}의 대상`}
                value={rule.target}
                onChange={(event) => update((current) => changeRule(current, rule.id, { target: event.target.value }))}
                hint={choices.length === 0 ? (targetsPlace(rule.kind) ? '저장한 장소가 없습니다. 지도 탭에서 먼저 더해 주세요.' : '저장한 물건이 없습니다. 물건 탭에서 먼저 더해 주세요.') : undefined}
              >
                <option value="">고르지 않음</option>
                {choices.map((choice) => (
                  <option key={choice.id} value={choice.id}>
                    {choice.name}
                  </option>
                ))}
              </SelectField>
              <TextField
                label={`규칙 ${index + 1}의 변화(-${CHANGE_MAX}~${CHANGE_MAX})`}
                inputMode="numeric"
                value={rule.change}
                onChange={(event) => update((current) => changeRule(current, rule.id, { change: event.target.value }))}
                error={hints.rules[rule.id]}
              />
              <Checkbox
                label="처음 한 번만"
                checked={rule.once}
                onChange={(event) => update((current) => changeRule(current, rule.id, { once: event.target.checked }))}
              />
              <div className="form-actions">
                <Button variant="quiet" aria-label={`규칙 ${index + 1} 지우기`} onClick={() => update((current) => removeRule(current, rule.id))}>
                  지우기
                </Button>
              </div>
            </li>
          );
        })}
      </ol>
      <p>
        <Button variant="secondary" disabled={draft.rules.length >= RULES_MAX} onClick={() => update((current) => addRule(current, newKey('rule', current.rules.map((rule) => rule.id))))}>
          규칙 더하기
        </Button>{' '}
        <span className="hint">
          {draft.rules.length} / {RULES_MAX}
        </span>
      </p>
    </fieldset>
  );
}
