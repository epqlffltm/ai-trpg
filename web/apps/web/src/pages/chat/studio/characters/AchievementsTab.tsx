// web/apps/web/src/pages/chat/studio/characters/AchievementsTab.tsx
// 캐릭터의 업적 탭(C6, docs/architecture/achievements.md 의 "chat"). 제작자가 자기 캐릭터에 다는 업적이다(스팀의 업적과 같다).
// 인증 서버의 활동 배지와는 다른 것이다. 업적마다 이름, 받는 법, 숨김, 그림, 받는 조건을 적는다. 적은 차례가 소개에 보이는 차례다.
// 받는 조건은 chat 의 엔진이 아는 것뿐이다(가 본 장소, 가진 물건, 받은 물건, 호감도의 단계, 나온 이벤트 씬, 보낸 말의 수).
// 엔진이 답을 저장한 뒤 보고, 맞으면 그 사람이 받는다(계정마다 한 번). 대상은 저장한 것에서 고른다. 탭의 칸만 보낸다.

import { Button, Checkbox, SelectField, TextField } from '@ai-trpg/ui';
import { useState } from 'react';
import type { AssetAchievementKind, AssetAchievementMatch, AssetCharacterDetail } from '../../../../api/types';
import { ImagePicker } from '../../../../components/ImagePicker';
import { TextAreaField } from '../../../../components/TextAreaField';
import {
  ACHIEVEMENT_CONDITIONS_MAX,
  ACHIEVEMENT_COUNT_MAX,
  ACHIEVEMENT_DESCRIPTION_MAX,
  ACHIEVEMENT_NAME_MAX,
  achievementDrafts,
  achievementsHints,
  ACHIEVEMENTS_MAX,
  addAchievement,
  addCondition,
  changeAchievement,
  changeCondition,
  conditionChoices,
  hasAchievementsHints,
  KIND_FIELDS,
  moveAchievementUp,
  removeAchievement,
  removeCondition,
  toAchievementsBody,
  type AchievementDraft,
  type AchievementHints,
  type ConditionDraft,
} from './achievementsForm';
import { CharacterForm } from './CharacterForm';
import { newKey } from './keys';
import { useCharacterSave } from './useCharacterSave';

const KINDS: Record<AssetAchievementKind, string> = {
  visited_place: '그 장소에 가 본 적이 있다',
  hold_item: '그 물건을 몇 개 이상 가졌다',
  received_item: '상대에게 그 물건을 받은 적이 있다',
  affection_stage: '호감도가 그 단계 이상이다',
  scene_seen: '그 이벤트 씬이 나온 적이 있다',
  messages_at_least: '보낸 말이 몇 개 이상이다',
};

const EMPTY_CHOICES: Record<AssetAchievementKind, string> = {
  visited_place: '저장한 장소가 없습니다. 지도 탭에서 먼저 더해 주세요.',
  hold_item: '저장한 물건이 없습니다. 물건 탭에서 먼저 더해 주세요.',
  received_item: '저장한 물건이 없습니다. 물건 탭에서 먼저 더해 주세요.',
  affection_stage: '저장한 호감도 단계가 없습니다. 호감도 탭에서 먼저 켜 주세요.',
  scene_seen: '저장한 이벤트 씬이 없습니다. 이벤트 씬 탭에서 먼저 더해 주세요.',
  messages_at_least: '',
};

const MATCHES: Record<AssetAchievementMatch, string> = { all: '조건이 모두 맞으면', any: '조건이 하나라도 맞으면' };

export function AchievementsTab({ character }: { character: AssetCharacterDetail }) {
  const [achievements, setAchievements] = useState<AchievementDraft[]>(() => achievementDrafts(character));
  const saving = useCharacterSave(character.id);
  const hints = achievementsHints(achievements);

  async function submit() {
    const saved = await saving.save(toAchievementsBody(achievements));
    if (saved) setAchievements(achievementDrafts(saved));
  }

  return (
    <CharacterForm label="업적" busy={saving.busy} problem={saving.problem} saved={saving.saved} blocked={hasAchievementsHints(hints)} onSubmit={() => void submit()}>
      <p className="hint">
        이 캐릭터의 업적을 답니다. 답을 받을 때마다 받는 조건을 보아 맞으면 그 사람이 받습니다. 한 사람은 업적마다 한 번만 받습니다. 숨긴 업적은 받기 전까지 이름, 받는 법, 그림이
        가려집니다. 적은 차례가 소개에 보이는 차례입니다.
      </p>
      <p className="hint">장소, 받은 물건, 이벤트 씬, 보낸 말은 지금 보는 가지에서 셉니다. 대화의 내용으로는 받지 않습니다.</p>
      {achievements.length === 0 ? <p>아직 업적이 없습니다.</p> : null}
      <ol className="plain-list" aria-label="업적">
        {achievements.map((achievement, index) => (
          <AchievementItem
            key={achievement.id}
            character={character}
            achievement={achievement}
            index={index}
            hints={hints[achievement.id] as AchievementHints}
            update={(change) => setAchievements((current) => changeAchievement(current, achievement.id, change))}
            onUp={() => setAchievements((current) => moveAchievementUp(current, index))}
            onRemove={() => setAchievements((current) => removeAchievement(current, achievement.id))}
          />
        ))}
      </ol>
      <p>
        <Button
          variant="secondary"
          disabled={achievements.length >= ACHIEVEMENTS_MAX}
          onClick={() => setAchievements((current) => addAchievement(current, newKey('achievement', current.map((achievement) => achievement.id))))}
        >
          업적 더하기
        </Button>{' '}
        <span className="hint">
          {achievements.length} / {ACHIEVEMENTS_MAX}
        </span>
      </p>
    </CharacterForm>
  );
}

