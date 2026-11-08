// web/apps/web/src/pages/trpg/studio/scenarios/AchievementsTab.tsx
// 시나리오의 업적 탭(B9). 제작자가 자기 작품에 다는 업적이다(스팀의 업적과 같다). 인증 서버의 활동 배지와는 다른 것이다.
// 업적을 차례대로 늘어놓고 줄마다 숨김과 받는 조건을 한 줄로 보인다. 차례가 시나리오 소개에 보이는 차례다.
// 줄을 고치면 창이 열리고, 창의 저장이 업적 목록을 통째로 바로 보낸다. 위로·아래로도 바로 저장한다(장 탭과 같다).
// 받는 조건은 퀘스트의 조건과 같고(ConditionsEditor), 라운드가 닫힐 때 엔진이 보고 그 테이블에 앉은 모두에게 준다.
// 그림은 내가 올린 그림에서 고른다(PortraitChooser). 내가 올린 것인지는 저장할 때(422), 조건이 맞는지는 게시 점검이 본다.

import { Button, Checkbox, Dialog, Notice, TextField } from '@ai-trpg/ui';
import { useCallback, useState, type FormEvent } from 'react';
import type { ScenarioDetail } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { TextAreaField } from '../../../../components/TextAreaField';
import { PortraitChooser } from '../../portraits/PortraitChooser';
import {
  ACHIEVEMENT_DESCRIPTION_MAX_LENGTH,
  ACHIEVEMENT_NAME_MAX_LENGTH,
  achievementDraft,
  achievementHints,
  achievementLine,
  canMoveAchievement,
  hasAchievementHints,
  MAX_ACHIEVEMENTS,
  movedAchievement,
  newAchievementId,
  toAchievement,
  withAchievement,
  withoutAchievement,
  type AchievementDraft,
} from './achievementsForm';
import { ConditionsEditor } from './ConditionsEditor';
import { KINDS_FOR, withChapterKind, type Targets } from './conditionsForm';
import { useConditionTargets } from './useConditionTargets';
import { useScenarioSave } from './useScenarioSave';

type Props = { scenario: ScenarioDetail };

/** 고치는 업적. index 가 null 이면 새 업적이다 */
type Editing = { id: string; index: number | null };

export function AchievementsTab({ scenario }: Props) {
  const { targets, pending, failed } = useConditionTargets(scenario);
  const [editing, setEditing] = useState<Editing | null>(null);
  const close = useCallback(() => setEditing(null), []);
  const saving = useScenarioSave(scenario.id);
  if (pending) return <p aria-busy="true">불러오는 중</p>;
  const achievements = scenario.achievements;
  const full = achievements.length >= MAX_ACHIEVEMENTS;

  async function move(index: number, step: -1 | 1) {
    await saving.save({ achievements: movedAchievement(achievements, index, step) });
  }

  return (
    <section className="page-section" aria-labelledby="achievements-heading">
      <h2 id="achievements-heading">
        업적{' '}
        <span className="hint">
          ({achievements.length} / {MAX_ACHIEVEMENTS})
        </span>
      </h2>
      <p className="hint">
        이 작품의 업적을 답니다. 라운드가 닫힐 때 받는 조건이 채워졌으면 엔진이 그 테이블에 캐릭터를 갖고 앉은 모두에게 줍니다. 한 사람은 업적마다 한 번만 받습니다. 숨긴 업적은 받기
        전까지 이름, 받는 법, 그림이 가려집니다. 차례가 시나리오 소개에 보이는 차례입니다. 창에서 저장하면 바로 저장됩니다.
      </p>
      {failed ? <Notice tone="error">로어북의 항목을 불러오지 못했습니다. 이름이 보이지 않을 수 있습니다.</Notice> : null}
      <ProblemNotice problem={saving.problem} />
      {achievements.length === 0 ? <p className="hint">업적이 없습니다.</p> : null}
      <ol className="plain-list studio-list" aria-label="업적">
        {achievements.map((achievement, index) => (
          <li key={achievement.id} className="studio-list__item studio-item">
            <div>
              <strong>{achievement.name}</strong>
              {achievement.description ? <div className="studio-list__description">{achievement.description}</div> : null}
              <div className="studio-list__description hint">{achievementLine(achievement, targets)}</div>
            </div>
            <div className="actions">
              <Button
                variant="quiet"
                aria-label={`${achievement.name} 위로`}
                disabled={saving.busy || !canMoveAchievement(achievements.length, index, -1)}
                onClick={() => void move(index, -1)}
              >
                위로
              </Button>
              <Button
                variant="quiet"
                aria-label={`${achievement.name} 아래로`}
                disabled={saving.busy || !canMoveAchievement(achievements.length, index, 1)}
                onClick={() => void move(index, 1)}
              >
                아래로
              </Button>
              <Button variant="quiet" aria-label={`${achievement.name} 고치기`} onClick={() => setEditing({ id: achievement.id, index })}>
                고치기
              </Button>
            </div>
          </li>
        ))}
      </ol>
      <p>
        <Button variant="secondary" disabled={full} onClick={() => setEditing({ id: newAchievementId(achievements), index: null })}>
          업적 더하기
        </Button>
      </p>
      <Dialog title={editing ? achievementTitle(scenario, editing) : '업적'} open={editing !== null} onClose={close}>
        {editing ? <AchievementForm scenario={scenario} targets={targets} editing={editing} done={close} /> : null}
      </Dialog>
    </section>
  );
}

