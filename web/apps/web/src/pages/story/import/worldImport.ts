// web/apps/web/src/pages/story/import/worldImport.ts
// "JSON 으로 세계관 넣기"의 순수한 함수. 붙여 넣은 글을 읽고, 인물마다 고른 내 캐릭터를 끼우고, 실패를 보일 줄로 바꾼다.
// 칸의 검사는 asset 서버가 한다(WorldCreate, 게시 검사). 화면은 JSON 인지와 인물마다 캐릭터를 골랐는지만 본다.

import { ApiError, isInputError, NetworkError } from '../../../api/errors';
import { worldProblemLine, worldWarningText } from '../studio/worldPublishText';

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

export function warningText(name: string): string {
  return worldWarningText(name);
}

/** 만들기나 게시가 되지 않은 까닭들. 한 줄씩 */
export function describeImportProblem(error: unknown): string[] {
  if (error instanceof NetworkError) return ['서버에 닿지 못했습니다. 연결을 확인하고 다시 시도하세요.'];
  if (!(error instanceof ApiError)) return ['처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.'];
  if (error.code === 'operator_only') return ['세계관은 지금 운영자만 만듭니다.'];
  if (error.code === 'character_not_owned') return ['내 캐릭터가 아닌 것을 고른 인물이 있습니다. 인물마다 내 캐릭터를 골라 주세요.'];
  if (error.status === 409 && Array.isArray(error.body.problems)) {
    return error.body.problems.map((name) => (typeof name === 'string' ? worldProblemLine(name).text : String(name)));
  }
  if (isInputError(error)) return Object.entries(error.fields).map(([field, messages]) => `${field}: ${messages.join(' ')}`);
  if (error.status === 404) return ['세계관을 찾지 못했습니다. 지웠거나 내 것이 아닙니다.'];
  return [error.message || '처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.'];
}
