// web/apps/web/src/pages/trpg/studio/scenarios/PlaceTrapsEditor.tsx
// 장소에 미리 놓인 덫의 줄들(B9 지도, #806 ②). 장소의 창 안에서 쓴다. 줄마다 덫 물건과 처음부터 아는 덫인가.
// 덫 물건은 아이템 규칙에 덫을 적은 물건만 고른다. 검사는 placesForm.ts.

import { Button, Checkbox, SelectField } from '@ai-trpg/ui';
import { MAX_TRAPS, newPlaceTrap, type PlaceTrapDraft } from './placesForm';
import type { EntryChoice } from './useLoreEntries';

type Props = {
  drafts: PlaceTrapDraft[];
  onChange: (drafts: PlaceTrapDraft[]) => void;
  /** 덫으로 놓을 수 있는 물건들 */
  entries: EntryChoice[];
  hints: Record<string, string>;
  /** 이 시나리오의 미리 놓인 덫이 모두 몇 개인가(이 장소 것 말고). 50 개까지다 */
  others: number;
};

export function PlaceTrapsEditor({ drafts, onChange, entries, hints, others }: Props) {
  const change = (index: number, changes: Partial<PlaceTrapDraft>) => onChange(drafts.map((one, at) => (at === index ? { ...one, ...changes } : one)));
  const full = others + drafts.length >= MAX_TRAPS;
  return (
    <div className="scenario-stacks">
      {drafts.length === 0 ? <p className="hint">미리 놓인 덫이 없습니다.</p> : null}
      {entries.length === 0 ? <p className="hint">덫을 적은 물건이 없습니다. 물건 탭의 아이템 규칙에서 덫을 적으세요.</p> : null}
      {drafts.map((draft, index) => (
        <fieldset key={index} className="scenario-stack">
          <legend>덫 {index + 1}</legend>
          <SelectField label="덫 물건" value={draft.entryId} onChange={(event) => change(index, { entryId: event.target.value })}>
            {draft.entryId === '' ? <option value="">고르기</option> : null}
            {draft.entryId !== '' && !entries.some((entry) => entry.id === draft.entryId) ? <option value={draft.entryId}>(덫이 아니거나 붙인 로어북에 없는 물건)</option> : null}
            {entries.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.name}
              </option>
            ))}
          </SelectField>
          <Checkbox
            label="처음부터 아는 덫"
            description="맵에 보이고 캐릭터가 밟지 않습니다. 해제할 수 있습니다."
            checked={draft.known}
            onChange={(event) => change(index, { known: event.target.checked })}
          />
          {hints[`trap.${index}`] ? <p className="ui-field__error">{hints[`trap.${index}`]}</p> : null}
          <Button variant="quiet" aria-label={`덫 ${index + 1} 지우기`} onClick={() => onChange(drafts.filter((_, at) => at !== index))}>
            지우기
          </Button>
        </fieldset>
      ))}
      <p>
        <Button variant="secondary" disabled={full || entries.length === 0} onClick={() => onChange([...drafts, newPlaceTrap(entries.map((entry) => entry.id))])}>
          덫 더하기
        </Button>
        {full ? <span className="hint"> 미리 놓인 덫은 시나리오 하나에 {MAX_TRAPS}개까지입니다.</span> : null}
      </p>
    </div>
  );
}
