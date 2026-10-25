// web/apps/web/src/pages/chat/conversation/conversationView.ts
// 대화(C3)에 보이는 글과 그림을 고른다. 순수한 함수다. 값은 모두 대화 읽기(GET /conversations/{id})가 준 것이다.
// 상태(장소, 시각, 호감도, 그림)는 서버가 가지의 끝에서 고른다. 화면은 같은 규칙을 다시 짜지 않고 이름만 붙인다.

import type { ConversationDetail, ConversationMessage, ConversationState } from '../../../api/types';

type CharacterDocument = ConversationDetail['character']['document'];
type Change = NonNullable<ConversationMessage['changes']>[number];

const TIME_OF_DAY: Record<ConversationState['clock']['time_of_day'], string> = {
  dawn: '새벽',
  morning: '아침',
  day: '낮',
  evening: '저녁',
  night: '밤',
};

/** "2일째 저녁 18:30" */
export function clockLabel(clock: ConversationState['clock']): string {
  const time = `${String(clock.hour).padStart(2, '0')}:${String(clock.minute).padStart(2, '0')}`;
  return `${clock.day}일째 ${TIME_OF_DAY[clock.time_of_day]} ${time}`;
}

/** 판의 장소 이름. 판에 없으면 받은 id 그대로 */
export function placeName(document: Pick<CharacterDocument, 'places'>, placeId: string): string {
  return (document.places ?? []).find((place) => place.id === placeId)?.name ?? placeId;
}

/** 판의 물건 이름. 판에 없으면 받은 id 그대로 */
export function itemName(document: Pick<CharacterDocument, 'items'>, itemId: string): string {
  return (document.items ?? []).find((item) => item.id === itemId)?.name ?? itemId;
}

/** 머리의 호감도. 숫자로 보이면 "호감 37/100", 단계로 보이면 "호감: 친구(2/4)". 게이지는 0~100 */
export function affectionView(affection: ConversationState['affection']): { label: string; percent: number } | null {
  if (!affection) return null;
  if (affection.display === 'number' && affection.value !== null) return { label: `호감 ${affection.value}/100`, percent: affection.value };
  const percent = affection.stages > 0 ? Math.round(((affection.stage_index + 1) / affection.stages) * 100) : 0;
  return { label: `호감: ${affection.stage}(${affection.stage_index + 1}/${affection.stages})`, percent };
}

/** 답에 실린 받아들인 변화를 한 줄씩 */
export function changeLines(changes: Change[], document: Pick<CharacterDocument, 'places' | 'items'>): string[] {
  return changes.map((change) => {
    if (change.kind === 'affection') {
      const amount = change.delta === null ? '' : `(${change.delta > 0 ? '+' : ''}${change.delta})`;
      return change.rising ? `호감이 올랐다${amount}` : `호감이 내렸다${amount}`;
    }
    if (change.kind === 'gift') return `${itemName(document, change.item)}을(를) 받았다`;
    return `${placeName(document, change.place)}에 함께 갔다(${change.minutes}분)`;
  });
}

/** 대안 사이의 자리. 대안이 하나면 null. "< 2/3 >" 의 앞뒤 말 */
export function alternativeView(message: Pick<ConversationMessage, 'id' | 'alternatives'>): { position: number; count: number; previous: string | null; next: string | null } | null {
  const ids = message.alternatives;
  const index = ids.indexOf(message.id);
  if (ids.length < 2 || index < 0) return null;
  return { position: index + 1, count: ids.length, previous: ids[index - 1] ?? null, next: ids[index + 1] ?? null };
}

/** 말한 이의 이름. 행동 말은 이름이 없다(서버가 쓴 글이다) */
export function speakerName(role: string, detail: Pick<ConversationDetail, 'persona' | 'character'>): string | null {
  if (role === 'user') return detail.persona?.name || '나';
  if (role === 'assistant') return detail.character.document.name;
  return null;
}

/** 끝에서 할 수 있는 일. 끝이 사람의 말이면 답 받기, 상대의 답이면 다시 생성(인사말은 빼고), 끊긴 답이면 이어서 */
export function tailActions(messages: ConversationMessage[]): { answer: string | null; regenerate: string | null; continueFrom: string | null } {
  const last = messages.at(-1);
  if (!last) return { answer: null, regenerate: null, continueFrom: null };
  if (last.role !== 'assistant') return { answer: last.id, regenerate: null, continueFrom: null };
  return {
    answer: null,
    regenerate: last.parent_id === null ? null : last.id,
    continueFrom: last.status === 'partial' ? last.id : null,
  };
}

/** 끝의 답이 낸 다음 답 추천 */
export function tailSuggestions(messages: ConversationMessage[]): string[] {
  const last = messages.at(-1);
  return last?.role === 'assistant' ? (last.suggestions ?? []) : [];
}

/**
 * 그림 창에 띄울 것. 끝의 답이 답한 말에 이벤트 씬이 붙어 있으면 그 씬이 배경과 캐릭터를 대신한다.
 * 아니면 상태의 배경과 캐릭터 그림(없으면 대표 그림). 답을 받는 중이면 답할 말과 받은 표정을 먼저 본다
 */
export function pictureOf(
  detail: Pick<ConversationDetail, 'messages' | 'state' | 'character'>,
  streaming: { answering: Pick<ConversationMessage, 'event_scene'> | null; sprite: string | null } | null,
): { scene: { title: string; imageId: string } | null; background: string | null; sprite: string | null } {
  const document = detail.character.document;
  const sceneId = streaming?.answering ? (streaming.answering.event_scene ?? null) : answeredScene(detail.messages);
  const scene = sceneId ? (document.event_scenes ?? []).find((entry) => entry.id === sceneId) : undefined;
  return {
    scene: scene ? { title: scene.title, imageId: scene.image_id } : null,
    background: detail.state.background,
    sprite: streaming?.sprite ?? detail.state.sprite ?? document.image_id,
  };
}

function answeredScene(messages: ConversationMessage[]): string | null {
  const last = messages.at(-1);
  if (last?.role !== 'assistant') return null;
  return messages.find((message) => message.id === last.parent_id)?.event_scene ?? null;
}
