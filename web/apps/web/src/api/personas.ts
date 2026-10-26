// web/apps/web/src/api/personas.ts
// 계정 페르소나(C4, asset 서버 #565). "나"의 설정이고 TRPG, chat, story 가 함께 쓴다. 주인만 보고 고친다.
//   - 목록은 기본이 먼저, 그다음 만든 차례다. 페르소나가 있으면 늘 하나가 기본이다(처음 만든 것이 기본이 된다)
//   - 고치기는 보낸 칸만 바꾼다. 글의 칸은 빈 글로 비우고, 그림은 null 로 뗀다. 내용이 바뀌면 revision 이 오른다
//   - 지우면 기본이었을 때 가장 먼저 만든 것이 기본이 된다. 가져간 대화는 사본으로 돈다
// 실패: 409 persona_limit(한 사람에 50개까지), 422 image_not_owned(내가 올린 그림이 아니다), 422 칸의 오류, 404(남의 것, 없는 것)

import { apiRequest } from './http';
import type { Persona, PersonaCreate, PersonaUpdate } from './types';

const PERSONAS = '/api/v1/asset/personas';

export function fetchPersonas(signal?: AbortSignal): Promise<Persona[]> {
  return apiRequest<Persona[]>(PERSONAS, signal ? { signal } : {});
}

export function fetchPersona(id: string, signal?: AbortSignal): Promise<Persona> {
  return apiRequest<Persona>(`${PERSONAS}/${encodeURIComponent(id)}`, signal ? { signal } : {});
}

export function createPersona(body: PersonaCreate): Promise<Persona> {
  return apiRequest<Persona>(PERSONAS, { method: 'POST', body });
}

export function updatePersona(id: string, body: PersonaUpdate): Promise<Persona> {
  return apiRequest<Persona>(`${PERSONAS}/${encodeURIComponent(id)}`, { method: 'PATCH', body });
}

export function makeDefaultPersona(id: string): Promise<Persona> {
  return apiRequest<Persona>(`${PERSONAS}/${encodeURIComponent(id)}/default`, { method: 'PUT' });
}

export function deletePersona(id: string): Promise<void> {
  return apiRequest<void>(`${PERSONAS}/${encodeURIComponent(id)}`, { method: 'DELETE' });
}
