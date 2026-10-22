// web/apps/web/src/hooks/usePublicNames.ts
// 화면에 보이는 공개 ID 들의 닉네임을 한 번에 읽는다(#532). 쪽마다 한 번 묻는다(한 번에 100개까지).
// 이름을 읽지 못해도 목록은 그대로 보인다. 이름만 빈다.

import { useQueries } from '@tanstack/react-query';
import { fetchPublicNames, PUBLIC_NAMES_LIMIT, type NameBook } from '../api/publicNames';

/** 이름이 없을 때 보일 글. 탈퇴했거나 막은 계정이다 */
export const UNKNOWN_PERSON = '탈퇴한 사용자';

/** 공개 ID → 보일 이름. 아직 읽는 중이거나 읽지 못했으면 undefined */
export type NameLookup = (publicId: string) => string | undefined;

/** groups: 쪽마다의 공개 ID. 같은 ID 가 여러 번 있어도 된다 */
export function usePublicNames(groups: string[][]): NameLookup {
  const results = useQueries({
    queries: groups.map((ids) => {
      const unique = uniqueIds(ids);
      return {
        queryKey: ['auth', 'public-names', unique],
        queryFn: ({ signal }: { signal: AbortSignal }) => fetchPublicNames(unique, signal),
        enabled: unique.length > 0,
        staleTime: 60 * 1000,
      };
    }),
  });
  const books = results.map((result) => result.data).filter((book): book is NameBook => book !== undefined);
  return (publicId) => nameIn(books, publicId);
}

/** 정렬해 겹친 것을 뺀다. 같은 사람들이면 같은 열쇠가 된다. 상한을 넘는 것은 자른다 */
export function uniqueIds(ids: string[]): string[] {
  return [...new Set(ids)].sort().slice(0, PUBLIC_NAMES_LIMIT);
}

function nameIn(books: NameBook[], publicId: string): string | undefined {
  for (const book of books) {
    if (book.has(publicId)) return book.get(publicId) ?? UNKNOWN_PERSON;
  }
  return undefined;
}
