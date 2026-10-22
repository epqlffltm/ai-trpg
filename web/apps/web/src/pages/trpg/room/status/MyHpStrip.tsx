// web/apps/web/src/pages/trpg/room/status/MyHpStrip.tsx
// 좁은 화면(모바일)에서 가운데 맨 위에 늘 보이는 내 HP 한 줄(B7 의 "PC 와 모바일"). 넓은 화면에서는 CSS 가 숨긴다
// (상태 패널이 옆에 늘 열려 있어서). 내 캐릭터의 시트가 없으면 보이지 않는다.

import type { TableDetail } from '../../../../api/types';
import { HpBar } from './HpBar';

export function MyHpStrip({ table, myId }: { table: TableDetail; myId: string | undefined }) {
  const mine = table.members.find((member) => member.user_id === myId);
  if (!mine?.sheet) return null;
  return (
    <div className="hp-strip" aria-label="내 HP">
      <span className="status-card__name">{mine.character?.name}</span>
      <HpBar sheet={mine.sheet} rules={table.rules} />
    </div>
  );
}
