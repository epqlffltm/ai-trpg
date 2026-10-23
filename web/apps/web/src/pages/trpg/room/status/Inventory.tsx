// web/apps/web/src/pages/trpg/room/status/Inventory.tsx
// 소지품(I). 캐릭터마다 가진 돈(화폐가 있는 판), 지닌 물건의 이름, 개수, 종류, 희귀도, 소모품의 회복량, 값. 나를 맨 앞에 둔다.
// 물건의 설명은 서버가 주지 않는다(로어북에 비밀이 있을 수 있다).
// 내 물건에는 쓰기(소모품), 건네기, 내려놓기(맵에 서 있을 때), 팔기(장면에 사 주는 상인이 있고 값이 있을 때) 단추가,
// 내 돈에는 돈 건네기 단추가 있다. 누르면 선언 입력의 행동 칸이 채워진다.
// 돈은 판 안의 돈이다. 결제의 크레딧과 섞이지 않게 "돈"이라 부른다(#278).

import { useQuery } from '@tanstack/react-query';
import type { HeldItem, TableDetail, TableMember } from '../../../../api/types';
import { amountLabel, itemPrice, merchantsBuy, moneyLabel, type Currency } from '../money';
import { openMerchants } from '../round/action/actionOptions';
import { sceneCastQuery } from '../round/roundQueries';
import { ActionButton, type ActionShortcuts } from './ActionButton';
import { healsLabel, itemLabel, meFirst } from './statusView';

type Props = { table: TableDetail; myId: string | undefined; shortcuts: ActionShortcuts };

/** 팔기 단추가 채울 상인. 사 주는 상인이 없으면 null, 한 명이면 그 상인, 여럿이면 빈 값(입력에서 고른다) */
type SellTo = string | null;

export function Inventory({ table, myId, shortcuts }: Props) {
  const sellTo = useSellTo(table);
  const holders = meFirst(table.members, myId).filter((member) => member.sheet && member.character);
  if (holders.length === 0) return <p className="hint">아직 물건을 가진 캐릭터가 없습니다.</p>;
  return (
    <div className="inventory">
      {holders.map((member) => (
        <section key={member.user_id} aria-label={`${member.character?.name}의 소지품`}>
          <h3 className="waiting-room__label">{member.character?.name}</h3>
          {table.currency ? (
            <Money member={member} currency={table.currency} shortcuts={member.user_id === myId ? shortcuts : null} />
          ) : null}
          {member.sheet && member.sheet.items.length > 0 ? (
            <ul className="plain-list items">
              {member.sheet.items.map((item) => (
                <li key={item.entry_id} className="item">
                  <span>
                    {item.name} <span className="item__count">×{item.count}</span>
                  </span>
                  <span className="hint">{itemNote(table, item)}</span>
                  {member.user_id === myId ? (
                    <ItemActions
                      item={item}
                      onMap={Boolean(table.map && member.sheet?.place_id)}
                      sellTo={itemPrice(table, item.entry_id) !== null ? sellTo : null}
                      shortcuts={shortcuts}
                    />
                  ) : null}
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

/** 장면에서 사 주는 상인. 장면은 선언 입력과 같은 읽기(sceneCastQuery)를 함께 쓴다 */
function useSellTo(table: TableDetail): SellTo {
  const enabled = table.status === 'playing' && merchantsBuy(table);
  const cast = useQuery({ ...sceneCastQuery(table.id), enabled });
  if (!enabled) return null;
  const open = openMerchants(cast.data);
  if (open.length === 0) return null;
  return open.length === 1 ? `npc:${open[0]?.id ?? ''}` : '';
}

/** "소모품 · 노말 · 회복 가벼움(1d4) · 값 5닢" */
function itemNote(table: TableDetail, item: HeldItem): string {
  const heals = item.kind === 'consumable' ? healsLabel(table, item.entry_id) : null;
  const price = itemPrice(table, item.entry_id);
  return [itemLabel(item), heals, price !== null ? `값 ${amountLabel(table.currency, price)}` : null].filter(Boolean).join(' · ');
}

function Money({ member, currency, shortcuts }: { member: TableMember; currency: Currency; shortcuts: ActionShortcuts }) {
  const money = member.sheet?.money ?? 0;
  return (
    <p className="money">
      <span>돈 {moneyLabel(currency, money)}</span>
      {shortcuts && money > 0 ? (
        <span className="action-chips">
          <ActionButton shortcuts={shortcuts} patch={{ kind: 'pay', amount: 1, target: '' }} label="건네기" what="돈" />
        </span>
      ) : null}
    </p>
  );
}

type ItemActionsProps = { item: HeldItem; onMap: boolean; sellTo: SellTo; shortcuts: ActionShortcuts };

function ItemActions({ item, onMap, sellTo, shortcuts }: ItemActionsProps) {
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
      {sellTo !== null ? (
        <ActionButton shortcuts={shortcuts} patch={{ kind: 'sell', item: item.entry_id, count: 1, target: sellTo }} label="팔기" what={item.name} />
      ) : null}
    </span>
  );
}
