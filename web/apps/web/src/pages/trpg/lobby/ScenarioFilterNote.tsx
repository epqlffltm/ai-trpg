// web/apps/web/src/pages/trpg/lobby/ScenarioFilterNote.tsx
// 로비를 시나리오 하나로 거르고 있다는 한 줄과 거르기를 푸는 단추. 시나리오의 제목은 공개 소개에서 읽는다(읽지 못하면 "이 시나리오").

import { Button } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { listingQuery } from '../queries';

export function ScenarioFilterNote({ scenarioId, onClear }: { scenarioId: string; onClear: () => void }) {
  const listing = useQuery(listingQuery(scenarioId, true));
  const title = listing.data?.title;
  return (
    <p className="filter-note">
      {title ? <Link to={`/trpg/scenarios/${scenarioId}`}>{title}</Link> : '이 시나리오'}의 테이블만 보고 있습니다.
      <Button variant="quiet" onClick={onClear}>
        모든 테이블 보기
      </Button>
    </p>
  );
}
