// web/apps/web/src/pages/trpg/studio/scenarios/HappeningsSection.tsx
// 사건 규칙(B9 퀘스트·사건 탭, #367). 사건 항목마다 한 줄("종탑에 닿는다 ⇒ 모두 → 지하 묘지", 없으면 "규칙 없음").
// 창에서 일어나는 조건(퀘스트의 조건과 같다)과 효과를 고치고, 창의 저장이 사건 규칙 목록을 통째로 바로 보낸다.
// 같은 사건 항목이 퀘스트이기도 해도 된다. 사건은 라운드가 닫힐 때 퀘스트를 본 뒤 한 번만 일어난다.

import { Button, Dialog, Notice } from '@ai-trpg/ui';
import { useCallback, useState, type FormEvent } from 'react';
import type { ScenarioDetail } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { ConditionsEditor } from './ConditionsEditor';
import { KINDS_FOR, type Targets } from './conditionsForm';
import { EffectsEditor } from './EffectsEditor';
import { eventRows, type EventRow } from './eventRows';
import { happeningDraft, happeningHints, happeningLine, hasHappeningHints, MAX_HAPPENINGS, toHappening, withHappening, withoutHappening, type HappeningDraft } from './happeningForm';
import { useScenarioSave } from './useScenarioSave';

type Props = { scenario: ScenarioDetail; targets: Targets };

export function HappeningsSection({ scenario, targets }: Props) {
  const [editing, setEditing] = useState<EventRow | null>(null);
  const close = useCallback(() => setEditing(null), []);
  const rows = eventRows(
    targets.quests,
    scenario.happenings.map((rule) => rule.entry_id),
  );
  return (
    <section className="page-section" aria-labelledby="happenings-heading">
      <h2 id="happenings-heading">
        사건{' '}
        <span className="hint">
          ({scenario.happenings.length} / {MAX_HAPPENINGS})
        </span>
      </h2>
      <p className="hint">조건이 채워지면 한 번 일어나 캐릭터나 인물을 옮기거나 길의 문을 다룹니다. 라운드가 닫힐 때 퀘스트를 본 뒤에 일어납니다. 창에서 저장하면 바로 저장됩니다.</p>
      <ul className="plain-list studio-list" aria-label="사건">
        {rows.map((row) => {
          const rule = scenario.happenings.find((one) => one.entry_id === row.id);
          return (
            <li key={row.id} className="studio-list__item studio-item">
              <div>
                <strong>{row.name}</strong>
                <div className="studio-list__description hint">{rule ? happeningLine(rule, targets) : '규칙 없음'}</div>
              </div>
              <Button variant="quiet" aria-label={`${row.name} 사건 고치기`} onClick={() => setEditing(row)}>
                고치기
              </Button>
            </li>
          );
        })}
      </ul>
      <Dialog title={editing ? `사건: ${editing.name}` : '사건'} open={editing !== null} onClose={close}>
        {editing ? <HappeningForm scenario={scenario} targets={targets} row={editing} done={close} /> : null}
      </Dialog>
    </section>
  );
}

type FormProps = Props & { row: EventRow; done: () => void };

function HappeningForm({ scenario, targets, row, done }: FormProps) {
  const rule = scenario.happenings.find((one) => one.entry_id === row.id);
  const [draft, setDraft] = useState<HappeningDraft>(() => happeningDraft(rule));
  const saving = useScenarioSave(scenario.id);
  const hints = happeningHints(draft, row.id);
  const blocked = hasHappeningHints(hints);
  const full = !rule && scenario.happenings.length >= MAX_HAPPENINGS;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (blocked || full) return;
    if (await saving.save({ happenings: withHappening(scenario.happenings, toHappening(row.id, draft)) })) done();
  }

  async function clear() {
    if (await saving.save({ happenings: withoutHappening(scenario.happenings, row.id) })) done();
  }

  const clearButton = rule ? (
    <Button variant="quiet" disabled={saving.busy} onClick={() => void clear()}>
      규칙 지우기
    </Button>
  ) : null;

  if (!row.listed) {
    return (
      <div>
        <ProblemNotice problem={saving.problem} />
        <p>이 규칙은 붙인 로어북의 사건을 가리키지 않아 테이블에서 쓰이지 않습니다. 지우거나, 그 사건이 있는 로어북을 다시 붙이세요.</p>
        <div className="actions">{clearButton}</div>
      </div>
    );
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate aria-label="사건">
      <ProblemNotice problem={saving.problem} />
      {full ? <Notice tone="error">사건 규칙은 {MAX_HAPPENINGS}개까지입니다.</Notice> : null}
      <fieldset className="scenario-choices">
        <legend>일어나는 조건</legend>
        <ConditionsEditor
          label="일어나는 조건"
          kinds={KINDS_FOR.any}
          drafts={draft.when}
          onChange={(when) => setDraft((current) => ({ ...current, when }))}
          match={draft.match}
          onMatch={(match) => setDraft((current) => ({ ...current, match }))}
          targets={{ ...targets, quests: targets.quests.filter((one) => one.id !== row.id) }}
          hints={hints.when}
        />
        {hints.fields.when ? <p className="ui-field__error">{hints.fields.when}</p> : null}
      </fieldset>
      <fieldset className="scenario-choices">
        <legend>효과</legend>
        <EffectsEditor
          drafts={draft.effects}
          onChange={(effects) => setDraft((current) => ({ ...current, effects }))}
          targets={targets}
          routes={scenario.routes}
          hints={hints.effects}
        />
        {hints.fields.effects ? <p className="ui-field__error">{hints.fields.effects}</p> : null}
      </fieldset>
      <div className="actions">
        <Button type="submit" busy={saving.busy} disabled={blocked || full}>
          저장
        </Button>
        {clearButton}
      </div>
    </form>
  );
}
