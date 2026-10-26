// web/apps/web/src/pages/trpg/studio/scenarios/ItemLockFields.tsx
// 물건 규칙 창의 자물쇠 물건 칸(B9 물건·돈, #281). 장비일 때만 보인다. 켜면 새 열쇠와 따기(판정, 도구가 있어야 하는가)가 열린다.
// 검사는 itemLockForm.ts. 자물쇠 물건 자신은 열쇠로 고를 수 없게 목록에서 뺀다.

import { Checkbox } from '@ai-trpg/ui';
import type { Ruleset } from '../../../../api/types';
import { CheckSelects } from './CheckSelects';
import type { ItemLockDraft } from './itemLockForm';
import { ItemSelect } from './ItemSelect';
import type { EntryChoice } from './useLoreEntries';

type Props = {
  draft: ItemLockDraft;
  /** 이 물건 항목. 열쇠와 도구의 목록에서 뺀다 */
  entryId: string;
  items: EntryChoice[];
  rules: Ruleset | null;
  hints: Record<string, string>;
  onChange: (lock: ItemLockDraft) => void;
};

export function ItemLockFields({ draft, entryId, items, rules, hints, onChange }: Props) {
  const others = items.filter((item) => item.id !== entryId);
  const pick = (changes: Partial<ItemLockDraft['pick']>) => onChange({ ...draft, pick: { ...draft.pick, ...changes } });
  return (
    <fieldset className="scenario-choices">
      <legend>새 자물쇠</legend>
      <Checkbox
        label="문에 다는 새 자물쇠다"
        description="행동 '자물쇠 바꾸기'로 판에 자물쇠가 있던 문에 답니다. 달면 소지품에서 없어지고, 그 문은 새 열쇠로만 열립니다. 단 자물쇠는 열린 채입니다."
        checked={draft.on}
        onChange={(event) => onChange({ ...draft, on: event.target.checked })}
      />
      {draft.on ? (
        <>
          <ItemSelect label="새 열쇠" value={draft.key} items={others} empty="고르기" onChange={(key) => onChange({ ...draft, key })} error={hints.lock} />
          <Checkbox label="열쇠 없이 딸 수 있다" checked={draft.pick.on} onChange={(event) => pick({ on: event.target.checked })} />
          {draft.pick.on ? (
            <>
              <CheckSelects
                label="따기 판정"
                rules={rules}
                ability={draft.pick.ability}
                difficulty={draft.pick.difficulty}
                onChange={(changes) => pick(changes)}
                error={hints.lock_pick}
              />
              <Checkbox
                label="도구가 있어야 딴다"
                description="따기를 거드는 물건(물건 규칙의 거들기)을 붙여야 딸 수 있습니다."
                checked={draft.pick.needsTool}
                onChange={(event) => pick({ needsTool: event.target.checked })}
              />
            </>
          ) : null}
        </>
      ) : null}
    </fieldset>
  );
}
