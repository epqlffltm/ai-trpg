// web/apps/web/src/pages/trpg/studio/scenarios/ItemsTab.tsx
// 시나리오의 물건·돈 탭(B9). 탭의 저장: 화폐와 시작 소지품. 창에서 바로 저장: 물건 규칙(ItemRulesSection), 프리젠의 소지품과 돈(PregenBelongings).
// 물건은 붙인 로어북의 물건 항목이다. 로어북이 없으면 재료 탭으로 가는 길을 둔다. 칸과 양의 이름은 저장된 룰북에서 읽는다.

import { Button, Checkbox, Notice, TextField } from '@ai-trpg/ui';
import { useState } from 'react';
import type { Ruleset, ScenarioDetail } from '../../../../api/types';
import { CURRENCY_NAME_MAX, CURRENCY_UNIT_MAX, currencyDraft, currencyHints, toCurrency, type CurrencyDraft } from './currencyForm';
import { ItemRulesSection } from './ItemRulesSection';
import { PregenBelongings } from './PregenBelongings';
import { ScenarioForm } from './ScenarioForm';
import type { ScenarioTab } from './scenarioTabs';
import { MAX_STARTING_ITEMS, stackDrafts, stacksHints, toStacks, type StackDraft } from './stacksForm';
import { StacksEditor } from './StacksEditor';
import { useItemEntries, type ItemEntry } from './useItemEntries';
import { useScenarioRules } from './useScenarioRules';
import { useScenarioSave } from './useScenarioSave';

type Props = { scenario: ScenarioDetail; goTo: (tab: ScenarioTab) => void };

export function ItemsTab({ scenario, goTo }: Props) {
  const { rules, pending } = useScenarioRules(scenario);
  const items = useItemEntries(scenario.lorebook_ids);
  if (pending || items.pending) return <p aria-busy="true">불러오는 중</p>;
  return (
    <>
      {scenario.lorebook_ids.length === 0 ? (
        <Notice>
          물건은 붙인 로어북의 물건 항목입니다. 로어북을 붙이면 규칙과 소지품을 정할 수 있습니다.{' '}
          <Button variant="quiet" onClick={() => goTo('materials')}>
            재료 탭으로
          </Button>
        </Notice>
      ) : null}
      {items.failed ? <Notice tone="error">로어북의 항목을 불러오지 못했습니다. 물건의 이름이 보이지 않을 수 있습니다.</Notice> : null}
      <MoneyForm scenario={scenario} rules={rules} entries={items.entries} />
      <ItemRulesSection scenario={scenario} rules={rules} entries={items.entries} />
      <PregenBelongings scenario={scenario} rules={rules} entries={items.entries} />
    </>
  );
}

type FormProps = { scenario: ScenarioDetail; rules: Ruleset | null; entries: ItemEntry[] };

/** 탭의 저장: 화폐와 시작 소지품 */
function MoneyForm({ scenario, rules, entries }: FormProps) {
  const [currency, setCurrency] = useState<CurrencyDraft>(() => currencyDraft(scenario.currency));
  const [stacks, setStacks] = useState<StackDraft[]>(() => stackDrafts(scenario.starting_items));
  const saving = useScenarioSave(scenario.id);
  const hints = currencyHints(currency);
  const stackHints = stacksHints(stacks, scenario.items);

  async function submit() {
    const saved = await saving.save({ currency: toCurrency(currency), starting_items: toStacks(stacks) });
    if (!saved) return;
    setCurrency(currencyDraft(saved.currency));
    setStacks(stackDrafts(saved.starting_items));
  }

  return (
    <ScenarioForm
      label="물건·돈"
      busy={saving.busy}
      problem={saving.problem}
      saved={saving.saved}
      blocked={Object.keys(hints).length > 0 || Object.keys(stackHints).length > 0}
      onSubmit={() => void submit()}
    >
      <CurrencyFields draft={currency} hints={hints} onChange={setCurrency} />
      <fieldset className="scenario-choices">
        <legend>시작 소지품(모두가 받는다)</legend>
        <StacksEditor
          label="시작 소지품"
          drafts={stacks}
          onChange={setStacks}
          entries={entries}
          itemRules={scenario.items}
          rules={rules}
          hints={stackHints}
          max={MAX_STARTING_ITEMS}
        />
      </fieldset>
    </ScenarioForm>
  );
}

type CurrencyProps = { draft: CurrencyDraft; hints: Record<string, string>; onChange: (draft: CurrencyDraft) => void };

function CurrencyFields({ draft, hints, onChange }: CurrencyProps) {
  const update = (changes: Partial<CurrencyDraft>) => onChange({ ...draft, ...changes });
  return (
    <fieldset className="scenario-choices">
      <legend>화폐</legend>
      <Checkbox
        label="이 시나리오는 돈을 쓴다"
        description="물건의 값, 상인, 퀘스트의 돈 보상이 화폐를 씁니다. 결제의 크레딧과 상관없는 게임 안의 돈입니다."
        checked={draft.enabled}
        onChange={(event) => update({ enabled: event.target.checked })}
      />
      {draft.enabled ? (
        <div className="scenario-players__row">
          <TextField label="이름" maxLength={CURRENCY_NAME_MAX} value={draft.name} onChange={(event) => update({ name: event.target.value })} error={draft.name === '' ? undefined : hints.currency_name} />
          <TextField label="단위(선택)" maxLength={CURRENCY_UNIT_MAX} value={draft.unit} onChange={(event) => update({ unit: event.target.value })} error={hints.currency_unit} />
          <TextField label="모두의 시작 돈" inputMode="numeric" value={draft.starting} onChange={(event) => update({ starting: event.target.value })} error={hints.starting} />
          <TextField
            label="상인이 사 주는 값(%)"
            inputMode="numeric"
            value={draft.sellPercent}
            onChange={(event) => update({ sellPercent: event.target.value })}
            error={hints.sell_percent}
          />
        </div>
      ) : null}
    </fieldset>
  );
}
