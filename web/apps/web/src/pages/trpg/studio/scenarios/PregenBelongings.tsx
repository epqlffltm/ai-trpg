// web/apps/web/src/pages/trpg/studio/scenarios/PregenBelongings.tsx
// 프리젠의 소지품과 더 받는 돈(B9 물건·돈 탭). 프리젠마다 한 줄, 고치면 창이 열리고 창의 저장이 프리젠 목록을 통째로 바로 보낸다.
// 이름, 설명, 시트는 캐릭터 탭에서 고친다. 여기서는 그대로 둔다. 시나리오의 시작 소지품과 돈은 모두가 따로 받는다.

import { Button, Dialog, TextField } from '@ai-trpg/ui';
import { useCallback, useState, type FormEvent } from 'react';
import type { Ruleset, ScenarioDetail } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { wholeNumber } from '../rulebooks/rulebookForm';
import { moneyText } from './currencyForm';
import { MONEY_MAX } from './itemRuleForm';
import { toPregensBody, withBelongings } from './pregenForm';
import { MAX_STARTING_ITEMS, stackDrafts, stacksHints, toStacks, type StackDraft } from './stacksForm';
import { StacksEditor } from './StacksEditor';
import { entryName, type ItemEntry } from './useItemEntries';
import { useScenarioSave } from './useScenarioSave';

type Props = { scenario: ScenarioDetail; rules: Ruleset | null; entries: ItemEntry[] };

export function PregenBelongings({ scenario, rules, entries }: Props) {
  const [editing, setEditing] = useState<number | null>(null);
  const close = useCallback(() => setEditing(null), []);
  if (scenario.pregens.length === 0) return null;
  return (
    <section className="page-section" aria-labelledby="pregen-belongings-heading">
      <h2 id="pregen-belongings-heading">프리젠의 소지품과 돈</h2>
      <p className="hint">그 프리젠을 고른 사람이 시작 소지품과 시작 돈에 더해 받는 것입니다. 창에서 저장하면 바로 저장됩니다.</p>
      <ul className="plain-list studio-list" aria-label="프리젠의 소지품">
        {scenario.pregens.map((pregen, at) => (
          <li key={pregen.name} className="studio-list__item studio-item">
            <div>
              <strong>{pregen.name}</strong>
              <div className="studio-list__description hint">
                {[
                  pregen.items.map((stack) => `${entryName(entries, stack.entry_id)} ${stack.count}`).join(', ') || '소지품 없음',
                  pregen.money > 0 ? moneyText(scenario.currency, pregen.money) : null,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </div>
            </div>
            <Button variant="quiet" aria-label={`${pregen.name}의 소지품 고치기`} onClick={() => setEditing(at)}>
              고치기
            </Button>
          </li>
        ))}
      </ul>
      <Dialog title={editing === null ? '프리젠의 소지품' : `${scenario.pregens[editing]?.name ?? ''}의 소지품과 돈`} open={editing !== null} onClose={close}>
        {editing !== null ? <BelongingsForm scenario={scenario} rules={rules} entries={entries} at={editing} done={close} /> : null}
      </Dialog>
    </section>
  );
}

type FormProps = Props & { at: number; done: () => void };

function BelongingsForm({ scenario, rules, entries, at, done }: FormProps) {
  const pregen = scenario.pregens[at];
  const [stacks, setStacks] = useState<StackDraft[]>(() => stackDrafts(pregen?.items ?? []));
  const [money, setMoney] = useState(String(pregen?.money ?? 0));
  const saving = useScenarioSave(scenario.id);
  const hints = stacksHints(stacks, scenario.items);
  const moneyHint = wholeNumber(money, 0, MONEY_MAX) === null ? `0~${MONEY_MAX.toLocaleString('ko-KR')} 사이의 정수입니다.` : undefined;
  const blocked = Object.keys(hints).length > 0 || moneyHint !== undefined;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (blocked) return;
    const pregens = withBelongings(scenario.pregens, at, toStacks(stacks), Number(money.trim()));
    if (await saving.save(toPregensBody(pregens))) done();
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate aria-label="프리젠의 소지품">
      <ProblemNotice problem={saving.problem} />
      <StacksEditor
        label="소지품"
        drafts={stacks}
        onChange={setStacks}
        entries={entries}
        itemRules={scenario.items}
        rules={rules}
        hints={hints}
        max={MAX_STARTING_ITEMS}
      />
      <TextField
        label="더 받는 돈"
        inputMode="numeric"
        value={money}
        onChange={(event) => setMoney(event.target.value)}
        error={moneyHint}
      />
      {!scenario.currency && money.trim() !== '0' ? <p className="ui-field__hint">화폐가 없으면 게시 점검이 알립니다.</p> : null}
      <div className="actions">
        <Button type="submit" busy={saving.busy} disabled={blocked}>
          저장
        </Button>
      </div>
    </form>
  );
}
