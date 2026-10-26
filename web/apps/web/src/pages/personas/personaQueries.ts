// web/apps/web/src/pages/personas/personaQueries.ts
// 내 페르소나(C4). 목록 하나를 고치기, 기본으로 두기, 지우기, C2 의 시작이 함께 쓴다. 바꾸면 목록을 다시 읽는다.

import { queryOptions } from '@tanstack/react-query';
import { isClientError } from '../../api/http';
import { fetchPersona, fetchPersonas } from '../../api/personas';

export function personasKey() {
  return ['asset', 'personas'] as const;
}

export function personasQuery() {
  return queryOptions({ queryKey: personasKey(), queryFn: ({ signal }) => fetchPersonas(signal) });
}

export function personaQuery(id: string) {
  return queryOptions({
    queryKey: [...personasKey(), id],
    queryFn: ({ signal }) => fetchPersona(id, signal),
    retry: (count, error) => !isClientError(error) && count < 2,
  });
}
