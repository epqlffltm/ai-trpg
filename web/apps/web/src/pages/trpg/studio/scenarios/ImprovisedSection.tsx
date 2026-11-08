// web/apps/web/src/pages/trpg/studio/scenarios/ImprovisedSection.tsx
// 즉흥 조우(B9 몬스터 탭, #254). 서술(AI)이 무작위 조우 표에서 몬스터의 등장을 고를 수 있는 테이블 하나의 횟수를 정한다.
// 고를 거리와 받아들일지는 엔진이 정한다(trpg-server/app/rounds/improvised.py). 저장하면 바로 보낸다. 검사는 improvisedForm.ts.

import { Button, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import type { ScenarioDetail } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { improvisedHint, improvisedLine, IMPROVISED_MAX, toImprovised } from './improvisedForm';
import { useScenarioSave } from './useScenarioSave';

type Props = { scenario: ScenarioDetail };

export function ImprovisedSection({ scenario }: Props) {
  const [value, setValue] = useState(String(scenario.improvised_encounters));
  const saving = useScenarioSave(scenario.id);
  const hint = improvisedHint(value);
  const count = toImprovised(value);
  const unchanged = count === scenario.improvised_encounters;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (count === null) return;
    const saved = await saving.save({ improvised_encounters: count });
    if (saved) setValue(String(saved.improvised_encounters));
  }

  return (
    <section className="page-section" aria-labelledby="improvised-heading">
      <h2 id="improvised-heading">
        즉흥 조우 <span className="hint">({improvisedLine(scenario.improvised_encounters)})</span>
      </h2>
      <p className="hint">
        이야기의 흐름에 맞으면 서술하는 AI 가 무작위 조우 표에서 몬스터의 등장을 고를 수 있습니다. 고를 수 있는 것은 일행이 선 장소의 표에 적힌 몬스터와 마리 수뿐이고, 받아들일지는 게임이 정합니다. 한 라운드에 한 번, 테이블 하나에 정한 횟수까지입니다. 0 이면 꺼집니다.
      </p>
      {scenario.wanders.length === 0 ? <p className="hint">무작위 조우 표가 없으면 켜도 고를 몬스터가 없습니다.</p> : null}
      <form onSubmit={submit} noValidate aria-label="즉흥 조우">
        <ProblemNotice problem={saving.problem} />
        <TextField
          label={`테이블 하나의 횟수(0~${IMPROVISED_MAX})`}
          name="improvised_encounters"
          inputMode="numeric"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          error={hint ?? undefined}
        />
        <div className="form-actions">
          <Button type="submit" busy={saving.busy} disabled={hint !== null || unchanged}>
            저장
          </Button>
          {saving.saved && unchanged ? <span className="hint">저장했습니다.</span> : null}
        </div>
      </form>
    </section>
  );
}
