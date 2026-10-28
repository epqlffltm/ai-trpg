// web/apps/web/src/pages/story/studio/worldProgressForm.ts
// 세계관의 진행 탭의 입력. 순수한 함수다. 규칙은 서버와 같다(asset-server/app/worlds/schemas.py).
//
//   - 시간대: 1~8개. id 는 화면이 붙인다. 이름(20자)은 하나씩, 시작 시각(0~23시)은 차례로 커진다.
//     시간대를 지우면 시작 시간대였을 때 비운다(비우면 첫 시간대에서 시작한다). 그 시간대의 배경과 일정은 게시 점검이 알린다
//   - 기한: 비우면 없음, 있으면 1~365 일. 엔딩 뒤: 끝(읽기만) 또는 후일담
//   - 보이기의 기본: 인물의 공개(보임, 실루엣, 숨김), 지도의 인물(보임, 숨김, 호감도 단계 이상), 인물 창의 항목. 인물마다 덮어쓴다
//   - 시작 장소와 시작 소지품은 지도·물건 탭에서 저장한 것에서 고른다. 소지품은 물건마다 한 줄, 수는 1~99

import type { StoryWorldDetail, StoryWorldShow, StoryWorldSlot, StoryWorldUpdate } from '../../../api/storyWorlds';

export const SLOTS_MIN = 1;
export const SLOTS_MAX = 8;
export const SLOT_NAME_MAX = 20;
export const DEADLINE_MAX = 365;
export const START_ITEMS_MAX = 20;
export const START_ITEM_MAX_COUNT = 99;

export type SlotDraft = { id: string; name: string; startHour: string };
export type StartItemDraft = { item: string; count: string };
export type AfterEnding = StoryWorldDetail['after_ending'];

export type ProgressDraft = {
  slots: SlotDraft[];
  startSlot: string;
  deadline: string;
  afterEnding: AfterEnding;
  show: StoryWorldShow;
  startPlace: string;
  startItems: StartItemDraft[];
};

export function progressDraft(world: StoryWorldDetail): ProgressDraft {
  return {
    slots: world.slots.map((slot) => ({ id: slot.id, name: slot.name, startHour: String(slot.start_hour) })),
    startSlot: world.start_slot ?? '',
    deadline: world.deadline_days === null ? '' : String(world.deadline_days),
    afterEnding: world.after_ending,
    show: world.show,
    startPlace: world.start_place ?? '',
    startItems: world.start_items.map((start) => ({ item: start.item, count: String(start.count ?? 1) })),
  };
}

export function addSlot(draft: ProgressDraft, id: string): ProgressDraft {
  if (draft.slots.length >= SLOTS_MAX) return draft;
  return { ...draft, slots: [...draft.slots, { id, name: '', startHour: '' }] };
}

export function changeSlot(draft: ProgressDraft, id: string, changes: Partial<Omit<SlotDraft, 'id'>>): ProgressDraft {
  return { ...draft, slots: draft.slots.map((slot) => (slot.id === id ? { ...slot, ...changes } : slot)) };
}

/** 시간대를 지운다. 하나는 남긴다. 시작 시간대였으면 비운다 */
export function removeSlot(draft: ProgressDraft, id: string): ProgressDraft {
  if (draft.slots.length <= SLOTS_MIN) return draft;
  return { ...draft, slots: draft.slots.filter((slot) => slot.id !== id), startSlot: draft.startSlot === id ? '' : draft.startSlot };
}

export function addStartItem(draft: ProgressDraft): ProgressDraft {
  if (draft.startItems.length >= START_ITEMS_MAX) return draft;
  return { ...draft, startItems: [...draft.startItems, { item: '', count: '1' }] };
}

export function changeStartItem(draft: ProgressDraft, index: number, changes: Partial<StartItemDraft>): ProgressDraft {
  return { ...draft, startItems: draft.startItems.map((start, at) => (at === index ? { ...start, ...changes } : start)) };
}

export function removeStartItem(draft: ProgressDraft, index: number): ProgressDraft {
  return { ...draft, startItems: draft.startItems.filter((_, at) => at !== index) };
}

/** 인물 창의 항목 하나를 켜고 끈다. 차례는 서버의 차례(intro, age, gender, affection)를 지킨다 */
export function togglePanel(show: StoryWorldShow, field: StoryWorldShow['panel'][number]): StoryWorldShow {
  const on = show.panel.includes(field);
  const order: StoryWorldShow['panel'] = ['intro', 'age', 'gender', 'affection'];
  const next = on ? show.panel.filter((entry) => entry !== field) : order.filter((entry) => entry === field || show.panel.includes(entry));
  return { ...show, panel: next };
}

