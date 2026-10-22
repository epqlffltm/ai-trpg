// web/apps/web/src/pages/trpg/room/RoomStage.tsx
// 테이블 방의 가운데. 테이블의 상태마다 다르다.
//   - 모집 중: 대기실(초대 코드, 시작하는 장면, 내 캐릭터 정하기(B5), 방장의 시작)
//   - 진행 중: 라운드(서술, 선언, 판정)는 다음이다
//   - 끝남: 끝났다는 안내. 지난 판의 읽기(B10)는 다음이다

import { Notice } from '@ai-trpg/ui';
import type { TableDetail } from '../../../api/types';
import { WaitingRoom } from './WaitingRoom';

export function RoomStage({ table, myId }: { table: TableDetail; myId: string | undefined }) {
  switch (table.status) {
    case 'recruiting':
      return <WaitingRoom table={table} myId={myId} />;
    case 'playing':
      return (
        <section aria-label="라운드">
          <Notice>진행 중입니다. 서술과 선언의 화면은 준비 중입니다.</Notice>
        </section>
      );
    case 'ended':
      return (
        <section aria-label="끝난 테이블">
          <Notice>끝난 테이블입니다. 채팅은 읽기만 할 수 있습니다.</Notice>
        </section>
      );
  }
}
