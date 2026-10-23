// web/apps/web/src/pages/trpg/studio/scenarios/NpcsTab.tsx
// 시나리오의 인물 탭(B9). 탭의 저장: 기본 인물 시트(시트가 없는 인물이 받는 숫자). 창에서 바로 저장: 인물 시트(NpcSheetsSection).
// 인물은 저장된 로어북들의 인물 항목이고, 지닌 물건은 물건 항목이다. 로어북이나 룰북이 없으면 재료 탭으로 가는 길을 둔다.

import { Button, Notice } from '@ai-trpg/ui';
import { useState } from 'react';
import type { Ruleset, ScenarioDetail } from '../../../../api/types';
import { NpcSheetsSection } from './NpcSheetsSection';
import { ScenarioForm } from './ScenarioForm';
import type { ScenarioTab } from './scenarioTabs';
import { sheetDraft, sheetHints, toSheet, type SheetDraft } from './sheetForm';
import { SheetFields } from './SheetFields';
import { useLoreEntries } from './useLoreEntries';
import { useScenarioRules } from './useScenarioRules';
import { useScenarioSave } from './useScenarioSave';

type Props = { scenario: ScenarioDetail; goTo: (tab: ScenarioTab) => void };

export function NpcsTab({ scenario, goTo }: Props) {
  const { rules, pending } = useScenarioRules(scenario);
  const people = useLoreEntries(scenario.lorebook_ids, 'person');
  const items = useLoreEntries(scenario.lorebook_ids, 'item');
  if (pending || people.pending) return <p aria-busy="true">불러오는 중</p>;
  const missing = scenario.lorebook_ids.length === 0 || !rules;
  return (
    <>
      {missing ? (
        <Notice>
          인물은 붙인 로어북의 인물 항목이고, 숫자는 룰북이 정합니다. 로어북과 룰북을 고르면 시트를 적을 수 있습니다.{' '}
          <Button variant="quiet" onClick={() => goTo('materials')}>
            재료 탭으로
          </Button>
        </Notice>
      ) : null}
      {people.failed ? <Notice tone="error">로어북의 항목을 불러오지 못했습니다. 인물의 이름이 보이지 않을 수 있습니다.</Notice> : null}
      {rules ? <DefaultNpcForm key={scenario.rulebook_id ?? 'none'} scenario={scenario} rules={rules} /> : null}
      <NpcSheetsSection scenario={scenario} rules={rules} people={people.entries} items={items.entries} />
    </>
  );
}

function DefaultNpcForm({ scenario, rules }: { scenario: ScenarioDetail; rules: Ruleset }) {
  const [draft, setDraft] = useState<SheetDraft>(() => sheetDraft(scenario.default_npc_sheet, rules));
  const saving = useScenarioSave(scenario.id);
  const hints = sheetHints(draft, rules);

  async function submit() {
    const saved = await saving.save({ default_npc_sheet: toSheet(draft, rules) });
    if (saved) setDraft(sheetDraft(saved.default_npc_sheet, rules));
  }

  return (
    <ScenarioForm label="인물" busy={saving.busy} problem={saving.problem} saved={saving.saved} blocked={Object.keys(hints).length > 0} onSubmit={() => void submit()}>
      <SheetFields legend="기본 인물 시트(시트가 없는 인물이 받는 숫자)" rules={rules} draft={draft} hints={hints} onChange={setDraft} />
    </ScenarioForm>
  );
}
