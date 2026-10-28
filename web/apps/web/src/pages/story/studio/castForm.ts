// web/apps/web/src/pages/story/studio/castForm.ts
// 세계관의 인물 탭의 입력. 순수한 함수다. 규칙은 서버와 같다(asset-server/app/worlds/schemas.py 의 CastMember).
//
//   - 인물은 20 명까지이고 하나마다 내 캐릭터 하나를 가리킨다(같은 캐릭터를 두 번 넣지 않는다). id 는 화면이 붙인다
//     (조건과 이벤트가 이 id 를 가리키므로 바뀌면 안 된다)
//   - 기본 장소(비우면 어디에도 없다), 일정(시간대, 장소, 조건. 위의 줄부터 맞춰 본다, 20 줄까지)
//   - 호감도: 보이는 방식, 처음 값(0~100), 단계(1~10, 첫 단계는 0, 경계가 오른다, 이름은 하나씩),
//     선물(물건마다 -20~20(0 아님), 한 번만, id 는 화면이 붙인다. 50 개까지)
//   - 고백: 쓰지 않으면 null(고백할 수 없는 인물). 성공하는 단계와 조건, 실패하면 계속(내려가는 값 0~100, 다시 못 하는 날 1~30) 또는 끝
//   - 보이기의 덮어쓰기: 비우면 세계관의 기본. 지도가 "단계 이상"이면 그 단계를 고른다
// 숫자 칸은 글로 들고 있다가 보낼 때 바꾼다.

import type { StoryWorldCast, StoryWorldDetail, StoryWorldShow, StoryWorldUpdate } from '../../../api/storyWorlds';
import { integerIn } from '../../chat/studio/characters/affectionForm';
import { conditionsDraft, conditionsHints, EMPTY_CONDITIONS, toConditions, type ConditionChoices, type ConditionsDraft } from './conditionsForm';

export const CAST_MAX = 20;
export const SCHEDULE_MAX = 20;
export const STAGES_MAX = 10;
export const STAGE_NAME_MAX = 20;
export const GIFTS_MAX = 50;
export const GIFT_CHANGE_MAX = 20;
export const AFFECTION_MAX = 100;
export const COOLDOWN_MAX = 30;

type Reveal = StoryWorldShow['reveal'];
type MapPresence = StoryWorldShow['map'];
type PanelField = StoryWorldShow['panel'][number];

export type ScheduleDraft = { slot: string; place: string; when: ConditionsDraft };
export type StageDraft = { name: string; at: string };
export type GiftDraft = { id: string; item: string; change: string; once: boolean };
export type ConfessionDraft = { stage: string; when: ConditionsDraft; onFail: 'continue' | 'end'; failDrop: string; cooldownDays: string };

export type CastDraft = {
  id: string;
  characterId: string;
  home: string;
  schedule: ScheduleDraft[];
  display: 'number' | 'stage';
  start: string;
  stages: StageDraft[];
  gifts: GiftDraft[];
  confession: ConfessionDraft | null;
  reveal: Reveal | '';
  map: MapPresence | '';
  mapStage: string;
  panel: PanelField[] | null;
};

export function castDraft(member: StoryWorldCast): CastDraft {
  const confession = member.confession;
  return {
    id: member.id,
    characterId: member.character_id,
    home: member.home ?? '',
    schedule: member.schedule.map((line) => ({ slot: line.slot, place: line.place, when: conditionsDraft(line.when) })),
    display: member.affection.display,
    start: String(member.affection.start),
    stages: member.affection.stages.map((stage) => ({ name: stage.name, at: String(stage.at) })),
    gifts: member.affection.gifts.map((gift) => ({ id: gift.id, item: gift.item, change: String(gift.change), once: gift.once })),
    confession: confession
      ? { stage: confession.stage, when: conditionsDraft(confession.when), onFail: confession.on_fail, failDrop: String(confession.fail_drop), cooldownDays: String(confession.cooldown_days) }
      : null,
    reveal: member.reveal ?? '',
    map: member.map ?? '',
    mapStage: member.map_stage ?? '',
    panel: member.panel ?? null,
  };
}

export function castDrafts(world: Pick<StoryWorldDetail, 'cast'>): CastDraft[] {
  return world.cast.map(castDraft);
}

