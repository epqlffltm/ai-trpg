// web/apps/web/src/pages/story/studio/WorldAchievementsTab.tsx
// 세계관의 업적 탭(D7, docs/architecture/achievements.md 의 "story"). 제작자가 자기 작품에 다는 업적이다(스팀의 업적과 같다).
// 인증 서버의 활동 배지와는 다른 것이다. 업적마다 이름, 받는 법, 숨김, 그림, 받는 조건을 적는다. 적은 차례가 소개에 보이는 차례다.
// 받는 조건은 이벤트의 조건과 같다(ConditionsEditor). 엔진이 행동마다 그 뒤의 상태로 보고, 맞으면 그 사람이 받는다(계정마다 한 번).
// 장소, 이벤트, 인물, 물건, 시간대, 엔딩, 장은 저장된 것에서 고른다. 탭의 칸만 보낸다(장 탭과 같다).

import { Button, Checkbox, TextField } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import type { StoryWorldDetail } from '../../../api/storyWorlds';
import { ImagePicker } from '../../../components/ImagePicker';
import { TextAreaField } from '../../../components/TextAreaField';
import { CharacterForm as StudioForm } from '../../chat/studio/characters/CharacterForm';
import { newKey } from '../../chat/studio/characters/keys';
import {
  ACHIEVEMENT_DESCRIPTION_MAX,
  ACHIEVEMENT_NAME_MAX,
  achievementDrafts,
  achievementsHints,
  ACHIEVEMENTS_MAX,
  addAchievement,
  changeAchievement,
  hasAchievementsHints,
  moveAchievementUp,
  removeAchievement,
  toAchievementsBody,
  type AchievementDraft,
  type AchievementHints,
} from './achievementsForm';
import { ConditionsEditor } from './ConditionsEditor';
import { savedChoices, type ConditionChoices } from './conditionsForm';
import { useWorldSave } from './useWorldSave';
import { labelOr } from './worldLabels';
import { castCharactersQuery } from './worldQueries';

export function WorldAchievementsTab({ world }: { world: StoryWorldDetail }) {
  const [achievements, setAchievements] = useState<AchievementDraft[]>(() => achievementDrafts(world));
  const saving = useWorldSave(world.id);
  const characters = useQuery(castCharactersQuery());
  const names = (characters.data?.items ?? []).map((character) => ({ id: character.id, name: character.name }));
  const choices = savedChoices(world, names, world.events.map((event) => ({ id: event.id, name: event.name })));
  const hints = achievementsHints(achievements, choices);

  async function submit() {
    const result = await saving.save(toAchievementsBody(achievements));
    if (result) setAchievements(achievementDrafts(result));
  }

  return (
    <StudioForm label="업적" busy={saving.busy} problem={saving.problem} saved={saving.saved} blocked={hasAchievementsHints(hints)} onSubmit={() => void submit()}>
      <p className="hint">
        이 세계관의 업적을 답니다. 행동마다 받는 조건을 보아 맞으면 그 사람이 받습니다. 한 사람은 업적마다 한 번만 받습니다. 숨긴 업적은 받기 전까지 이름, 받는 법, 그림이 가려집니다. 적은
        차례가 소개에 보이는 차례입니다.
      </p>
      <p className="hint">"그 엔딩을 본 적이 있다"는 그 엔딩에 닿은 행동에도 맞습니다. 대화로는 받지 않습니다.</p>
      {achievements.length === 0 ? <p>아직 업적이 없습니다.</p> : null}
      <ol className="plain-list" aria-label="업적">
        {achievements.map((achievement, index) => (
          <AchievementItem
            key={achievement.id}
            achievement={achievement}
            index={index}
            choices={choices}
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
    </StudioForm>
  );
}

type ItemProps = {
  achievement: AchievementDraft;
  index: number;
  choices: ConditionChoices;
  hints: AchievementHints;
  update: (change: (achievement: AchievementDraft) => AchievementDraft) => void;
  onUp: () => void;
  onRemove: () => void;
};

function AchievementItem({ achievement, index, choices, hints, update, onUp, onRemove }: ItemProps) {
  const label = labelOr(achievement.name, `업적 ${index + 1}`);
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
        description="받기 전에는 이름, 받는 법, 그림이 가려집니다. 이야기의 반전이 업적의 이름으로 새지 않게 합니다."
        checked={achievement.hidden}
        onChange={(change) => update((current) => ({ ...current, hidden: change.target.checked }))}
      />
      <ImagePicker label={`${label}의 그림`} imageId={achievement.imageId} onChange={(imageId) => update((current) => ({ ...current, imageId }))} hint="소개의 업적 목록과 받았을 때의 알림에 보입니다." />
      <ConditionsEditor prefix={label} draft={achievement.when} choices={choices} hints={hints.conditions} onChange={(when) => update((current) => ({ ...current, when }))} emptyText="조건을 하나 이상 적어야 합니다." />
      {hints.when ? <p className="ui-field__error">{hints.when}</p> : null}
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
