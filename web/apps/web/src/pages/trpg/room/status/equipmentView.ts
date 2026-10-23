// web/apps/web/src/pages/trpg/room/status/equipmentView.ts
// 장비(#276)를 보일 글과 고를 것. 순수한 함수다. 착용한 것은 서버가 준 것(sheet.worn, 규칙의 칸의 차례)을 그대로 쓴다.
//
//   - 칸은 규칙의 장비의 칸(rules.equipment_slots)이다. 여러 칸을 차지한 물건(두 손 검)은 한 줄로 묶어 보인다
//   - 공격과 방어는 판의 물건(TableDetail.items)의 attack, defense, guard 를 착용에 맞춰 더한다(서버의 app/engine/armor.py 와 같다).
//     부위의 방어 = 그 칸을 차지한 것의 방어 + 착용한 모든 것의 모든 부위 방어(guard)
//   - 무기의 관통력(ap)과 불굴 세이브(ward)도 판의 물건에서 읽는다. 불굴 세이브는 더하지 않고 착용한 것 중 가장 큰 값이다
//   - 착용과 벗기는 선언이 아니라 바로 바꾼다. 진행 중이고 라운드가 선언을 받는 중이며, 내 캐릭터가 서 있을 때만 된다

import type { HeldItem, Round, Sheet, TableDetail, TableMember } from '../../../../api/types';

type Worn = Sheet['worn'][number];
type Catalog = TableDetail['items'][number];

/** 장비의 한 줄. 빈 칸이면 worn 이 null 이다. 여러 칸을 차지한 것은 그 칸들이 한 줄이다 */
export type EquipmentRow = { slots: string[]; label: string; worn: Worn | null };

const ARMOR_MODES: Record<string, string> = { ac: '맞히기 어렵게', reduce: '피해를 깎음', save: '세이브로 막음' };

function catalogItem(table: TableDetail, entryId: string): Catalog | undefined {
  return table.items.find((item) => item.entry_id === entryId);
}

/** 물건이 들어갈 칸. 서버는 늘 싣는다(없으면 빈 목록). 칸이 생기기 전의 모양이어도 깨지지 않게 비어 있으면 빈 목록으로 본다 */
function slotsOf(item: Catalog | undefined): string[] {
  return item?.slots ?? [];
}

/** 착용한 것. 위와 같은 까닭으로 비어 있으면 빈 목록 */
export function wornOf(sheet: Sheet): Worn[] {
  return sheet.worn ?? [];
}

function slotName(table: TableDetail, key: string): string {
  return table.rules.equipment_slots.find((slot) => slot.key === key)?.name ?? key;
}

/** 칸들의 이름. "주손·보조손" */
export function slotsLabel(table: TableDetail, keys: string[]): string {
  return keys.map((key) => slotName(table, key)).join('·');
}

/** 규칙의 칸의 차례로 줄을 만든다. 차지한 물건이 있으면 그 물건의 칸을 모두 묶는다 */
export function equipmentRows(table: TableDetail, sheet: Sheet): EquipmentRow[] {
  const rows: EquipmentRow[] = [];
  const shown = new Set<string>();
  for (const slot of table.rules.equipment_slots) {
    if (shown.has(slot.key)) continue;
    const worn = wornOf(sheet).find((one) => one.slots.includes(slot.key)) ?? null;
    const slots = worn ? worn.slots : [slot.key];
    for (const key of slots) shown.add(key);
    rows.push({ slots, label: slotsLabel(table, slots), worn });
  }
  return rows;
}

/** 물건 하나의 공격과 방어. "공격 +2 · 관통 1 · 방어 5 · 모든 부위 +1 · 불굴 세이브 4". 없으면 null */
export function gearLabel(table: TableDetail, entryId: string): string | null {
  const item = catalogItem(table, entryId);
  if (!item) return null;
  const parts = [
    item.attack ? `공격 +${item.attack}` : null,
    item.ap ? `관통 ${item.ap}` : null,
    item.defense ? `방어 ${item.defense}` : null,
    item.guard ? `모든 부위 +${item.guard}` : null,
    item.ward ? `불굴 세이브 ${item.ward}` : null,
  ];
  const text = parts.filter(Boolean).join(' · ');
  return text || null;
}