/** 새 인물. 단계는 하나(0 에서 시작) */
export function newCastDraft(id: string): CastDraft {
  return {
    id,
    characterId: '',
    home: '',
    schedule: [],
    display: 'stage',
    start: '0',
    stages: [{ name: '처음', at: '0' }],
    gifts: [],
    confession: null,
    reveal: '',
    map: '',
    mapStage: '',
    panel: null,
  };
}

export function addMember(cast: CastDraft[], id: string): CastDraft[] {
  return cast.length >= CAST_MAX ? cast : [...cast, newCastDraft(id)];
}

export function removeMember(cast: CastDraft[], id: string): CastDraft[] {
  return cast.filter((member) => member.id !== id);
}

/** 인물 하나를 바꾼다(그 인물의 초안을 받아 새 초안을 돌려주는 함수로) */
export function changeMember(cast: CastDraft[], id: string, change: (member: CastDraft) => CastDraft): CastDraft[] {
  return cast.map((member) => (member.id === id ? change(member) : member));
}

export function addScheduleLine(member: CastDraft): CastDraft {
  if (member.schedule.length >= SCHEDULE_MAX) return member;
  return { ...member, schedule: [...member.schedule, { slot: '', place: '', when: EMPTY_CONDITIONS }] };
}

export function changeScheduleLine(member: CastDraft, index: number, changes: Partial<ScheduleDraft>): CastDraft {
  return { ...member, schedule: member.schedule.map((line, at) => (at === index ? { ...line, ...changes } : line)) };
}

export function removeScheduleLine(member: CastDraft, index: number): CastDraft {
  return { ...member, schedule: member.schedule.filter((_, at) => at !== index) };
}

/** 단계를 더한다. 경계는 마지막 단계보다 10 크게(넘치면 100) 제안한다 */
export function addStage(member: CastDraft): CastDraft {
  if (member.stages.length >= STAGES_MAX) return member;
  const last = integerIn(member.stages.at(-1)?.at ?? '0', 0, AFFECTION_MAX) ?? 0;
  return { ...member, stages: [...member.stages, { name: '', at: String(Math.min(last + 10, AFFECTION_MAX)) }] };
}

export function changeStage(member: CastDraft, index: number, changes: Partial<StageDraft>): CastDraft {
  return { ...member, stages: member.stages.map((stage, at) => (at === index ? { ...stage, ...changes } : stage)) };
}

/** 단계를 지운다. 하나는 남긴다 */
export function removeStage(member: CastDraft, index: number): CastDraft {
  return member.stages.length <= 1 ? member : { ...member, stages: member.stages.filter((_, at) => at !== index) };
}

export function addGift(member: CastDraft, id: string): CastDraft {
  if (member.gifts.length >= GIFTS_MAX) return member;
  return { ...member, gifts: [...member.gifts, { id, item: '', change: '5', once: false }] };
}

export function changeGift(member: CastDraft, id: string, changes: Partial<Omit<GiftDraft, 'id'>>): CastDraft {
  return { ...member, gifts: member.gifts.map((gift) => (gift.id === id ? { ...gift, ...changes } : gift)) };
}

export function removeGift(member: CastDraft, id: string): CastDraft {
  return { ...member, gifts: member.gifts.filter((gift) => gift.id !== id) };
}

/** 고백을 켠다(마지막 단계에서 성공, 실패하면 계속, 10 내려가고 1 일 대기). 끄면 null */
export function toggleConfession(member: CastDraft): CastDraft {
  if (member.confession) return { ...member, confession: null };
  const stage = member.stages.at(-1)?.name.trim() ?? '';
  return { ...member, confession: { stage, when: EMPTY_CONDITIONS, onFail: 'continue', failDrop: '10', cooldownDays: '1' } };
}

export function changeConfession(member: CastDraft, changes: Partial<ConfessionDraft>): CastDraft {
  return member.confession ? { ...member, confession: { ...member.confession, ...changes } } : member;
}

/** 인물 창의 항목을 덮어쓰는가. 켜면 세계관의 기본에서 시작한다 */
export function togglePanelOverride(member: CastDraft, base: PanelField[]): CastDraft {
  return { ...member, panel: member.panel ? null : [...base] };
}

export function togglePanelField(member: CastDraft, field: PanelField): CastDraft {
  if (!member.panel) return member;
  const order: PanelField[] = ['intro', 'age', 'gender', 'affection'];
  const on = member.panel.includes(field);
  return { ...member, panel: on ? member.panel.filter((entry) => entry !== field) : order.filter((entry) => entry === field || member.panel?.includes(entry)) };
}

