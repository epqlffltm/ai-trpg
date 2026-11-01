// web/apps/web/src/pages/trpg/studio/scenarios/QuestsTab.tsx
// 시나리오의 퀘스트·사건 탭(B9). 탭의 저장은 없고 모두 창에서 바로 저장한다: 퀘스트(QuestsSection)와 사건(HappeningsSection).
// 조건과 효과가 가리키는 것은 useConditionTargets 가 모은다. 장이 있는 시나리오면 조건에 장(그 장 이상)도 고를 수 있다.

import { Button, Notice } from '@ai-trpg/ui';
import type { ScenarioDetail } from '../../../../api/types';
import { HappeningsSection } from './HappeningsSection';
import { QuestsSection } from './QuestsSection';
import type { ScenarioTab } from './scenarioTabs';
import { useConditionTargets } from './useConditionTargets';
import { useScenarioRules } from './useScenarioRules';

type Props = { scenario: ScenarioDetail; goTo: (tab: ScenarioTab) => void };

export function QuestsTab({ scenario, goTo }: Props) {
  const { rules, pending } = useScenarioRules(scenario);
  const { targets, pending: loading, failed } = useConditionTargets(scenario);
  if (pending || loading) return <p aria-busy="true">불러오는 중</p>;
  return (
    <>
      {scenario.lorebook_ids.length === 0 ? (
        <Notice>
          퀘스트와 사건은 붙인 로어북의 사건 항목입니다. 로어북을 붙이면 정할 수 있습니다.{' '}
          <Button variant="quiet" onClick={() => goTo('materials')}>
            재료 탭으로
          </Button>
        </Notice>
      ) : null}
      {failed ? <Notice tone="error">로어북의 항목을 불러오지 못했습니다. 이름이 보이지 않을 수 있습니다.</Notice> : null}
      <QuestsSection scenario={scenario} rules={rules} targets={targets} />
      <HappeningsSection scenario={scenario} targets={targets} />
    </>
  );
}