/** 0~23 의 정수면 그 수, 아니면 null */
export function hourOf(text: string): number | null {
  const trimmed = text.trim();
  if (!/^\d{1,2}$/.test(trimmed)) return null;
  const hour = Number(trimmed);
  return hour < 24 ? hour : null;
}

/** 1~max 의 정수면 그 수, 아니면 null */
export function countOf(text: string, max: number): number | null {
  const trimmed = text.trim();
  if (!/^\d{1,3}$/.test(trimmed)) return null;
  const count = Number(trimmed);
  return count >= 1 && count <= max ? count : null;
}

function slotHint(slot: SlotDraft, earlier: SlotDraft[]): Record<string, string> {
  const found: Record<string, string> = {};
  const name = slot.name.trim();
  if (name === '') found.name = '이름을 적어 주세요.';
  else if (name.length > SLOT_NAME_MAX) found.name = `이름은 ${SLOT_NAME_MAX}자까지입니다.`;
  else if (earlier.some((other) => other.name.trim() === name)) found.name = '같은 이름의 시간대가 이미 있습니다.';
  const hour = hourOf(slot.startHour);
  const before = earlier.at(-1);
  const previous = before ? hourOf(before.startHour) : null;
  if (hour === null) found.startHour = '시작 시각은 0~23 사이의 정수(시)입니다.';
  else if (previous !== null && hour <= previous) found.startHour = '시작 시각은 앞의 시간대보다 늦어야 합니다.';
  return found;
}

function startItemHint(start: StartItemDraft, earlier: StartItemDraft[]): string | undefined {
  if (start.item === '') return '물건을 골라 주세요.';
  if (earlier.some((other) => other.item === start.item)) return '같은 물건이 이미 있습니다. 수를 늘려 주세요.';
  if (countOf(start.count, START_ITEM_MAX_COUNT) === null) return `수는 1~${START_ITEM_MAX_COUNT} 사이의 정수입니다.`;
  return undefined;
}

export type ProgressHints = { slots: Record<string, Record<string, string>>; deadline?: string; startItems: Record<number, string> };

export function progressHints(draft: ProgressDraft): ProgressHints {
  const slots: Record<string, Record<string, string>> = {};
  draft.slots.forEach((slot, index) => {
    const found = slotHint(slot, draft.slots.slice(0, index));
    if (Object.keys(found).length > 0) slots[slot.id] = found;
  });
  const startItems: Record<number, string> = {};
  draft.startItems.forEach((start, index) => {
    const found = startItemHint(start, draft.startItems.slice(0, index));
    if (found) startItems[index] = found;
  });
  const deadline = draft.deadline.trim() !== '' && countOf(draft.deadline, DEADLINE_MAX) === null ? `기한은 1~${DEADLINE_MAX} 일입니다. 비우면 기한이 없습니다.` : undefined;
  return { slots, startItems, ...(deadline ? { deadline } : {}) };
}

export function hasProgressHints(hints: ProgressHints): boolean {
  return Object.keys(hints.slots).length > 0 || Object.keys(hints.startItems).length > 0 || hints.deadline !== undefined;
}

/**
 * 진행 탭의 칸만 보낸다. 힌트가 없을 때만 부른다. 비운 시작 시간대, 기한, 시작 장소는 null 이다.
 * 시작 장소와 소지품은 가장 최근에 받은 세계관(latest)에 있는 장소와 물건만 보낸다(이 탭을 연 뒤에 지도·물건 탭에서 지웠을 수 있다)
 */
export function toProgressBody(draft: ProgressDraft, latest: Pick<StoryWorldDetail, 'places' | 'items'>): StoryWorldUpdate {
  const places = new Set(latest.places.map((place) => place.id));
  const items = new Set(latest.items.map((item) => item.id));
  const slots: StoryWorldSlot[] = draft.slots.map((slot) => ({ id: slot.id, name: slot.name.trim(), start_hour: hourOf(slot.startHour) ?? 0 }));
  return {
    slots,
    start_slot: draft.startSlot === '' ? null : draft.startSlot,
    deadline_days: draft.deadline.trim() === '' ? null : countOf(draft.deadline, DEADLINE_MAX),
    after_ending: draft.afterEnding,
    show: draft.show,
    start_place: places.has(draft.startPlace) ? draft.startPlace : null,
    start_items: draft.startItems
      .filter((start) => items.has(start.item))
      .map((start) => ({ item: start.item, count: countOf(start.count, START_ITEM_MAX_COUNT) ?? 1 })),
  };
}
