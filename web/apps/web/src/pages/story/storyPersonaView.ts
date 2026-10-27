// web/apps/web/src/pages/story/storyPersonaView.ts
// 장면의 페르소나에 보일 것. 순수한 함수다.

import type { StoryPersona } from '../../api/story';

/** 머리에 보일 페르소나의 이름. 없으면 "페르소나 없음" */
export function personaLabel(persona: Pick<StoryPersona, 'name'> | null | undefined): string {
  return persona ? persona.name : '페르소나 없음';
}

/** 세션에 가져온 뒤 그 페르소나의 설정이 바뀌었나(내 목록의 판이 더 크다). 목록에 없거나 세션에 페르소나가 없으면 false */
export function staleRevision(personas: { id: string; revision: number }[], persona: Pick<StoryPersona, 'id' | 'revision'> | null | undefined): boolean {
  if (!persona) return false;
  const mine = personas.find((entry) => entry.id === persona.id);
  return mine !== undefined && mine.revision > persona.revision;
}
