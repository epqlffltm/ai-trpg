// web/apps/web/src/pages/trpg/room/RoomStage.tsx
// 테이블 방의 가운데. 테이블의 상태마다 다르다.
//   - 모집 중: 대기실(초대 코드, 시작하는 장면, 내 캐릭터 정하기(B5), 방장의 시작)
//   - 진행 중: 라운드(서술, 선언, 판정, 미리 보기, 방장의 닫기)
//   - 끝남: 최근의 라운드를 읽기만 한다. 지난 판의 읽기(B10)는 다음이다

import type { TableDetail } from '../../../api/types';
import type { NarrationPreview } from './round/preview';
import { RoundStage } from './round/RoundStage';
import { WaitingRoom } from './WaitingRoom';

type Props = {
  table: TableDetail;
  myId: string | undefined;
  preview: NarrationPreview | null;
  nameOfMember: (userId: string) => string;
};

export function RoomStage({ table, myId, preview, nameOfMember }: Props) {
  if (table.status === 'recruiting') return <WaitingRoom table={table} myId={myId} />;
  return <RoundStage table={table} myId={myId} preview={preview} nameOfMember={nameOfMember} />;
}
