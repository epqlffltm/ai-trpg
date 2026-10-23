// web/apps/web/src/pages/trpg/studio/scenarios/OpeningsTab.tsx
// 시나리오의 스타팅 탭(B9). 스타팅은 테이블이 시작할 때 서술하는 AI 가 처음 읽어 주는 장면이다.
// 테이블을 만드는 사람이 하나를 고르고, 목록의 차례가 고르는 화면의 차례다. 더하기, 지우기, 앞으로 옮기기.

import { Button } from '@ai-trpg/ui';
import { useState } from 'react';
import type { ScenarioDetail } from '../../../../api/types';
import { TextAreaField } from '../../../../components/TextAreaField';
import {
  addOpening,
  changeOpening,
  moveOpeningUp,
  OPENING_MAX_LENGTH,
  OPENINGS_MAX,
  openingsHints,
  removeOpening,
  toOpeningsBody,
} from './openingsForm';
import { ScenarioForm } from './ScenarioForm';
import { useScenarioSave } from './useScenarioSave';

export function OpeningsTab({ scenario }: { scenario: ScenarioDetail }) {
  const [openings, setOpenings] = useState<string[]>(() => scenario.openings);
  const saving = useScenarioSave(scenario.id);
  const hints = openingsHints(openings);

  async function submit() {
    const saved = await saving.save(toOpeningsBody(openings));
    if (saved) setOpenings(saved.openings);
  }

  return (
    <ScenarioForm
      label="스타팅"
      busy={saving.busy}
      problem={saving.problem}
      saved={saving.saved}
      blocked={Object.keys(hints).length > 0}
      onSubmit={() => void submit()}
    >
      <p className="hint">
        테이블이 시작할 때 서술하는 AI 가 처음 읽어 주는 장면입니다. 테이블을 만드는 사람이 하나를 고르고, 맨 앞의 것이 기본입니다. 게시하려면 하나는 있어야
        합니다.
      </p>
      {openings.length === 0 ? <p>아직 스타팅이 없습니다.</p> : null}
      <ol className="plain-list scenario-openings" aria-label="스타팅">
        {openings.map((opening, index) => (
          // 스타팅에는 서버의 id 가 없다. 차례가 곧 그 스타팅이다
          <li key={index} className="scenario-opening">
            <TextAreaField
              label={`스타팅 ${index + 1}`}
              rows={6}
              maxLength={OPENING_MAX_LENGTH}
              value={opening}
              onChange={(event) => setOpenings((current) => changeOpening(current, index, event.target.value))}
              error={hints[index]}
              hint={`${opening.length} / ${OPENING_MAX_LENGTH}자`}
            />
            <div className="form-actions">
              {index > 0 ? (
                <Button variant="quiet" onClick={() => setOpenings((current) => moveOpeningUp(current, index))} aria-label={`스타팅 ${index + 1} 앞으로`}>
                  앞으로
                </Button>
              ) : null}
              <Button variant="quiet" onClick={() => setOpenings((current) => removeOpening(current, index))} aria-label={`스타팅 ${index + 1} 지우기`}>
                지우기
              </Button>
            </div>
          </li>
        ))}
      </ol>
      <p>
        <Button variant="secondary" disabled={openings.length >= OPENINGS_MAX} onClick={() => setOpenings(addOpening)}>
          스타팅 더하기
        </Button>{' '}
        <span className="hint">
          {openings.length} / {OPENINGS_MAX}
        </span>
      </p>
    </ScenarioForm>
  );
}
