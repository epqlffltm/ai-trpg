// web/apps/web/src/pages/story/import/worldImport.ts
// "JSON 으로 세계관 넣기"의 순수한 함수. 붙여 넣은 글을 읽고, 인물마다 고른 내 캐릭터를 끼우고, 실패를 보일 줄로 바꾼다.
// 칸의 검사는 asset 서버가 한다(WorldCreate, 게시 검사). 화면은 JSON 인지와 인물마다 캐릭터를 골랐는지만 본다.

import { ApiError, isInputError, NetworkError } from '../../../api/errors';

export type ParsedWorld = { world: Record<string, unknown> } | { error: string };
export type CastSlot = { index: number; id: string };

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/** 붙여 넣은 글을 세계관 하나(객체)로 읽는다 */
export function parseWorld(text: string): ParsedWorld {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch (error) {
    return { error: `JSON 으로 읽지 못했습니다. ${error instanceof Error ? error.message : ''}`.trim() };
  }
  return isObject(value) ? { world: value } : { error: '세계관 하나(중괄호로 감싼 객체)를 넣어 주세요.' };
}

/** 캐릭터를 끼울 인물들. cast 의 차례와 인물의 id */
export function castSlots(world: Record<string, unknown>): CastSlot[] {
  const cast = Array.isArray(world.cast) ? world.cast : [];
  return cast.flatMap((member, index) => (isObject(member) && typeof member.id === 'string' ? [{ index, id: member.id }] : []));
}

/** 인물마다 고른 캐릭터를 끼운 세계관. 고르지 않은 인물은 그대로 둔다(서버가 거절한다) */
export function withCharacters(world: Record<string, unknown>, chosen: Record<number, string>): Record<string, unknown> {
  if (!Array.isArray(world.cast)) return world;
  const cast = world.cast.map((member: unknown, index) => (isObject(member) && chosen[index] ? { ...member, character_id: chosen[index] } : member));
  return { ...world, cast };
}

/** 모든 인물에 캐릭터를 골랐는가 */
export function allChosen(slots: CastSlot[], chosen: Record<number, string>): boolean {
  return slots.every((slot) => Boolean(chosen[slot.index]));
}

/** 게시를 막는 것(asset-server/app/worlds/publishing.py 의 Problem) */
const PROBLEMS: Record<string, string> = {
  start_place_missing: '장소가 없거나 시작 장소를 고르지 않았습니다.',
  start_slot_missing: '시작 시간대가 없는 시간대입니다.',
  cast_empty: '인물이 하나도 없습니다.',
  place_missing: '없는 장소를 가리키는 길, 일정, 조건, 효과가 있습니다.',
  slot_missing: '없는 시간대를 가리키는 배경, 일정, 조건이 있습니다.',
  item_missing: '없는 물건을 가리키는 소지품, 선물, 조건, 효과가 있습니다.',
  cast_target_missing: '없는 인물을 가리키는 조건, 효과, 장면, 엔딩이 있습니다.',
  event_missing: '없는 이벤트를 가리키는 조건이나 엔딩이 있습니다.',
  stage_missing: '인물에 없는 호감도의 단계를 가리킵니다(조건, 지도, 고백).',
  character_missing: '인물이 가리킨 캐릭터가 없습니다. 지웠거나 내 것이 아닙니다.',
  character_unpublished: '인물이 가리킨 캐릭터를 게시한 적이 없습니다. 캐릭터를 먼저 게시해 주세요.',
  character_rating_too_high: '전체이용가 세계관에 성인 등급 캐릭터가 있습니다.',
  lorebook_missing: '가리킨 로어북이 없습니다.',
  lorebook_unpublished: '가리킨 로어북을 게시한 적이 없습니다.',
  ending_missing: '고백 성공, 끝내는 고백 실패, 기한 같은 시작마다 조건이 빈 엔딩이 하나는 있어야 합니다.',
  image_not_owned: '내가 올리지 않은 그림이 있습니다.',
};

/** 게시는 되지만 알리는 것 */
const WARNINGS: Record<string, string> = {
  place_unreachable: '시작 장소에서 길로 닿지 않는 장소가 있습니다.',
  event_unreachable: '열릴 수 없는 이벤트가 있습니다.',
  cast_never_present: '어디에도 나오지 않는 인물이 있습니다.',
  ending_unreachable: '고를 일이 없는 엔딩이 있습니다.',
};

export function warningText(name: string): string {
  return WARNINGS[name] ?? name;
}

/** 만들기나 게시가 되지 않은 까닭들. 한 줄씩 */
export function describeImportProblem(error: unknown): string[] {
  if (error instanceof NetworkError) return ['서버에 닿지 못했습니다. 연결을 확인하고 다시 시도하세요.'];
  if (!(error instanceof ApiError)) return ['처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.'];
  if (error.code === 'operator_only') return ['세계관은 지금 운영자만 만듭니다.'];
  if (error.code === 'character_not_owned') return ['내 캐릭터가 아닌 것을 고른 인물이 있습니다. 인물마다 내 캐릭터를 골라 주세요.'];
  if (error.status === 409 && Array.isArray(error.body.problems)) {
    return error.body.problems.map((name) => (typeof name === 'string' ? (PROBLEMS[name] ?? name) : String(name)));
  }
  if (isInputError(error)) return Object.entries(error.fields).map(([field, messages]) => `${field}: ${messages.join(' ')}`);
  if (error.status === 404) return ['세계관을 찾지 못했습니다. 지웠거나 내 것이 아닙니다.'];
  return [error.message || '처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.'];
}
