// web/apps/web/src/pages/trpg/room/status/StatusPanel.tsx
// 테이블 방 왼쪽 열의 창 넷(B7, Stitch 20번). 단추 넷이 세로로 서고, 누른 단추 바로 아래로 그 창이 펼쳐진다.
// 창은 하나만 펼친다(다른 단추를 누르면 앞의 창은 접힌다). 펼친 단추를 다시 누르면 접는다. 처음에는 상태·장비가 펼쳐져 있다.
//   - 상태·장비(C): 내 캐릭터의 HP, 자원, 레벨과 점수 놓기(#286), 부상, 능력치, 착용한 장비와 칸마다 벗기(#276)
//   - 소지품·돈(I): 캐릭터마다 돈, 지닌 물건, 내 물건의 착용(Inventory)
//   - 퀘스트·지도(J): 게임 안의 시각, 퀘스트, 장소와 길(WorldInfo)
//   - 일행·기록(L): 앉은 사람마다의 캐릭터와 장비(CharacterCards, 읽기만)와 일어난 일(EventLog)
// 상태를 바꾸지 않는다. 값은 이벤트가 오면 테이블을 다시 읽어 바뀐다(useBatchedRefetch).
// 물건과 장소의 단추는 선언 입력의 행동 칸을 채울 뿐이다(useActionShortcuts). 보내는 것은 선언이다.
// 점수 놓기는 선언이 아니라 바로 바꾼다(useRaise).

import { useCallback, useState, type ReactNode } from 'react';
import type { TableDetail, TableMember } from '../../../../api/types';
import type { NameLookup } from '../../../../hooks/usePublicNames';
import { EventLog } from '../events/EventLog';
import { displayName } from '../MemberList';
import { CharacterCards } from './CharacterCards';
import { EquipmentList } from './EquipmentList';
import { Inventory } from './Inventory';
import { RaiseButton } from './RaiseButton';
import { nextOpenTab, STATUS_TABS, type StatusTab } from './statusTabs';
import { useActionShortcuts } from './useActionShortcuts';
import { useEquipment } from './useEquipment';
import { useRaise } from './useRaise';
import { useStatusShortcuts } from './useStatusShortcuts';
import { WorldInfo } from './WorldInfo';

type Props = { table: TableDetail; myId: string | undefined; nameOf: NameLookup };

export function StatusPanel({ table, myId, nameOf }: Props) {
  const [open, setOpen] = useState<StatusTab | null>('mine');
  const openOnly = useCallback((tab: StatusTab) => setOpen(tab), []);
  useStatusShortcuts(openOnly);
  return (
    <section className="room-tools" aria-labelledby="status-heading">
      <h2 id="status-heading" className="visually-hidden">
        상태
      </h2>
      {STATUS_TABS.map((entry) => (
        <div key={entry.tab} className="room-tools__item">
          <button
            type="button"
            id={`status-button-${entry.tab}`}
            className="room-tools__button"
            aria-expanded={open === entry.tab}
            aria-controls={`status-panel-${entry.tab}`}
            aria-keyshortcuts={entry.key.toUpperCase()}
            onClick={() => setOpen((current) => nextOpenTab(current, entry.tab))}
          >
            <span>{entry.label}</span> <kbd>{entry.key.toUpperCase()}</kbd>
          </button>
          {open === entry.tab ? (
            <div id={`status-panel-${entry.tab}`} role="region" aria-labelledby={`status-button-${entry.tab}`} className="room-tools__panel">
              <StatusContent tab={entry.tab} table={table} myId={myId} nameOf={nameOf} />
            </div>
          ) : null}
        </div>
      ))}
    </section>
  );
}

function StatusContent({ tab, table, myId, nameOf }: Props & { tab: StatusTab }): ReactNode {
  if (tab === 'mine') return <MineContent table={table} myId={myId} nameOf={nameOf} />;
  if (tab === 'items') return <ItemsContent table={table} myId={myId} />;
  if (tab === 'world') return <WorldContent table={table} myId={myId} />;
  return (
    <>
      <CharacterCards members={table.members} rules={table.rules} myId={myId} nameOf={nameOf} gearOf={(member) => readOnlyGear(table, member)} />
      <EventLog table={table} nameOfMember={(userId) => displayName(userId, table.members, nameOf)} />
    </>
  );
}

/** 상태·장비. 앉아 있지 않거나 캐릭터를 아직 정하지 않았으면 그렇다고만 적는다 */
function MineContent({ table, myId, nameOf }: Props) {
  const raising = useRaise(table, myId);
  const equipment = useEquipment(table, myId);
  const mine = findMine(table, myId);
  if (!mine?.sheet) return <p className="hint">내 캐릭터가 없습니다.</p>;
  const playing = table.status === 'playing';
  return (
    <>
      <CharacterCards
        members={[mine]}
        rules={table.rules}
        myId={myId}
        nameOf={nameOf}
        gearOf={(member) =>
          member.sheet ? (
            <EquipmentList table={table} sheet={member.sheet} name={member.character?.name ?? ''} equipment={playing ? equipment : null} />
          ) : null
        }
      />
      {table.rules.progression ? <RaiseButton sheet={mine.sheet} rules={table.rules} raising={raising} /> : null}
    </>
  );
}

function ItemsContent({ table, myId }: { table: TableDetail; myId: string | undefined }) {
  const shortcuts = useActionShortcuts(table, myId);
  return <Inventory table={table} myId={myId} shortcuts={shortcuts} />;
}

function WorldContent({ table, myId }: { table: TableDetail; myId: string | undefined }) {
  const shortcuts = useActionShortcuts(table, myId);
  return <WorldInfo table={table} mine={findMine(table, myId)} shortcuts={shortcuts} />;
}

/** 일행·기록의 카드에 붙일 장비. 단추 없이 읽기만 한다 */
function readOnlyGear(table: TableDetail, member: TableMember): ReactNode {
  if (!member.sheet) return null;
  return <EquipmentList table={table} sheet={member.sheet} name={member.character?.name ?? ''} equipment={null} />;
}

function findMine(table: TableDetail, myId: string | undefined): TableMember | undefined {
  return table.members.find((member) => member.user_id === myId);
}
