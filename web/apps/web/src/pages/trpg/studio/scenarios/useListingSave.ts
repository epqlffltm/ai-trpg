// web/apps/web/src/pages/trpg/studio/scenarios/useListingSave.ts
// 소개 페이지를 저장한다(B9 소개 탭). 받은 소개 페이지를 읽기에 넣는다. 판을 새로 내지 않아도 공개된 소개에 바로 보인다.

import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { updateListing } from '../../../../api/scenarios';
import type { ListingDetail, ListingUpdate } from '../../../../api/types';
import { useSending } from '../useSending';
import { describeListingProblem } from './listingProblem';
import { listingKey } from './scenarioQueries';

export function useListingSave(scenarioId: string) {
  const queryClient = useQueryClient();
  const sending = useSending();
  const [saved, setSaved] = useState(false);

  /** 저장한 소개 페이지, 못 했으면 null */
  async function save(body: ListingUpdate): Promise<ListingDetail | null> {
    setSaved(false);
    const listing = await sending.send(() => updateListing(scenarioId, body), describeListingProblem);
    if (!listing) return null;
    queryClient.setQueryData(listingKey(scenarioId), listing);
    setSaved(true);
    return listing;
  }

  return { busy: sending.busy, problem: sending.problem, saved, save };
}
