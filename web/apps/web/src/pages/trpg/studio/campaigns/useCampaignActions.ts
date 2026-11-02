// web/apps/web/src/pages/trpg/studio/campaigns/useCampaignActions.ts
// 캠페인의 편을 저장하고, 게시한다(#481 B).
// 편을 저장하면 받은 캠페인을 낱개의 읽기에 넣고(useSaveAsset) 점검을 다시 읽는다.
// 게시했든 막혔든(409 problems) 점검을 다시 읽는다. 게시했으면 판의 목록도 다시 읽는다.

import { useQueryClient } from '@tanstack/react-query';
import { publishCampaign, updateCampaign } from '../../../../api/campaigns';
import type { CampaignDetail, CampaignVersionDetail } from '../../../../api/types';
import { useSaveAsset } from '../useAssetActions';
import { useSending } from '../useSending';
import { campaignCheckKey, campaignVersionsKey } from './campaignQueries';
import { describeCampaignPublishProblem, describeEpisodesProblem } from './campaignProblem';
import { toEpisodesBody, type EpisodeDraft } from './episodesDraft';

export function useSaveEpisodes(campaignId: string) {
  const queryClient = useQueryClient();
  const saving = useSaveAsset<CampaignDetail>('campaigns', describeEpisodesProblem);

  /** 저장한 캠페인, 못 했으면 null */
  async function save(episodes: EpisodeDraft[]): Promise<CampaignDetail | null> {
    const saved = await saving.save(() => updateCampaign(campaignId, { episodes: toEpisodesBody(episodes) }));
    if (saved) void queryClient.invalidateQueries({ queryKey: campaignCheckKey(campaignId) });
    return saved;
  }

  return { busy: saving.busy, problem: saving.problem, save };
}

export function usePublishCampaign(campaignId: string) {
  const queryClient = useQueryClient();
  const sending = useSending();

  /** 낸 판, 못 냈으면 null */
  async function publish(note: string): Promise<CampaignVersionDetail | null> {
    const version = await sending.send(() => publishCampaign(campaignId, note), describeCampaignPublishProblem);
    void queryClient.invalidateQueries({ queryKey: campaignCheckKey(campaignId) });
    if (version) void queryClient.invalidateQueries({ queryKey: campaignVersionsKey(campaignId) });
    return version;
  }

  return { busy: sending.busy, problem: sending.problem, publish };
}
