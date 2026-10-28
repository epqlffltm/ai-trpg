// web/apps/web/src/pages/story/studio/eventsForm.ts
// 세계관의 이벤트 탭의 입력. 순수한 함수다. 규칙은 서버와 같다(asset-server/app/worlds/schemas.py 의 Event).
//
//   - 이벤트는 50 개까지이고 적은 차례가 뜻이 있다(행동 뒤에 조건이 맞는 것 가운데 위의 것 하나만 열린다). id 는 화면이 붙인다
//   - 이름(30 자), 열리는 조건, 되풀이(아니면 한 번만), 장면 지시, 열릴 때의 효과, 선택지(3 개까지: 글 100 자와 효과)
//   - 이벤트의 이름은 사용자에게 보인다(기록, 갤러리). 장면의 상황은 모델만 읽는다

import type { StoryWorldDetail, StoryWorldEvent, StoryWorldUpdate } from '../../../api/storyWorlds';
import { conditionsDraft, conditionsHints, EMPTY_CONDITIONS, toConditions, type ConditionChoices, type ConditionsDraft } from './conditionsForm';
import { effectsDraft, effectsHints, toEffects, type EffectDraft } from './effectsForm';
import { EMPTY_SCENE, sceneDraft, sceneHint, toScene, type SceneDraft } from './sceneForm';

export const EVENTS_MAX = 50;
export const EVENT_NAME_MAX = 30;
export const CHOICES_MAX = 3;
export const CHOICE_TEXT_MAX = 100;

export type ChoiceDraft = { id: string; text: string; effects: EffectDraft[] };
export type EventDraft = { id: string; name: string; when: ConditionsDraft; repeat: boolean; scene: SceneDraft; onOpen: EffectDraft[]; choices: ChoiceDraft[] };

export function eventDraft(event: StoryWorldEvent): EventDraft {
  return {
    id: event.id,
    name: event.name,
    when: conditionsDraft(event.when),
    repeat: event.repeat,
    scene: sceneDraft(event.scene),
    onOpen: effectsDraft(event.on_open),
    choices: event.choices.map((choice) => ({ id: choice.id, text: choice.text, effects: effectsDraft(choice.effects) })),
  };
}

export function eventDrafts(world: Pick<StoryWorldDetail, 'events'>): EventDraft[] {
  return world.events.map(eventDraft);
}

export function addEvent(events: EventDraft[], id: string): EventDraft[] {
  if (events.length >= EVENTS_MAX) return events;
  return [...events, { id, name: '', when: EMPTY_CONDITIONS, repeat: false, scene: EMPTY_SCENE, onOpen: [], choices: [] }];
}

export function changeEvent(events: EventDraft[], id: string, change: (event: EventDraft) => EventDraft): EventDraft[] {
  return events.map((event) => (event.id === id ? change(event) : event));
}

export function removeEvent(events: EventDraft[], id: string): EventDraft[] {
  return events.filter((event) => event.id !== id);
}

/** 한 칸 위로. 위의 이벤트가 먼저 맞춰진다 */
export function moveEventUp(events: EventDraft[], index: number): EventDraft[] {
  if (index <= 0 || index >= events.length) return events;
  const next = [...events];
  [next[index - 1], next[index]] = [next[index] as EventDraft, next[index - 1] as EventDraft];
  return next;
}

export function addChoice(event: EventDraft, id: string): EventDraft {
  return event.choices.length >= CHOICES_MAX ? event : { ...event, choices: [...event.choices, { id, text: '', effects: [] }] };
}

export function changeChoice(event: EventDraft, id: string, changes: Partial<Omit<ChoiceDraft, 'id'>>): EventDraft {
  return { ...event, choices: event.choices.map((choice) => (choice.id === id ? { ...choice, ...changes } : choice)) };
}

export function removeChoice(event: EventDraft, id: string): EventDraft {
  return { ...event, choices: event.choices.filter((choice) => choice.id !== id) };
}

export type EventHints = {
  name?: string;
  scene?: string;
  when: Record<number, string>;
  onOpen: Record<number, string>;
  choices: Record<string, string>;
  choiceEffects: Record<string, Record<number, string>>;
};

function eventHints(event: EventDraft, earlier: EventDraft[], choices: ConditionChoices): EventHints {
  const hints: EventHints = { when: conditionsHints(event.when, choices), onOpen: effectsHints(event.onOpen, choices), choices: {}, choiceEffects: {} };
  const name = event.name.trim();
  if (name === '') hints.name = '이름을 적어 주세요.';
  else if (name.length > EVENT_NAME_MAX) hints.name = `이름은 ${EVENT_NAME_MAX}자까지입니다.`;
  else if (earlier.some((other) => other.name.trim() === name)) hints.name = '같은 이름의 이벤트가 이미 있습니다.';
  const scene = sceneHint(event.scene, choices.cast);
  if (scene) hints.scene = scene;
  for (const choice of event.choices) {
    const text = choice.text.trim();
    if (text === '') hints.choices[choice.id] = '선택지의 글을 적어 주세요.';
    else if (text.length > CHOICE_TEXT_MAX) hints.choices[choice.id] = `글은 ${CHOICE_TEXT_MAX}자까지입니다.`;
    const effects = effectsHints(choice.effects, choices);
    if (Object.keys(effects).length > 0) hints.choiceEffects[choice.id] = effects;
  }
  return hints;
}

/** 이벤트마다(id → 문제) */
export function eventsHints(events: EventDraft[], choices: ConditionChoices): Record<string, EventHints> {
  const hints: Record<string, EventHints> = {};
  events.forEach((event, index) => {
    hints[event.id] = eventHints(event, events.slice(0, index), choices);
  });
  return hints;
}

export function eventHasHints(hints: EventHints): boolean {
  return Boolean(hints.name || hints.scene) || [hints.when, hints.onOpen, hints.choices, hints.choiceEffects].some((group) => Object.keys(group).length > 0);
}

export function hasEventsHints(hints: Record<string, EventHints>): boolean {
  return Object.values(hints).some(eventHasHints);
}

/** 이벤트 탭의 칸만 보낸다. 힌트가 없을 때만 부른다 */
export function toEventsBody(events: EventDraft[]): StoryWorldUpdate {
  return {
    events: events.map((event) => ({
      id: event.id,
      name: event.name.trim(),
      when: toConditions(event.when),
      repeat: event.repeat,
      scene: toScene(event.scene),
      on_open: toEffects(event.onOpen),
      choices: event.choices.map((choice) => ({ id: choice.id, text: choice.text.trim(), effects: toEffects(choice.effects) })),
    })),
  };
}