type ItemProps = {
  character: AssetCharacterDetail;
  achievement: AchievementDraft;
  index: number;
  hints: AchievementHints;
  update: (change: (achievement: AchievementDraft) => AchievementDraft) => void;
  onUp: () => void;
  onRemove: () => void;
};

function AchievementItem({ character, achievement, index, hints, update, onUp, onRemove }: ItemProps) {
  const label = achievement.name.trim() || `업적 ${index + 1}`;
  return (
    <li className="scenario-opening">
      <h3>{label}</h3>
      <TextField label={`${label}의 이름`} maxLength={ACHIEVEMENT_NAME_MAX} value={achievement.name} onChange={(change) => update((current) => ({ ...current, name: change.target.value }))} error={hints.name} />
      <TextAreaField
        label={`${label}의 받는 법(선택)`}
        maxLength={ACHIEVEMENT_DESCRIPTION_MAX}
        value={achievement.description}
        onChange={(change) => update((current) => ({ ...current, description: change.target.value }))}
        error={hints.description}
        hint="숨기지 않은 업적이면 받기 전에도 보입니다."
      />
      <Checkbox
        label={`${label}: 숨긴 업적`}
        description="받기 전에는 이름, 받는 법, 그림이 가려집니다."
        checked={achievement.hidden}
        onChange={(change) => update((current) => ({ ...current, hidden: change.target.checked }))}
      />
      <ImagePicker label={`${label}의 그림`} imageId={achievement.imageId} onChange={(imageId) => update((current) => ({ ...current, imageId }))} hint="소개의 업적 목록과 받았을 때의 알림에 보입니다." />
      <SelectField label={`${label}의 맞추는 법`} value={achievement.match} onChange={(change) => update((current) => ({ ...current, match: change.target.value as AssetAchievementMatch }))}>
        {Object.entries(MATCHES).map(([match, text]) => (
          <option key={match} value={match}>
            {text}
          </option>
        ))}
      </SelectField>
      <ol className="plain-list" aria-label={`${label}의 받는 조건`}>
        {achievement.items.map((condition, at) => (
          <ConditionItem
            key={at}
            character={character}
            prefix={`${label}의 조건 ${at + 1}`}
            condition={condition}
            hint={hints.conditions[at]}
            onChange={(changes) => update((current) => changeCondition(current, at, changes))}
            onRemove={() => update((current) => removeCondition(current, at))}
          />
        ))}
      </ol>
      {hints.when ? <p className="ui-field__error">{hints.when}</p> : null}
      <p>
        <Button variant="secondary" aria-label={`${label}에 조건 더하기`} disabled={achievement.items.length >= ACHIEVEMENT_CONDITIONS_MAX} onClick={() => update(addCondition)}>
          조건 더하기
        </Button>{' '}
        <span className="hint">
          {achievement.items.length} / {ACHIEVEMENT_CONDITIONS_MAX}
        </span>
      </p>
      <p className="hint">이름표: {achievement.id}. 받은 기록이 이것을 가리킵니다. 지우면 소개에서 빠지지만 이미 받은 기록은 남습니다.</p>
      <div className="form-actions">
        <Button variant="quiet" aria-label={`${label}을(를) 위로`} disabled={index === 0} onClick={onUp}>
          위로
        </Button>
        <Button variant="quiet" aria-label={`${label} 지우기`} onClick={onRemove}>
          업적 지우기
        </Button>
      </div>
    </li>
  );
}

type ConditionProps = {
  character: AssetCharacterDetail;
  prefix: string;
  condition: ConditionDraft;
  hint: string | undefined;
  onChange: (changes: Partial<ConditionDraft>) => void;
  onRemove: () => void;
};

function ConditionItem({ character, prefix, condition, hint, onChange, onRemove }: ConditionProps) {
  const fields = KIND_FIELDS[condition.kind];
  const choices = conditionChoices(character, condition.kind);
  const picked = fields.value ? condition.value : condition.target;
  return (
    <li>
      <SelectField label={`${prefix}의 종류`} value={condition.kind} onChange={(change) => onChange({ kind: change.target.value as AssetAchievementKind })}>
        {Object.entries(KINDS).map(([kind, text]) => (
          <option key={kind} value={kind}>
            {text}
          </option>
        ))}
      </SelectField>
      {fields.target || fields.value ? (
        <SelectField
          label={`${prefix}의 대상`}
          value={picked}
          onChange={(change) => onChange(fields.value ? { value: change.target.value } : { target: change.target.value })}
          hint={choices.length === 0 ? EMPTY_CHOICES[condition.kind] : undefined}
        >
          <option value="">고르지 않음</option>
          {choices.map((choice) => (
            <option key={choice.value} value={choice.value}>
              {choice.label}
            </option>
          ))}
        </SelectField>
      ) : null}
      {fields.count ? (
        <TextField label={`${prefix}의 수(1~${ACHIEVEMENT_COUNT_MAX})`} inputMode="numeric" value={condition.count} onChange={(change) => onChange({ count: change.target.value })} />
      ) : null}
      {hint ? <p className="ui-field__error">{hint}</p> : null}
      <Button variant="quiet" aria-label={`${prefix} 지우기`} onClick={onRemove}>
        조건 지우기
      </Button>
    </li>
  );
}
