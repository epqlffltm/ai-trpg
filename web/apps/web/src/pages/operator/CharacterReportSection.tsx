// web/apps/web/src/pages/operator/CharacterReportSection.tsx
// 캐릭터의 신고(asset). 열린 신고를 캐릭터마다 한 줄로 묶어 보인다. 미성년 사유가 있는 것이 먼저다.
// 한 줄을 펼치면 그 캐릭터의 신고와 처리, 숨기기가 나온다. 처리하면 그 줄은 목록에서 빠진다.

import { useInfiniteQuery } from '@tanstack/react-query';
import { useState } from 'react';
import type { CharacterReportGroup } from '../../api/types';
import { formatDateTime } from '../../format/dateTime';
import { CharacterReportDetail } from './CharacterReportDetail';
import { LoadMore } from './LoadMore';
import { reasonSummary } from './moderationPure';
import { characterGroupsQuery } from './moderationQueries';

export function CharacterReportSection() {
  const query = useInfiniteQuery(characterGroupsQuery());
  const groups = query.data?.pages.flatMap((page) => page.items) ?? [];
  const total = query.data?.pages[0]?.total ?? 0;
  return (
    <section className="page-section" aria-labelledby="character-reports">
      <h2 id="character-reports">캐릭터의 신고 {query.isSuccess ? <small>({total}개 캐릭터)</small> : null}</h2>
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isSuccess && groups.length === 0 ? <p className="empty-state">열린 신고가 없습니다.</p> : null}
      <ul className="plain-list moderation-list" aria-label="신고된 캐릭터">
        {groups.map((group) => (
          <CharacterGroupItem key={group.character_id} group={group} />
        ))}
      </ul>
      <LoadMore
        failed={query.isError}
        hasMore={query.hasNextPage}
        loadingMore={query.isFetchingNextPage}
        onRetry={() => void query.refetch()}
        onMore={() => void query.fetchNextPage()}
      />
    </section>
  );
}

function CharacterGroupItem({ group }: { group: CharacterReportGroup }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="moderation-list__item">
      <p>
        <strong>{group.name}</strong> {group.hidden ? <span className="badge">숨김</span> : null} 열린 신고 {group.open_count}건
      </p>
      <p>{reasonSummary(group.reasons)}</p>
      <p className="hint">
        처음 {formatDateTime(group.first_reported_at)} · 마지막 {formatDateTime(group.last_reported_at)}
      </p>
      <details onToggle={(event) => setOpen(event.currentTarget.open)}>
        <summary>신고 보기와 처리</summary>
        {open ? <CharacterReportDetail characterId={group.character_id} hidden={group.hidden} /> : null}
      </details>
    </li>
  );
}
