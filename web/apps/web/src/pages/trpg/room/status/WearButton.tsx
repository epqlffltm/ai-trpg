// web/apps/web/src/pages/trpg/room/status/WearButton.tsx
// 소지품의 물건 하나를 착용하는 단추(#276). 들어갈 칸이 정해져 있으면 바로 끼운다.
// 고를 수 있으면(들어갈 칸이 차지하는 칸보다 많다) 창을 열어 차지할 칸을 고른다. 찬 칸에 끼우면 서버가 그 칸의 것을 벗긴다.

import { Button, Checkbox, Dialog } from '@ai-trpg/ui';
import { useCallback, useState } from 'react';
import type { HeldItem, Sheet, TableDetail } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { fixedSlots, slotsLabel, wearSlots, wornOf } from './equipmentView';
import type { Equipment } from './useEquipment';

type Props = { table: TableDetail; sheet: Sheet; item: HeldItem; equipment: Equipment };

export function WearButton({ table, sheet, item, equipment }: Props) {
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<string[]>([]);
  const close = useCallback(() => setOpen(false), []);
  const fixed = fixedSlots(table, item.entry_id);
  const choice = wearSlots(table, item.entry_id);
  if (!choice) return null;

  function start() {
    if (fixed) {
      void equipment.wear(item.entry_id, fixed);
      return;
    }
    setChosen([]);
    setOpen(true);
  }

  async function confirm() {
    if (await equipment.wear(item.entry_id, chosen)) setOpen(false);
  }

  function toggle(slot: string, on: boolean) {
    setChosen((current) => (on ? [...current, slot] : current.filter((key) => key !== slot)));
  }

  return (
    <>
      <button
        type="button"
        className="action-chip"
        disabled={!equipment.enabled || equipment.busy}
        aria-label={`${item.name} 착용`}
        onClick={start}
      >
        착용
      </button>
      <Dialog title={`${item.name} 착용`} open={open} onClose={close}>
        <p>칸 {choice.count}개를 고르세요. 찬 칸에 끼우면 그 칸의 것을 벗습니다.</p>
        <fieldset className="choice-list">
          <legend>칸</legend>
          {choice.allowed.map((slot) => {
            const holder = wornOf(sheet).find((one) => one.slots.includes(slot));
            return (
              <Checkbox
                key={slot}
                label={slotsLabel(table, [slot])}
                description={holder ? `지금 ${holder.name}` : undefined}
                checked={chosen.includes(slot)}
                disabled={!chosen.includes(slot) && chosen.length >= choice.count}
                onChange={(event) => toggle(slot, event.target.checked)}
              />
            );
          })}
        </fieldset>
        <ProblemNotice problem={equipment.problem} />
        <div className="actions">
          <Button busy={equipment.busy} disabled={chosen.length !== choice.count} onClick={() => void confirm()}>
            착용하기
          </Button>
        </div>
      </Dialog>
    </>
  );
}