/** 착용한 모든 것의 모든 부위 방어(guard)의 합 */
export function guardOf(table: TableDetail, sheet: Sheet): number {
  return wornOf(sheet).reduce((sum, one) => sum + (catalogItem(table, one.entry_id)?.guard ?? 0), 0);
}

/** 착용한 것의 불굴 세이브. 더하지 않고 가장 큰 값이다(서버와 같다). 없으면 0 */
export function wardOf(table: TableDetail, sheet: Sheet): number {
  return Math.max(0, ...wornOf(sheet).map((one) => catalogItem(table, one.entry_id)?.ward ?? 0));
}

/** 그 칸(부위)의 방어. 차지한 것의 방어와 모든 부위 방어를 더한다 */
export function defenseAt(table: TableDetail, sheet: Sheet, slot: string): number {
  const worn = wornOf(sheet).find((one) => one.slots.includes(slot));
  const own = worn ? (catalogItem(table, worn.entry_id)?.defense ?? 0) : 0;
  return own + guardOf(table, sheet);
}

/** 방어가 하는 일. 세이브면 목표값을 붙인다("세이브로 막음(목표 7)"). 방어 방식이 없는 규칙이면 null(방어구가 막지 않는다) */
export function armorModeLabel(table: TableDetail): string | null {
  const armor = table.rules.armor;
  if (!armor) return null;
  const label = ARMOR_MODES[armor.mode] ?? armor.mode;
  return armor.mode === 'save' && armor.save_target ? `${label}(목표 ${armor.save_target})` : label;
}

/** 장비 아래의 한 줄. "모든 부위 방어 +1 · 불굴 세이브 4 · 방어는 세이브로 막음(목표 7)". 적을 것이 없으면 null */
export function equipmentNote(table: TableDetail, sheet: Sheet): string | null {
  const guard = guardOf(table, sheet);
  const ward = wardOf(table, sheet);
  const mode = armorModeLabel(table);
  const parts = [guard > 0 ? `모든 부위 방어 +${guard}` : null, ward > 0 ? `불굴 세이브 ${ward}` : null, mode ? `방어는 ${mode}` : null];
  const text = parts.filter(Boolean).join(' · ');
  return text || null;
}

/** 착용하는 물건인가(들어갈 칸이 있다) */
export function isWearable(table: TableDetail, entryId: string): boolean {
  return slotsOf(catalogItem(table, entryId)).length > 0;
}

/** 이미 착용한 물건인가 */
export function isWorn(sheet: Sheet, entryId: string): boolean {
  return wornOf(sheet).some((one) => one.entry_id === entryId);
}

/** 착용할 물건. 가진 것 가운데 칸이 있고 아직 착용하지 않은 것 */
export function wearableItems(table: TableDetail, sheet: Sheet): HeldItem[] {
  return sheet.items.filter((item) => isWearable(table, item.entry_id) && !isWorn(sheet, item.entry_id));
}

/** 착용할 칸을 고를 거리. 들어갈 칸과 차지하는 칸의 수. 물건이 판에 없으면 null */
export function wearSlots(table: TableDetail, entryId: string): { allowed: string[]; count: number } | null {
  const item = catalogItem(table, entryId);
  const allowed = slotsOf(item);
  return item && allowed.length > 0 ? { allowed, count: item.slot_count } : null;
}

/** 고를 것이 없으면(들어갈 칸의 수와 차지하는 칸의 수가 같다) 그 칸들. 골라야 하면 null */
export function fixedSlots(table: TableDetail, entryId: string): string[] | null {
  const choice = wearSlots(table, entryId);
  return choice && choice.allowed.length === choice.count ? choice.allowed : null;
}

/** 지금 장비를 바꿀 수 있는가. 진행 중, 라운드가 선언을 받는 중, 내 캐릭터가 살아서 서 있다 */
export function canChangeEquipment(table: TableDetail, me: TableMember | undefined, round: Round | undefined): boolean {
  if (table.status !== 'playing' || round?.status !== 'open') return false;
  return Boolean(me?.sheet && !me.sheet.dead && me.sheet.hp > 0);
}
