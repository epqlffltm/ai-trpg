// web/apps/web/src/pages/trpg/room/status/EquipmentList.tsx
// 한 캐릭터의 장비(#276). 칸마다 착용한 것(여러 칸을 차지한 것은 한 줄), 그 공격과 방어, 모든 부위의 방어와 방어가 하는 일.
// 내 캐릭터면 칸마다 "벗기"가 있다. 착용은 소지품의 물건 줄에서 한다(WearButton). 바꿀 수 없는 때는 단추를 막는다.

import { Button } from '@ai-trpg/ui';
import type { Sheet, TableDetail } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { armorModeLabel, equipmentRows, gearLabel, guardOf } from './equipmentView';
import type { Equipment } from './useEquipment';

type Props = { table: TableDetail; sheet: Sheet; name: string; equipment: Equipment | null };

export function EquipmentList({ table, sheet, name, equipment }: Props) {
  if (table.rules.equipment_slots.length === 0) return null;
  const guard = guardOf(table, sheet);
  const mode = armorModeLabel(table);
  return (
    <div className="equipment" aria-label={`${name}의 장비`} role="group">
      <ul className="plain-list equipment__rows">
        {equipmentRows(table, sheet).map((row) => (
          <li key={row.slots.join('+')} className="equipment__row">
            <span className="equipment__slot">{row.label}</span>
            <span className={row.worn ? 'equipment__item' : 'equipment__item hint'}>
              {row.worn ? row.worn.name : '비어 있음'}
              {row.worn && gearLabel(table, row.worn.entry_id) ? <span className="hint"> · {gearLabel(table, row.worn.entry_id)}</span> : null}
            </span>
            {equipment && row.worn ? (
              <Button
                variant="quiet"
                aria-label={`${row.worn.name} 벗기`}
                disabled={!equipment.enabled || equipment.busy}
                onClick={() => void equipment.takeOff(row.slots[0] ?? '')}
              >
                벗기
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
      {guard > 0 || mode ? (
        <p className="hint equipment__note">
          {guard > 0 ? `모든 부위 방어 +${guard}` : ''}
          {guard > 0 && mode ? ' · ' : ''}
          {mode ? `방어는 ${mode}` : ''}
        </p>
      ) : null}
      {equipment ? <ProblemNotice problem={equipment.problem} /> : null}
    </div>
  );
}
