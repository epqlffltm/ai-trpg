// web/apps/web/src/pages/trpg/room/status/Inventory.tsx
// 소지품(I). 캐릭터마다 지닌 물건의 이름, 개수, 종류, 희귀도, 소모품의 회복량. 나를 맨 앞에 둔다.
// 물건의 설명은 서버가 주지 않는다(로어북에 비밀이 있을 수 있다). 쓰기와 건네기는 선언으로 한다(③-2).

import type { TableDetail } from '../../../../api/types';
import { healsLabel, itemLabel, meFirst } from './statusView';

export function Inventory({ table, myId }: { table: TableDetail; myId: string | undefined }) {
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
