// web/apps/web/src/pages/trpg/studio/collection/useItemActions.ts
// 묶음에 담긴 것(항목, 몬스터) 하나를 더하고, 고치고, 지운다. 한 번에 하나만 보낸다.
// 끝나면 담긴 것의 목록을 다시 읽고, 묶음의 고친 때가 바뀌므로 재료의 목록도 무른다.

import { useQueryClient } from '@tanstack/react-query';
import type { StudioKind } from '../../../../api/studio';
import { describeSaveProblem } from '../studioProblem';
import { assetListKey } from '../studioQueries';
import { useSending } from '../useSending';

/** 담긴 것의 열쇠. 묶음의 낱개 열쇠 아래에 둔다 */
export function itemsKey(kind: StudioKind, assetId: string) {
  return ['trpg', 'studio', kind, 'detail', assetId, 'items'] as const;
}

export function useItemActions(kind: StudioKind, assetId: string) {
  const queryClient = useQueryClient();
  const sending = useSending();

  /** 보낸다. 되었으면 true. 담긴 것과 재료의 목록을 다시 읽는다 */
  async function run(request: () => Promise<unknown>): Promise<boolean> {
    const done = await sending.send(async () => {
      await request();
      return true;
    }, (error) => describeSaveProblem(error, kind));
    if (!done) return false;
    void queryClient.invalidateQueries({ queryKey: itemsKey(kind, assetId) });
    void queryClient.invalidateQueries({ queryKey: assetListKey(kind) });
    return true;
  }

  return { busy: sending.busy, problem: sending.problem, run };
}