function achievementTitle(scenario: ScenarioDetail, editing: Editing): string {
  if (editing.index === null) return '새 업적';
  return `업적: ${scenario.achievements[editing.index]?.name ?? ''}`;
}

type FormProps = Props & { targets: Targets; editing: Editing; done: () => void };

function AchievementForm({ scenario, targets, editing, done }: FormProps) {
  const achievement = editing.index === null ? undefined : scenario.achievements[editing.index];
  const [draft, setDraft] = useState<AchievementDraft>(() => achievementDraft(achievement));
  const saving = useScenarioSave(scenario.id);
  const hints = achievementHints(draft);
  const blocked = hasAchievementHints(hints);

  function update(changes: Partial<AchievementDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (blocked) return;
    if (await saving.save({ achievements: withAchievement(scenario.achievements, toAchievement(editing.id, draft)) })) done();
  }

  async function remove() {
    if (await saving.save({ achievements: withoutAchievement(scenario.achievements, editing.id) })) done();
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate aria-label="업적">
      <ProblemNotice problem={saving.problem} />
      <TextField label="이름" maxLength={ACHIEVEMENT_NAME_MAX_LENGTH} value={draft.name} onChange={(event) => update({ name: event.target.value })} error={hints.fields.name} />
      <TextAreaField
        label="받는 법(선택)"
        maxLength={ACHIEVEMENT_DESCRIPTION_MAX_LENGTH}
        value={draft.description}
        onChange={(event) => update({ description: event.target.value })}
        error={hints.fields.description}
        hint="숨기지 않은 업적이면 받기 전에도 보입니다."
      />
      <Checkbox
        label="숨긴 업적"
        description="받기 전에는 이름, 받는 법, 그림이 가려집니다. 이야기의 반전이 업적의 이름으로 새지 않게 합니다."
        checked={draft.hidden}
        onChange={(event) => update({ hidden: event.target.checked })}
      />
      <PortraitChooser
        name="업적의 그림"
        label="그림(선택)"
        hint="시나리오 소개의 업적 목록에 보입니다. 저장해야 붙습니다."
        imageId={draft.imageId}
        onChange={(imageId) => update({ imageId })}
      />
      <fieldset className="scenario-choices">
        <legend>받는 조건</legend>
        <p className="ui-field__hint">라운드가 닫힐 때 엔진이 봅니다. 퀘스트, 사건, 장을 모두 본 뒤라 같은 라운드에 이룬 퀘스트와 넘어간 장도 봅니다.</p>
        <ConditionsEditor
          label="받는 조건"
          kinds={withChapterKind(KINDS_FOR.any, targets)}
          drafts={draft.when}
          onChange={(when) => update({ when })}
          match={draft.match}
          onMatch={(match) => update({ match })}
          targets={targets}
          hints={hints.when}
        />
        {hints.fields.when ? <p className="ui-field__error">{hints.fields.when}</p> : null}
      </fieldset>
      <p className="hint">이름표: {editing.id}. 받은 기록이 이것을 가리킵니다. 지우면 목록에서 빠지지만 이미 받은 기록은 남습니다.</p>
      <div className="actions">
        <Button type="submit" busy={saving.busy} disabled={blocked}>
          저장
        </Button>
        {achievement ? (
          <Button variant="quiet" disabled={saving.busy} onClick={() => void remove()}>
            업적 지우기
          </Button>
        ) : null}
      </div>
    </form>
  );
}
