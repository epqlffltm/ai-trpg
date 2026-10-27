// web/apps/web/src/pages/story/storyCastView.ts
// 그림 창과 인물 창(D5)에 보일 것. 세션의 세계관 칸(view)과 상태만 받는 순수한 함수다.
// 무엇을 보일지(호감도의 숫자나 단계, 인물 창의 항목)는 제작자가 정했고 서버가 그대로 걸러 보낸다. 화면은 받은 것만 그린다.

import type { StoryMessage, StoryProgress, StorySavedMessage, StoryState, StoryView, StoryViewCast } from '../../api/story';
import { itemName, eventName } from './storyWorld';

const MINUTES_PER_DAY = 1440;

/** 지금 장소와 시간대의 배경. 시간대의 배경이 없으면 장소의 그림, 그것도 없으면 null */
export function backgroundOf(view: Pick<StoryView, 'places'>, state: Pick<StoryState, 'place' | 'slot'>): string | null {
  const place = view.places.find((entry) => entry.id === state.place);
  if (!place) return null;
  return place.backgrounds[state.slot] ?? place.image_id ?? null;
}

type Scene = { title: string; imageId: string };

/**
 * 그림 창에 띄울 장면의 일러스트. 끝의 답이 답한 말(받는 중이면 답할 말)에 이벤트나 엔딩이 적혀 있고 그림이 있으면 그것이다.
 * 엔딩이 이벤트보다 먼저다. 없으면 null(배경과 인물을 그린다)
 */
export function sceneOf(
  view: Pick<StoryView, 'events' | 'endings'>,
  messages: StoryMessage[],
  answering: Pick<StorySavedMessage, 'event_id' | 'ending_id'> | null,
): Scene | null {
  const source = answering ?? answeredMessage(messages);
  if (!source) return null;
  const ending = source.ending_id ? view.endings.find((entry) => entry.id === source.ending_id) : undefined;
  if (ending?.image_id) return { title: ending.name ?? '엔딩', imageId: ending.image_id };
  const event = source.event_id ? view.events.find((entry) => entry.id === source.event_id) : undefined;
  return event?.image_id ? { title: event.name, imageId: event.image_id } : null;
}

function answeredMessage(messages: StoryMessage[]): StoryMessage | null {
  const last = messages.at(-1);
  if (last?.role !== 'assistant') return null;
  return messages.find((message) => message.id === last.parent_id) ?? null;
}

/** 인물의 그림. 기본 표정(빈 글)의 스프라이트, 없으면 대표 그림. 실루엣이면 서버가 비워 보낸다 */
export function portraitOf(cast: Pick<StoryViewCast, 'sprites' | 'image_id'> | undefined): string | null {
  if (!cast) return null;
  return cast.sprites.find((sprite) => sprite.expression === '')?.image_id ?? cast.image_id ?? null;
}

/** 호감도의 단계. 그 값 이하에서 가장 높은 단계 */
export function stageOf(stages: { name: string; at: number }[], value: number): string | null {
  return [...stages].sort((a, b) => b.at - a.at).find((stage) => value >= stage.at)?.name ?? null;
}

/** 인물 창의 호감도 한 줄. 제작자가 보이지 않게 했으면(affection 이 없다) null */
export function affectionText(cast: Pick<StoryViewCast, 'affection'>, value: number | undefined): string | null {
  if (!cast.affection || value === undefined) return null;
  if (cast.affection.display === 'number') return `호감도 ${value}`;
  const stage = stageOf(cast.affection.stages, value);
  return stage ? `호감도: ${stage}` : null;
}

/** 시각(1일째 0시부터의 분)을 "3일째 18시" 로 */
export function clockText(minutes: number): string {
  const day = Math.floor(minutes / MINUTES_PER_DAY) + 1;
  const hour = Math.floor((minutes % MINUTES_PER_DAY) / 60);
  return `${day}일째 ${hour}시`;
}

/** 고백 대기. 다시 고백할 수 있는 때가 지금보다 뒤면 그 시각, 아니면 null */
export function coolingText(cast: Pick<StoryViewCast, 'affection'>, now: number): string | null {
  const until = cast.affection?.cooling_until;
  return typeof until === 'number' && until > now ? `${clockText(until)}부터 다시 고백할 수 있습니다` : null;
}

/** 인물 창의 소개 한 줄(나이, 성별). 제작자가 고른 항목만 */
export function profileLine(cast: Pick<StoryViewCast, 'age' | 'gender'>): string {
  return [cast.age, cast.gender].filter(Boolean).join(' · ');
}

/** 건넨 선물과 함께 본 이벤트의 이름 */
export function giftNames(view: StoryView, cast: Pick<StoryViewCast, 'affection'>): string[] {
  return (cast.affection?.gifts ?? []).map((id) => itemName(view, id));
}

export function eventNames(view: StoryView, cast: Pick<StoryViewCast, 'events'>): string[] {
  return cast.events.map((id) => eventName(view, id));
}

/** 세션 목록의 진행 한 줄. "3일째 · D-12", "끝: 봄의 약속", "후일담 · 5일째" */
export function progressLine(progress: StoryProgress | null | undefined): string | null {
  if (!progress) return null;
  if (progress.ending !== null && !progress.epilogue) return `끝: ${progress.ending_name ?? progress.ending}`;
  const left = typeof progress.deadline_days === 'number' && !progress.epilogue ? Math.max(0, progress.deadline_days - progress.day) : null;
  return [progress.epilogue ? '후일담' : null, `${progress.day}일째`, left !== null ? `D-${left}` : null].filter(Boolean).join(' · ');
}
