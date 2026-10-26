// web/apps/web/src/pages/trpg/room/round/action/DoorActionFields.tsx
// 문을 다루는 행동(#281)의 칸. 내 장소에 닿은 길 가운데 그 행동을 할 수 있어 보이는 문을 고르고,
// 잠그기와 열기는 그 문에서 다룰 수 있는 장치가 둘이면 장치를 고른다. 자물쇠 바꾸기는 지닌 자물쇠 물건을 고른다. 판정을 쓰는 행동은 판의 능력치와 난이도를 알린다.
// 따기, 부수기, 고치기는 거드는 물건(#802)을 붙인다. 도구가 있어야 하는 문(판의 needs_tool)이면 꼭 고른다.
// 고를 거리와 거르기는 doorOptions.ts, 보내는 모양은 actionDraft.ts 다.

import type { DoorDevice, Ruleset, TableMap } from '../../../../../api/types';
import type { ActionDraft } from './actionDraft';
import { hereId, type ActionContext } from './actionOptions';
import { AidSelect } from './AidSelect';
import { ChoiceSelect } from './ChoiceSelect';
import { deviceLabel, doorDevices, doorsFor, doorState, lockItems, type DoorKind } from './doorOptions';

type Props = {
  kind: DoorKind;
  draft: ActionDraft;
  ctx: ActionContext;
  onChange: (changes: Partial<ActionDraft>) => void;
};

const KIND_HINTS: Record<DoorKind, string> = {
  unlock: '자물쇠는 그 열쇠를 지닌 사람이, 빗장은 빗장 쪽에 선 사람이 엽니다. 굴리지 않습니다. 지나가지는 않습니다.',
  lock: '자물쇠는 그 열쇠를 지닌 사람이, 빗장은 빗장 쪽에 선 사람이 잠급니다. 굴리지 않습니다. 부서진 문은 잠그지 못합니다.',
  pick: '열쇠 없이 잠긴 자물쇠를 땁니다. 도구가 있어야 하는 자물쇠는 따기를 거드는 물건을 붙여야 합니다. 빗장은 따지 못합니다.',
  force: '자물쇠와 빗장을 부숴 엽니다. 부서진 문은 고치기 전까지 다시 잠그지 못합니다.',
  repair: '부서진 문을 고칩니다. 고친 문은 열린 채입니다. 도구가 있어야 하는 문은 고치기를 거드는 물건을 붙여야 합니다.',
  replace: '열린 문의 자물쇠를 지닌 자물쇠 물건으로 바꿔 답니다. 굴리지 않습니다. 단 물건은 없어지고, 그 뒤로는 그 자물쇠의 열쇠만 통합니다.',
};

export function DoorActionFields({ kind, draft, ctx, onChange }: Props) {
  const map = ctx.table.map;
  const here = hereId(ctx);
  if (!map || !here) return null;
  const doors = doorsFor(kind, map, here);
  const door = doors.find((one) => one.place === draft.place);
  const devices = door && (kind === 'lock' || kind === 'unlock') ? doorDevices(kind, door.route, here) : [];
  const check = door ? checkOf(kind, door.route) : null;
  return (
    <>
      <div className="ability-grid">
        <ChoiceSelect
          label="문"
          value={draft.place}
          choices={doors.map((one) => ({ value: one.place, label: `${one.name} 쪽 문(${doorState(one, map)})` }))}
          empty="고르기"
          onChange={(place) => onChange({ place, device: '' })}
        />
        {kind === 'replace' ? (
          <ChoiceSelect
            label="달 자물쇠"
            value={draft.item}
            choices={lockItems(ctx.table, ctx.me).map((item) => ({ value: item.entry_id, label: `${item.name} ×${item.count}` }))}
            empty="고르기"
            onChange={(item) => onChange({ item })}
          />
        ) : null}
        {kind === 'pick' || kind === 'force' || kind === 'repair' ? (
          <AidSelect act={kind} value={draft.item} ctx={ctx} required={check?.needs_tool === true} onChange={(item) => onChange({ item })} />
        ) : null}
        {devices.length > 1 ? (
          <ChoiceSelect
            label="장치"
            value={draft.device || (devices[0] ?? '')}
            choices={devices.map((device: DoorDevice) => ({ value: device, label: deviceLabel(device) }))}
            onChange={(device) => onChange({ device })}
          />
        ) : null}
      </div>
      <p className="hint">
        {KIND_HINTS[kind]}
        {check ? ` ${checkText(check, ctx.table.rules)}` : ''}
      </p>
    </>
  );
}

type RouteCheck = { ability: string; difficulty: string; needs_tool?: boolean };

/** 그 행동이 굴리는 판의 판정. 잠그기와 열기는 굴리지 않는다 */
function checkOf(kind: DoorKind, route: TableMap['routes'][number]): RouteCheck | null {
  if (kind === 'pick') return route.pick ?? null;
  if (kind === 'force') return route.force ?? null;
  if (kind === 'repair') return route.repair ?? null;
  return null;
}

/** "판정: 근력, 보통." 결과는 라운드를 마감할 때 서버가 굴린다 */
function checkText(check: RouteCheck, rules: Ruleset): string {
  const ability = rules.abilities.find((one) => one.key === check.ability)?.name ?? check.ability;
  const difficulty = rules.difficulties.find((one) => one.key === check.difficulty)?.name ?? check.difficulty;
  return `판정: ${ability}, ${difficulty}. 실패하면 아무 일도 없습니다.`;
}
