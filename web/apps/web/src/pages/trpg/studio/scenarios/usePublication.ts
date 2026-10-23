// web/apps/web/src/pages/trpg/studio/scenarios/usePublication.ts
// 공개할 판을 정하거나 공개를 내린다(B9 게시 탭). 받은 소개 페이지를 읽기에 넣는다.
// 공개 목록(B1)과 공개된 소개(B2)는 다음에 읽을 때 바뀐다. 이미 연 테이블은 그 테이블의 판을 그대로 쓴다.

import { useQueryClient } from '@tanstack/react-query';
import { setPublication } from '../../../../api/scenarios';
import type { ListingDetail } from '../../../../api/types';
import { useSending } from '../useSending';
import { describePublicationProblem } from './listingProblem';
import { listingKey } from './scenarioQueries';

export function usePublication(scenarioId: string) {
  const queryClient = useQueryClient();
  const sending = useSending();

  /** 바뀐 소개 페이지, 못 했으면 null. version 이 null 이면 공개를 내린다 */
  async function publish(version: number | null): Promise<ListingDetail | null> {
    const listing = await sending.send(() => setPublication(scenarioId, version), describePublicationProblem);
    if (listing) queryClient.setQueryData(listingKey(scenarioId), listing);
    return listing;
  }

  return { busy: sending.busy, problem: sending.problem, publish };
}
