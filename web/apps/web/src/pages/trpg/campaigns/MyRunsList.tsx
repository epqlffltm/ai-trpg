// web/apps/web/src/pages/trpg/campaigns/MyRunsList.tsx
// 로비 옆의 "내 캠페인"(#481 B). 내가 열었거나 앉았거나 캐릭터를 넘긴 플레이. 지금 편의 테이블로 간다.
// 지금 편의 테이블이 없으면(방장이 아직 다음 편을 열지 않았다) 이름만 보인다.

import { ListSection } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { listStatus } from '../../home/listStatus';
import { tablePath } from '../tables/useEnterTable';
import { myRunsQuery } from './runQueries';
import { runStateLabel } from './runView';

export function MyRunsList() {
  const query = useQuery(myRunsQuery());
  const items = query.data?.items ?? [];
  return (
    <ListSection
      title="내 캠페인"
      status={listStatus(query, items.length)}
      emptyText="함께하는 캠페인이 없습니다."
      onRetry={() => void query.refetch()}
    >
      <ul className="plain-list" aria-label="내 캠페인">
        {items.map((run) => (
          <li key={run.id}>
            {run.table_id ? <Link to={tablePath(run.table_id)}>{run.title}</Link> : run.title}{' '}
            <span className="hint">{runStateLabel(run)}</span>
          </li>
        ))}
      </ul>
    </ListSection>
  );
}
