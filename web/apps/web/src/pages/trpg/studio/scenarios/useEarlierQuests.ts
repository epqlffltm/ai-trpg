// web/apps/web/src/pages/trpg/studio/scenarios/useEarlierQuests.ts
// 캠페인의 앞 편의 퀘스트(#481 B)를 고를 사건들. 시나리오는 어느 캠페인에 들지 모르므로 내 로어북들(100 개까지)의 사건 항목을 모은다.
// 이름 뒤에 로어북의 제목을 붙인다(같은 이름의 사건이 여러 로어북에 있을 수 있다). 앞 편의 판의 퀘스트인지는 캠페인을 게시할 때 본다.
// 쓸 때만 읽는다(enabled). 조건의 고르는 칸과 퀘스트·사건·장의 한 줄이 같은 읽기를 나눠 쓴다.

import { useQueries, useQuery } from '@tanstack/react-query';
import type { AssetSummary, LoreEntry, ScenarioDetail } from '../../../../api/types';
import { entriesQuery } from '../lorebooks/lorebookQueries';
import { isEarlierQuest } from './conditionsForm';
import { choicesQuery } from './scenarioQueries';
import type { EntryChoice } from './useLoreEntries';

/** 로어북마다의 사건 항목. "구출(1편 로어북)". 로어북의 차례, 로어북 안의 차례다 */
export function earlierQuestChoices(lorebooks: AssetSummary[], entryLists: (LoreEntry[] | undefined)[]): EntryChoice[] {
  return lorebooks.flatMap((lorebook, index) =>
    (entryLists[index] ?? []).filter((entry) => entry.kind === 'event').map((entry) => ({ id: entry.id, name: `${entry.name}(${lorebook.title})` })),
  );
}

/** 저장된 시나리오가 캠페인의 앞 편의 퀘스트를 보는 조건을 쓰는가(퀘스트, 사건, 장, 업적) */
export function usesEarlierQuests(scenario: ScenarioDetail): boolean {
  const conditions = [
    ...scenario.quests.flatMap((rule) => [...rule.reveal, ...rule.fail]),
    ...scenario.happenings.flatMap((rule) => rule.when),
    ...scenario.chapters.flatMap((chapter) => chapter.when),
    ...scenario.achievements.flatMap((achievement) => achievement.when),
  ];
  return conditions.some((condition) => isEarlierQuest(condition.kind));
}

export function useEarlierQuests(enabled: boolean) {
  const lorebooks = useQuery({ ...choicesQuery('lorebooks'), enabled });
  const items = lorebooks.data?.items ?? [];
  const results = useQueries({ queries: items.map((lorebook) => ({ ...entriesQuery(lorebook.id), enabled })) });
  return {
    choices: earlierQuestChoices(
      items,
      results.map((result) => result.data),
    ),
    pending: enabled && (lorebooks.isPending || results.some((result) => result.isPending)),
    failed: lorebooks.isError || results.some((result) => result.isError),
  };
}
