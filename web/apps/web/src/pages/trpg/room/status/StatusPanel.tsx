// web/apps/web/src/pages/trpg/room/status/StatusPanel.tsx
// 상태 패널(B7). 진행 중과 끝난 테이블의 옆에 둔다. 위에 내 HP 한 줄을 늘 보이고, 아래는 탭으로 나눈다.
//   - 캐릭터(C): 앉은 사람마다 HP, 부상, 능력치, 떠난 캐릭터
//   - 소지품(I): 캐릭터마다 지닌 물건
//   - 퀘스트·장소(J): 게임 안의 시각, 퀘스트, 장소와 길
// 상태를 바꾸지 않는다. 값은 이벤트가 오면 테이블을 다시 읽어 바뀐다(useBatchedRefetch).
// 물건과 장소의 단추는 선언 입력의 행동 칸을 채울 뿐이다(useActionShortcuts). 보내는 것은 선언이다.

import { useState } from 'react';
import type { TableDetail } from '../../../../api/types';
import type { NameLookup } from '../../../../hooks/usePublicNames';
import { CharacterCards } from './CharacterCards';
import { HpBar } from './HpBar';
import { Inventory } from './Inventory';
import { STATUS_TABS, type StatusTab } from './statusTabs';
import { useActionShortcuts } from './useActionShortcuts';
import { useStatusShortcuts } from './useStatusShortcuts';
import { WorldInfo } from './WorldInfo';

type Props = { table: TableDetail; myId: string | undefined; nameOf: NameLookup };

export function StatusPanel({ table, myId, nameOf }: Props) {
  const [tab, setTab] = useState<StatusTab>('characters');
  useStatusShortcuts(setTab);
  const shortcuts = useActionShortcuts(table, myId);
  const mine = table.members.find((member) => member.user_id === myId);
  return (
    <section className="room-panel status" aria-labelledby="status-heading">
      <h2 id="status-heading">상태</h2>
      {mine?.sheet ? (
        <div className="status__mine">
          <span className="status-card__name">{mine.character?.name}</span>
          <HpBar sheet={mine.sheet} rules={table.rules} />
        </div>
      ) : null}
      <div className="status__tabs" role="tablist" aria-label="상태 패널">
        {STATUS_TABS.map((entry) => (
          <button
            key={entry.tab}
            type="button"
            role="tab"
            id={`status-tab-${entry.tab}`}
            aria-selected={tab === entry.tab}
            aria-controls="status-tabpanel"
            aria-keyshortcuts={entry.key.toUpperCase()}
            className="status__tab"
            onClick={() => setTab(entry.tab)}
          >
            {entry.label} <kbd>{entry.key.toUpperCase()}</kbd>
          </button>
        ))}
      </div>
      <div id="status-tabpanel" role="tabpanel" aria-labelledby={`status-tab-${tab}`} className="status__body">
        {tab === 'characters' ? <CharacterCards members={table.members} rules={table.rules} myId={myId} nameOf={nameOf} /> : null}
        {tab === 'items' ? <Inventory table={table} myId={myId} shortcuts={shortcuts} /> : null}
        {tab === 'world' ? <WorldInfo table={table} mine={mine} shortcuts={shortcuts} /> : null}
      </div>
    </section>
  );
}