/** 그 인물의 단계 이름들(빈 이름은 뺀다) */
export function stageNames(member: Pick<CastDraft, 'stages'>): string[] {
  return member.stages.map((stage) => stage.name.trim()).filter((name) => name !== '');
}

type Named = { id: string; name: string };

/**
 * 조건에서 고를 거리. 장소, 물건, 시간대, 이벤트는 저장된 세계관에서, 인물은 지금 고치는 초안에서 온다
 * (인물의 이름은 고른 캐릭터의 이름이다. 고르지 않았으면 빈 이름)
 */
export function castChoices(world: Pick<StoryWorldDetail, 'places' | 'items' | 'slots' | 'events'>, cast: CastDraft[], characters: Named[]): ConditionChoices {
  const nameOf = (id: string) => characters.find((character) => character.id === id)?.name ?? '';
  return {
    places: world.places.map((place) => ({ id: place.id, name: place.name })),
    items: world.items.map((item) => ({ id: item.id, name: item.name })),
    slots: world.slots.map((slot) => ({ id: slot.id, name: slot.name })),
    events: world.events.map((event) => ({ id: event.id, name: event.name })),
    cast: cast.map((member) => ({ id: member.id, name: nameOf(member.characterId), stages: stageNames(member) })),
  };
}

function stageHints(stages: StageDraft[]): Record<number, string> {
  const hints: Record<number, string> = {};
  const seen = new Set<string>();
  let previous = -1;
  stages.forEach((stage, index) => {
    const name = stage.name.trim();
    const at = integerIn(stage.at, 0, AFFECTION_MAX);
    if (name === '') hints[index] = '이름을 적어 주세요.';
    else if (name.length > STAGE_NAME_MAX) hints[index] = `이름은 ${STAGE_NAME_MAX}자까지입니다.`;
    else if (seen.has(name)) hints[index] = '같은 이름의 단계가 이미 있습니다.';
    else if (at === null) hints[index] = `경계는 0~${AFFECTION_MAX} 사이의 정수입니다.`;
    else if (index === 0 && at !== 0) hints[index] = '첫 단계는 0 에서 시작합니다.';
    else if (index > 0 && at <= previous) hints[index] = '경계는 위의 단계보다 커야 합니다.';
    seen.add(name);
    if (at !== null) previous = at;
  });
  return hints;
}

export type MemberHints = {
  character?: string;
  home?: string;
  start?: string;
  mapStage?: string;
  schedule: Record<number, string>;
  scheduleWhen: Record<number, Record<number, string>>;
  stages: Record<number, string>;
  gifts: Record<string, string>;
  confession?: string;
  confessionWhen: Record<number, string>;
};

function scheduleHint(line: ScheduleDraft, choices: ConditionChoices): string | undefined {
  if (line.slot === '' || line.place === '') return '시간대와 장소를 골라 주세요.';
  if (!choices.slots.some((slot) => slot.id === line.slot)) return '없는 시간대입니다. 다시 골라 주세요.';
  if (!choices.places.some((place) => place.id === line.place)) return '없는 장소입니다. 다시 골라 주세요.';
  return undefined;
}

function giftHint(gift: GiftDraft, items: Named[]): string | undefined {
  if (gift.item === '') return '물건을 골라 주세요.';
  if (!items.some((item) => item.id === gift.item)) return '없는 물건입니다. 다시 골라 주세요.';
  const change = integerIn(gift.change, -GIFT_CHANGE_MAX, GIFT_CHANGE_MAX);
  if (change === null) return `변화는 -${GIFT_CHANGE_MAX}~${GIFT_CHANGE_MAX} 사이의 정수입니다.`;
  return change === 0 ? '0 은 호감도를 바꾸지 않습니다.' : undefined;
}

function confessionHint(confession: ConfessionDraft, stages: string[]): string | undefined {
  if (!stages.includes(confession.stage)) return '성공하는 단계를 골라 주세요.';
  if (confession.onFail === 'end') return undefined;
  if (integerIn(confession.failDrop, 0, AFFECTION_MAX) === null) return `내려가는 값은 0~${AFFECTION_MAX} 사이의 정수입니다.`;
  if (integerIn(confession.cooldownDays, 1, COOLDOWN_MAX) === null) return `다시 못 하는 날은 1~${COOLDOWN_MAX} 사이의 정수입니다.`;
  return undefined;
}

