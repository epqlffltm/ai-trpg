// web/apps/web/src/pages/story/studio/endingsForm.ts
// 세계관의 엔딩 탭의 입력. 순수한 함수다. 규칙은 서버와 같다(asset-server/app/worlds/schemas.py 의 Ending).
//
//   - 엔딩은 30 개까지이고 적은 차례가 뜻이 있다. 시작(고백 성공, 고백 실패, 기한, 이벤트)이 일어나면
//     그 시작의 엔딩을 위에서부터 맞춰 보고 조건이 맞는 첫 엔딩을 고른다. id 는 화면이 붙인다
//   - 시작의 대상: 고백은 고백할 수 있는 인물, 이벤트는 이벤트, 기한은 없다. 시작을 바꾸면 대상을 비운다
//   - 시작마다 조건이 빈 엔딩이 하나는 있어야 게시된다(ending_missing). 그것은 게시 점검이 막는다
//   - 계정에 남기기(unlock), 못 본 사람에게 보일 힌트(100 자)

import type { StoryWorldDetail, StoryWorldEnding, StoryWorldUpdate } from '../../../api/storyWorlds';
import { conditionsDraft, conditionsHints, EMPTY_CONDITIONS, toConditions, type Choice, type ConditionChoices, type ConditionsDraft } from './conditionsForm';
import { EMPTY_SCENE, sceneDraft, sceneHint, toScene, type SceneDraft } from './sceneForm';

export const ENDINGS_MAX = 30;
export const ENDING_NAME_MAX = 30;
export const HINT_MAX = 100;

export type TriggerKind = StoryWorldEnding['trigger']['kind'];

export const TRIGGER_LABELS: Record<TriggerKind, string> = {
  confess_success: '고백 성공',
  confess_fail: '고백 실패(끝내는 실패)',
  deadline: '기한이 지남',
  event: '이벤트가 열림',
};

export type EndingDraft = { id: string; name: string; trigger: TriggerKind; target: string; when: ConditionsDraft; scene: SceneDraft; unlock: boolean; hint: string };

export function endingDraft(ending: StoryWorldEnding): EndingDraft {
  return {
    id: ending.id,
    name: ending.name,
    trigger: ending.trigger.kind,
    target: ending.trigger.target ?? '',
    when: conditionsDraft(ending.when),
    scene: sceneDraft(ending.scene),
    unlock: ending.unlock,
    hint: ending.hint,
  };
}

export function endingDrafts(world: Pick<StoryWorldDetail, 'endings'>): EndingDraft[] {
  return world.endings.map(endingDraft);
}

export function addEnding(endings: EndingDraft[], id: string): EndingDraft[] {
  if (endings.length >= ENDINGS_MAX) return endings;
  return [...endings, { id, name: '', trigger: 'confess_success', target: '', when: EMPTY_CONDITIONS, scene: EMPTY_SCENE, unlock: true, hint: '' }];
}

/** 엔딩 하나를 바꾼다. 시작을 바꾸면 대상을 비운다 */
export function changeEnding(endings: EndingDraft[], id: string, change: (ending: EndingDraft) => EndingDraft): EndingDraft[] {
  return endings.map((ending) => {
    if (ending.id !== id) return ending;
    const next = change(ending);
    return next.trigger !== ending.trigger ? { ...next, target: '' } : next;
  });
}

export function removeEnding(endings: EndingDraft[], id: string): EndingDraft[] {
  return endings.filter((ending) => ending.id !== id);
}

export function moveEndingUp(endings: EndingDraft[], index: number): EndingDraft[] {
  if (index <= 0 || index >= endings.length) return endings;
  const next = [...endings];
  [next[index - 1], next[index]] = [next[index] as EndingDraft, next[index - 1] as EndingDraft];
  return next;
}

/** 시작의 대상으로 고를 거리. 고백은 고백할 수 있는 인물(confessable), 이벤트는 이벤트, 기한은 없다 */
export function triggerTargets(trigger: TriggerKind, confessable: Choice[], events: Choice[]): Choice[] {
  if (trigger === 'confess_success' || trigger === 'confess_fail') return confessable;
  if (trigger === 'event') return events;
  return [];
}

export type EndingHints = { name?: string; target?: string; hint?: string; scene?: string; when: Record<number, string> };

function endingHints(ending: EndingDraft, earlier: EndingDraft[], choices: ConditionChoices, confessable: Choice[]): EndingHints {
  const hints: EndingHints = { when: conditionsHints(ending.when, choices) };
  const name = ending.name.trim();
  if (name === '') hints.name = '이름을 적어 주세요.';
  else if (name.length > ENDING_NAME_MAX) hints.name = `이름은 ${ENDING_NAME_MAX}자까지입니다.`;
  else if (earlier.some((other) => other.name.trim() === name)) hints.name = '같은 이름의 엔딩이 이미 있습니다.';
  if (ending.trigger !== 'deadline') {
    const targets = triggerTargets(ending.trigger, confessable, choices.events);
    if (ending.target === '') hints.target = ending.trigger === 'event' ? '이벤트를 골라 주세요.' : '고백받는 인물을 골라 주세요.';
    else if (!targets.some((target) => target.id === ending.target)) hints.target = '없는 대상입니다. 다시 골라 주세요.';
  }
  if (ending.hint.trim().length > HINT_MAX) hints.hint = `힌트는 ${HINT_MAX}자까지입니다.`;
  const scene = sceneHint(ending.scene, choices.cast);
  if (scene) hints.scene = scene;
  return hints;
}

export function endingsHints(endings: EndingDraft[], choices: ConditionChoices, confessable: Choice[]): Record<string, EndingHints> {
  const hints: Record<string, EndingHints> = {};
  endings.forEach((ending, index) => {
    hints[ending.id] = endingHints(ending, endings.slice(0, index), choices, confessable);
  });
  return hints;
}

export function hasEndingsHints(hints: Record<string, EndingHints>): boolean {
  return Object.values(hints).some((entry) => Boolean(entry.name || entry.target || entry.hint || entry.scene) || Object.keys(entry.when).length > 0);
}

/** 엔딩 탭의 칸만 보낸다. 힌트가 없을 때만 부른다. 기한의 시작은 대상을 보내지 않는다 */
export function toEndingsBody(endings: EndingDraft[]): StoryWorldUpdate {
  return {
    endings: endings.map((ending) => ({
      id: ending.id,
      name: ending.name.trim(),
      trigger: ending.trigger === 'deadline' ? { kind: 'deadline' } : { kind: ending.trigger, target: ending.target },
      when: toConditions(ending.when),
      scene: toScene(ending.scene),
      unlock: ending.unlock,
      hint: ending.hint.trim(),
    })),
  };
}
