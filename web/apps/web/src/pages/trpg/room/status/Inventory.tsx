// web/apps/web/src/pages/trpg/room/status/Inventory.tsx
// 소지품(I). 캐릭터마다 지닌 물건의 이름, 개수, 종류, 희귀도, 소모품의 회복량. 나를 맨 앞에 둔다.
// 물건의 설명은 서버가 주지 않는다(로어북에 비밀이 있을 수 있다).
// 내 물건에는 쓰기(소모품), 건네기, 내려놓기(맵에 서 있을 때) 단추가 있다. 누르면 선언 입력의 행동 칸이 채워진다.

import type { HeldItem, TableDetail } from '../../../../api/types';
import { ActionButton, type ActionShortcuts } from './ActionButton';
import { healsLabel, itemLabel, meFirst } from './statusView';

type Props = { table: TableDetail; myId: string | undefined; shortcuts: ActionShortcuts };

export function Inventory({ table, myId, shortcuts }: Props) {
  const holders = meFirst(table.members, myId).filter((member) => member.sheet && member.character);
  if (holders.length === 0) return <p className="hint">아직 물건을 가진 캐릭터가 없습니다.</p>;
  return (
    <div className="inventory">
      {holders.map((member) => (
        <section key={member.user_id} aria-label={`${member.character?.name}의 소지품`}>
          <h3 className="waiting-room__label">{member.character?.name}</h3>
          {member.sheet && member.sheet.items.length > 0 ? (
            <ul className="plain-list items">
              {member.sheet.items.map((item) => (
                <li key={item.entry_id} className="item">
                  <span>
                    {item.name} <span className="item__count">×{item.count}</span>
                  </span>
                  <span className="hint">
                    {itemLabel(item)}
                    {item.kind === 'consumable' && healsLabel(table, item.entry_id) ? ` · ${healsLabel(table, item.entry_id)}` : ''}
                  </span>
                  {member.user_id === myId ? <ItemActions item={item} onMap={Boolean(table.map && member.sheet?.place_id)} shortcuts={shortcuts} /> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="hint">지닌 물건이 없습니다.</p>
          )}
        </section>
      ))}
    </div>
  );
}

function ItemActions({ item, onMap, shortcuts }: { item: HeldItem; onMap: boolean; shortcuts: ActionShortcuts }) {
  if (!shortcuts) return null;
  return (
    <span className="action-chips">
      {item.kind === 'consumable' ? (
        <ActionButton shortcuts={shortcuts} patch={{ kind: 'use', item: item.entry_id, target: '' }} label="쓰기" what={item.name} />
      ) : null}
      <ActionButton shortcuts={shortcuts} patch={{ kind: 'give', item: item.entry_id, count: 1 }} label="건네기" what={item.name} />
      {onMap ? (
        <ActionButton shortcuts={shortcuts} patch={{ kind: 'put_down', item: item.entry_id, count: 1 }} label="내려놓기" what={item.name} />
      ) : null}
    </span>
  );
}