function memberHints(member: CastDraft, earlier: CastDraft[], choices: ConditionChoices, characters: Named[]): MemberHints {
  const hints: MemberHints = { schedule: {}, scheduleWhen: {}, stages: stageHints(member.stages), gifts: {}, confessionWhen: {} };
  if (member.characterId === '') hints.character = '캐릭터를 골라 주세요.';
  else if (!characters.some((character) => character.id === member.characterId)) hints.character = '게시한 내 캐릭터 목록에 없습니다. 다시 골라 주세요.';
  else if (earlier.some((other) => other.characterId === member.characterId)) hints.character = '같은 캐릭터가 이미 다른 인물입니다.';
  if (member.home !== '' && !choices.places.some((place) => place.id === member.home)) hints.home = '없는 장소입니다. 다시 골라 주세요.';
  if (integerIn(member.start, 0, AFFECTION_MAX) === null) hints.start = `처음 값은 0~${AFFECTION_MAX} 사이의 정수입니다.`;
  const stages = stageNames(member);
  if (member.map === 'stage' && !stages.includes(member.mapStage)) hints.mapStage = '지도에 보이기 시작하는 단계를 골라 주세요.';
  member.schedule.forEach((line, index) => {
    const found = scheduleHint(line, choices);
    if (found) hints.schedule[index] = found;
    const when = conditionsHints(line.when, choices);
    if (Object.keys(when).length > 0) hints.scheduleWhen[index] = when;
  });
  for (const gift of member.gifts) {
    const found = giftHint(gift, choices.items);
    if (found) hints.gifts[gift.id] = found;
  }
  if (member.confession) {
    const found = confessionHint(member.confession, stages);
    if (found) hints.confession = found;
    hints.confessionWhen = conditionsHints(member.confession.when, choices);
  }
  return hints;
}

/** 인물마다(id → 문제) */
export function castHints(cast: CastDraft[], choices: ConditionChoices, characters: Named[]): Record<string, MemberHints> {
  const hints: Record<string, MemberHints> = {};
  cast.forEach((member, index) => {
    hints[member.id] = memberHints(member, cast.slice(0, index), choices, characters);
  });
  return hints;
}

export function memberHasHints(hints: MemberHints): boolean {
  return (
    Boolean(hints.character || hints.home || hints.start || hints.mapStage || hints.confession) ||
    [hints.schedule, hints.scheduleWhen, hints.stages, hints.gifts, hints.confessionWhen].some((group) => Object.keys(group).length > 0)
  );
}

export function hasCastHints(hints: Record<string, MemberHints>): boolean {
  return Object.values(hints).some(memberHasHints);
}

function toMember(member: CastDraft): StoryWorldCast {
  const confession = member.confession;
  return {
    id: member.id,
    character_id: member.characterId,
    home: member.home === '' ? null : member.home,
    schedule: member.schedule.map((line) => ({ slot: line.slot, place: line.place, when: toConditions(line.when) })),
    affection: {
      display: member.display,
      start: integerIn(member.start, 0, AFFECTION_MAX) ?? 0,
      stages: member.stages.map((stage) => ({ name: stage.name.trim(), at: integerIn(stage.at, 0, AFFECTION_MAX) ?? 0 })),
      gifts: member.gifts.map((gift) => ({ id: gift.id, item: gift.item, change: integerIn(gift.change, -GIFT_CHANGE_MAX, GIFT_CHANGE_MAX) ?? 0, once: gift.once })),
    },
    confession: confession
      ? {
          stage: confession.stage,
          when: toConditions(confession.when),
          on_fail: confession.onFail,
          fail_drop: integerIn(confession.failDrop, 0, AFFECTION_MAX) ?? 0,
          cooldown_days: integerIn(confession.cooldownDays, 1, COOLDOWN_MAX) ?? 1,
        }
      : null,
    reveal: member.reveal === '' ? null : member.reveal,
    map: member.map === '' ? null : member.map,
    map_stage: member.map === 'stage' ? member.mapStage : null,
    panel: member.panel,
  };
}

/** 인물 탭의 칸만 보낸다. 힌트가 없을 때만 부른다 */
export function toCastBody(cast: CastDraft[]): StoryWorldUpdate {
  return { cast: cast.map(toMember) };
}
