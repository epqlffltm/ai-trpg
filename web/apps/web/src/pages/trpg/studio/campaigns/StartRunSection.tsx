// web/apps/web/src/pages/trpg/studio/campaigns/StartRunSection.tsx
// 캠페인으로 플레이를 시작한다(#481 B). 마지막으로 게시한 판으로 하고, 첫 편의 테이블이 열리면 그 테이블 방으로 간다.
// 정원만 고른다. 다른 설정(서술 모델, 시간 제한 …)은 판의 추천이고, 열린 테이블에서 방장이 바꾼다.
// 친구는 첫 편의 초대 코드로 들어오고, 그 뒤의 편은 캠페인에서 초대 코드 없이 들어온다. 게시한 판이 없으면 시작하지 못한다.

import { Button, ChipGroup } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { useStartRun } from '../../campaigns/useRunActions';
import { PLAYER_COUNTS } from '../../labels';
import { campaignVersionsQuery } from './campaignQueries';

const CAPACITY_CHIPS = PLAYER_COUNTS.map((count) => ({ value: count, label: count === 1 ? '혼자' : `${count}명` }));

export function StartRunSection({ campaignId }: { campaignId: string }) {
  const versions = useQuery(campaignVersionsQuery(campaignId));
  const starting = useStartRun(campaignId);
  const [capacity, setCapacity] = useState<number>(PLAYER_COUNTS[PLAYER_COUNTS.length - 1] ?? 1);
  const latest = versions.data?.[0];

  return (
    <section className="page-section" aria-labelledby="campaign-start-heading">
      <h2 id="campaign-start-heading">플레이 시작</h2>
      <p className="hint">
        {latest
          ? `마지막으로 게시한 ${latest.number}판으로 첫 편의 테이블을 엽니다. 친구는 그 테이블의 초대 코드로 들어오고, 다음 편부터는 초대 코드 없이 들어옵니다.`
          : '게시한 판이 있어야 시작할 수 있습니다.'}
      </p>
      <ProblemNotice problem={starting.problem} />
      <div className="ui-field">
        <span className="ui-field__label">정원(방장 포함)</span>
        <ChipGroup<number> label="정원" chips={CAPACITY_CHIPS} selected={capacity} onChange={(value) => value && setCapacity(value)} />
      </div>
      <div className="form-actions">
        <Button busy={starting.busy} disabled={!latest} onClick={() => void starting.start({ capacity })}>
          플레이 시작
        </Button>
      </div>
    </section>
  );
}
