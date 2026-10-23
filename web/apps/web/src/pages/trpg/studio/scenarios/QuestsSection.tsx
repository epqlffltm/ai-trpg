// web/apps/web/src/pages/trpg/studio/scenarios/QuestsSection.tsx
// 퀘스트(B9 퀘스트·사건 탭). 붙인 로어북의 사건 항목을 모두 늘어놓고 줄마다 퀘스트 규칙(없으면 "규칙 없음")을 한 줄로 보인다.
// 줄을 고치면 창이 열리고, 창의 저장이 퀘스트 규칙 목록을 통째로 바로 보낸다. 규칙 지우기는 숨김·조건 없음으로 돌린다.
// 붙인 로어북에 없는 사건의 규칙도 줄로 남겨 지울 수 있게 한다.

import { Button, Dialog, Notice, SelectField, TextField } from '@ai-trpg/ui';
import { useCallback, useState, type FormEvent } from 'react';
import type { QuestStart, Ruleset, ScenarioDetail } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { ConditionsEditor } from './ConditionsEditor';
import { KINDS_FOR, type Targets } from './conditionsForm';
import { moneyText } from './currencyForm';
import { hasQuestHints, questDraft, questHints, questLine, toQuestRule, withoutQuestRule, withQuestRule, type QuestDraft } from './questForm';
import { MAX_STARTING_ITEMS } from './stacksForm';
import { StacksEditor } from './StacksEditor';
import { eventRows, type EventRow } from './eventRows';
import { useScenarioSave } from './useScenarioSave';

type Props = { scenario: ScenarioDetail; rules: Ruleset | null; targets: Targets };

export function QuestsSection({ scenario, rules, targets }: Props) {
  const [editing, setEditing] = useState<EventRow | null>(null);
  const close = useCallback(() => setEditing(null), []);
  const rows = eventRows(
    targets.quests,
    scenario.quests.map((rule) => rule.entry_id),
  );
  return (
    <section className="page-section" aria-labelledby="quests-heading">
      <h2 id="quests-heading">퀘스트</h2>
      <p className="hint">
        붙인 로어북의 사건 항목 하나가 퀘스트 하나입니다. 성공·실패·드러남은 조건을 보고 엔진만 정합니다(방장도 서술도 바꾸지 못합니다). 창에서 저장하면 바로 저장됩니다.
      </p>
      {rows.length === 0 ? <p className="hint">붙인 로어북에 사건 항목이 없습니다. 로어북에 종류가 사건인 항목을 더하세요.</p> : null}
      <ul className="plain-list studio-list" aria-label="퀘스트">
        {rows.map((row) => {
          const rule = scenario.quests.find((one) => one.entry_id === row.id);
          return (
            <li key={row.id} className="studio-list__item studio-item">
              <div>
                <strong>{row.name}</strong>
                <div className="studio-list__description hint">{rule ? questLine(rule, targets) : '규칙 없음(숨김으로 시작, 조건 없음)'}</div>
              </div>
              <Button variant="quiet" aria-label={`${row.name} 퀘스트 고치기`} onClick={() => setEditing(row)}>
                고치기
              </Button>
            </li>
          );
        })}
      </ul>
      <Dialog title={editing ? `퀘스트: ${editing.name}` : '퀘스트'} open={editing !== null} onClose={close}>
        {editing ? <QuestForm scenario={scenario} rules={rules} targets={targets} row={editing} done={close} /> : null}
      </Dialog>
    </section>
  );
}

type FormProps = Props & { row: EventRow; done: () => void };

