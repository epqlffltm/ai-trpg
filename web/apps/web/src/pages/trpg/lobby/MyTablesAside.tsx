// web/apps/web/src/pages/trpg/lobby/MyTablesAside.tsx
// 로비 옆의 "내 테이블". 앉아 있는 테이블로 돌아간다. 첫 화면의 이어하기와 같은 것을 읽는다(GET /tables, 6개).

import { ListSection } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { listStatus } from '../../home/listStatus';
import { tableStatusLabel } from '../../home/labels';
import { myTablesQuery } from '../../home/queries';
import { tablePath } from '../tables/useEnterTable';

export function MyTablesAside() {
  const query = useQuery(myTablesQuery());
  const items = query.data?.items ?? [];
  return (
    <aside className="lobby__side" aria-label="내 테이블">
      <ListSection
        title="내 테이블"
        status={listStatus(query, items.length)}
        emptyText="앉아 있는 테이블이 없습니다."
        onRetry={() => void query.refetch()}
      >
        <ul className="plain-list">
          {items.map((table) => (
            <li key={table.id}>
              <Link to={tablePath(table.id)}>{table.title}</Link>{' '}
              <span className="hint">
                {tableStatusLabel(table.status)} · {table.member_count}/{table.capacity}명
              </span>
            </li>
          ))}
        </ul>
      </ListSection>
    </aside>
  );
}
