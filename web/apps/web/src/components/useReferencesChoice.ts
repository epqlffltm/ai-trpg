// web/apps/web/src/components/useReferencesChoice.ts
// 대화·세션의 참고 자료 켜기를 서버에 적는다(#1338). 읽어 둔 대화·세션의 references_enabled 칸만 바꿔 다시 읽지 않는다.
// chat 의 대화(C3)와 story 의 세션(D2)이 함께 쓴다. 부르는 주소와 읽어 둔 열쇠만 다르다.

import { useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { putQueryData } from '../queryClient';

type Switched = { enabled: boolean };
type WithReferences = { references_enabled: boolean };

export function useReferencesChoice<T extends WithReferences>(queryKey: QueryKey, choose: (enabled: boolean) => Promise<Switched>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: choose,
    onSuccess: async ({ enabled }) => {
      await putQueryData(queryClient, queryKey, (current: T | undefined) => (current ? { ...current, references_enabled: enabled } : current));
    },
  });
}