function QuestForm({ scenario, rules, targets, row, done }: FormProps) {
  const rule = scenario.quests.find((one) => one.entry_id === row.id);
  const [draft, setDraft] = useState<QuestDraft>(() => questDraft(rule));
  const saving = useScenarioSave(scenario.id);
  const hints = questHints(draft, row.id, scenario.items);
  const blocked = hasQuestHints(hints);

  function update(changes: Partial<QuestDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (blocked) return;
    if (await saving.save({ quests: withQuestRule(scenario.quests, toQuestRule(row.id, draft)) })) done();
  }

  async function clear() {
    if (await saving.save({ quests: withoutQuestRule(scenario.quests, row.id) })) done();
  }

  if (!row.listed) {
    return (
      <div>
        <ProblemNotice problem={saving.problem} />
        <p>이 규칙은 붙인 로어북의 사건을 가리키지 않아 테이블에서 쓰이지 않습니다. 지우거나, 그 사건이 있는 로어북을 다시 붙이세요.</p>
        <div className="actions">
          <Button variant="quiet" disabled={saving.busy} onClick={() => void clear()}>
            규칙 지우기
          </Button>
        </div>
      </div>
    );
  }

  const others = { ...targets, quests: targets.quests.filter((one) => one.id !== row.id) };
  return (
    <form onSubmit={(event) => void submit(event)} noValidate aria-label="퀘스트">
      <ProblemNotice problem={saving.problem} />
      <SelectField label="처음 상태" value={draft.start} onChange={(event) => update({ start: event.target.value as QuestStart })}>
        <option value="hidden">숨김(조건이 채워지면 드러남)</option>
        <option value="active">진행 중(처음부터 보임)</option>
      </SelectField>
      <fieldset className="scenario-choices">
        <legend>이루는 조건</legend>
        <p className="ui-field__hint">비우면 이 퀘스트는 성공하지 않습니다. 물건 지니기에는 이룰 때 그 물건을 가져가게(배달) 할 수 있습니다.</p>
        <ConditionsEditor
          label="이루는 조건"
          kinds={KINDS_FOR.goal}
          drafts={draft.conditions}
          onChange={(conditions) => update({ conditions })}
          match={draft.match}
          onMatch={(match) => update({ match })}
          targets={others}
          hints={hints.conditions}
          consume
        />
      </fieldset>
      {draft.start === 'hidden' ? (
        <fieldset className="scenario-choices">
          <legend>드러나는 조건</legend>
          <p className="ui-field__hint">비우면 이룰 때 드러나며 바로 성공합니다. 다른 퀘스트의 성공·실패로 이어 드러나게 할 수 있습니다.</p>
          <ConditionsEditor
            label="드러나는 조건"
            kinds={KINDS_FOR.reveal}
            drafts={draft.reveal}
            onChange={(reveal) => update({ reveal })}
            match={draft.revealMatch}
            onMatch={(revealMatch) => update({ revealMatch })}
            targets={others}
            hints={hints.reveal}
          />
        </fieldset>
      ) : null}
      <fieldset className="scenario-choices">
        <legend>실패하는 조건</legend>
        <p className="ui-field__hint">진행 중에 채워지면 실패합니다. 같은 라운드에 이루는 조건도 채워지면 성공이 먼저입니다. 지켜야 할 물건(잃는다)과 인물(죽는다)에 씁니다.</p>
        <ConditionsEditor
          label="실패하는 조건"
          kinds={KINDS_FOR.any}
          drafts={draft.fail}
          onChange={(fail) => update({ fail })}
          match={draft.failMatch}
          onMatch={(failMatch) => update({ failMatch })}
          targets={others}
          hints={hints.fail}
        />
      </fieldset>
      <fieldset className="scenario-choices">
        <legend>보상</legend>
        <StacksEditor
          label="보상 물건"
          drafts={draft.reward}
          onChange={(reward) => update({ reward })}
          entries={targets.items}
          itemRules={scenario.items}
          rules={rules}
          hints={hints.reward}
          max={MAX_STARTING_ITEMS}
          wear={false}
        />
        <TextField
          label="살아 있는 캐릭터마다 받는 돈"
          inputMode="numeric"
          value={draft.money}
          onChange={(event) => update({ money: event.target.value })}
          error={hints.fields.money}
        />
        {draft.money.trim() !== '0' && draft.money.trim() !== '' ? (
          <p className="ui-field__hint">{scenario.currency ? moneyText(scenario.currency, Number(draft.money) || 0) : '화폐가 없으면 게시 점검이 알립니다.'}</p>
        ) : null}
      </fieldset>
      <TextField
        label="기한(분, 선택)"
        inputMode="numeric"
        value={draft.minutes}
        onChange={(event) => update({ minutes: event.target.value })}
        error={hints.fields.minutes}
      />
      <p className="ui-field__hint">드러난 때부터 게임 안의 시간으로 셉니다. 지나면 실패합니다. 1440분이 하루입니다.</p>
      {blocked ? <Notice tone="error">고칠 칸이 있어 저장하지 않습니다.</Notice> : null}
      <div className="actions">
        <Button type="submit" busy={saving.busy} disabled={blocked}>
          저장
        </Button>
        {rule ? (
          <Button variant="quiet" disabled={saving.busy} onClick={() => void clear()}>
            규칙 지우기
          </Button>
        ) : null}
      </div>
    </form>
  );
}
