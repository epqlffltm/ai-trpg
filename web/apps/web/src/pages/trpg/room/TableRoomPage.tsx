// web/apps/web/src/pages/trpg/room/TableRoomPage.tsx
// 테이블 방(B6, /trpg/tables/:tableId). 로그인해야 열린다. 이 파일은 테이블을 읽고 상태만 맡는다. 그리는 것은 TableRoom 이다.
// 앉아 있지 않거나 없는 테이블은 서버가 404 로 답한다(있다는 것을 드러내지 않는다). 화면도 둘을 가르지 않는다.
// 이미 읽은 테이블을 다시 읽다가 잠깐 실패하면(503, 끊김) 방을 그대로 둔다. 방을 내리면 스트림도 끊긴다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router';
import { ApiError } from '../../../api/errors';
import { tableQuery } from './roomQueries';
import { TableRoom } from './TableRoom';

export function TableRoomPage() {
  const { tableId = '' } = useParams();
  const table = useQuery(tableQuery(tableId));

  if (table.isPending) return <p className="page page--loading">불러오는 중</p>;
  const gone = isGone(table.error);
  if (table.data && !gone) return <TableRoom key={tableId} table={table.data} />;
  return <LoadProblem missing={gone} onRetry={() => void table.refetch()} />;
}

/** 앉아 있지 않거나 없다. 경로의 ID 가 UUID 가 아니면 422 다. 없는 것과 같게 본다 */
function isGone(error: Error | null): boolean {
  return error instanceof ApiError && (error.status === 404 || error.status === 422);
}

function LoadProblem({ missing, onRetry }: { missing: boolean; onRetry: () => void }) {
  return (
    <main className="page page--narrow">
      <h1>테이블</h1>
      {missing ? (
        <Notice>앉아 있지 않거나 없는 테이블입니다.</Notice>
      ) : (
        <Notice tone="error">
          테이블을 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={onRetry}>
            다시 시도
          </Button>
        </Notice>
      )}
      <Link to="/trpg/lobby">로비로</Link>
    </main>
  );
}
