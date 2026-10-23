// web/apps/web/src/pages/trpg/studio/useAssetActions.ts
// 재료 하나를 만들고, 고치고, 지운다(B9). 재료의 종류마다 보내는 함수만 다르다.
// 받은 것은 그 낱개의 읽기에 바로 넣고, 목록은 다시 읽는다(제목과 고친 때가 바뀐다). 지우면 낱개의 읽기를 버린다.

import { useQueryClient } from '@tanstack/react-query';
import { deleteAsset, type StudioKind } from '../../../api/studio';
import { describeDeleteProblem, describeSaveProblem } from './studioProblem';
import { assetDetailKey, assetListKey } from './studioQueries';
import { useSending } from './useSending';

type Saved = { id: string };

/** 받은 재료를 낱개의 읽기에 넣고 목록을 무른다 */
function useRemember(kind: StudioKind) {
  const queryClient = useQueryClient();
  return (asset: Saved) => {
    queryClient.setQueryData(assetDetailKey(kind, asset.id), asset);
    void queryClient.invalidateQueries({ queryKey: assetListKey(kind) });
  };
}

/** 만들기나 고치기. send 로 보낼 것을 넘기면 결과를 기억하고 돌려준다 */
export function useSaveAsset<T extends Saved>(kind: StudioKind) {
  const sending = useSending();
  const remember = useRemember(kind);
  async function save(request: () => Promise<T>): Promise<T | null> {
    const saved = await sending.send(request, (error) => describeSaveProblem(error, kind));
    if (saved) remember(saved);
    return saved;
  }
  return { busy: sending.busy, problem: sending.problem, save };
}

export function useDeleteAsset(kind: StudioKind, assetId: string) {
  const queryClient = useQueryClient();
  const sending = useSending();
  /** 지웠으면 true. 낱개의 읽기를 버리고 목록을 무른다 */
  async function remove(): Promise<boolean> {
    const done = await sending.send(async () => {
      await deleteAsset(kind, assetId);
      return true;
    }, (error) => describeDeleteProblem(error, kind));
    if (!done) return false;
    queryClient.removeQueries({ queryKey: assetDetailKey(kind, assetId) });
    void queryClient.invalidateQueries({ queryKey: assetListKey(kind) });
    return true;
  }
  return { busy: sending.busy, problem: sending.problem, remove };
}
