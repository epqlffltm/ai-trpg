// web/apps/web/src/pages/trpg/room/events/achievementNoticeView.ts
// 테이블 방의 "업적을 얻었다" 알림. 일어난 일 가운데 방금 닫힌 라운드에 받은 판의 업적(achievement_earned)을 고른다. 순수한 함수다.
// 판의 업적은 제작자가 작품에 단 것이다(docs/architecture/achievements.md). 엔진이 라운드를 닫을 때 주고, 이벤트로 알린다.
//
// - 업적은 라운드 N 이 닫힐 때 받는다(payload.round = N). 그 서술이 끝나 라운드 N+1 이 열려도 그 라운드 동안은 보인다.
//   라운드 N+1 이 닫혀 N+2 가 열리면 저절로 사라진다. 지난 업적은 일어난 일의 기록에 남는다
// - 받은 사람은 그때 캐릭터를 갖고 앉아 있던 모두다(payload.users). 캐릭터의 이름이 먼저다
// - 숨긴 업적도 받은 사람들에게는 이름과 그림이 보인다. 서버가 싣는 칸(name, description, image_id, users)만 읽는다
// 알림은 이벤트로만 정한다. 계정의 업적 기록(시나리오 소개의 업적)과 섞지 않는다.

import type { TableEvent } from '../../../../api/types';
import { eventRound } from './eventLines';

export type EarnedAchievement = {
  /** 이벤트의 번호. 닫은 알림을 기억하는 데 쓴다 */
  key: string;
  name: string;
  description: string;
  imageId: string | null;
  /** 받은 사람의 보일 이름들. 앉은 차례다 */
  receivers: string[];
};

type Payload = Record<string, unknown>;

function textOf(payload: Payload, key: string): string | null {
  const value = payload[key];
  return typeof value === 'string' && value !== '' ? value : null;
}

/** 받은 사람 한 명의 보일 이름. 캐릭터의 이름이 없으면 사람의 이름 */
function receiverName(user: unknown, nameOfMember: (userId: string) => string): string | null {
  if (user === null || typeof user !== 'object') return null;
  const one = user as Payload;
  const userId = textOf(one, 'user_id');
  return textOf(one, 'character_name') ?? (userId ? nameOfMember(userId) : null);
}

/** 알림을 띄울 라운드인가. 지금 라운드이거나 바로 앞 라운드(방금 닫혔다) */
export function isRecentRound(round: number | null, currentRound: number | null): boolean {
  if (round === null || currentRound === null) return false;
  return round === currentRound || round === currentRound - 1;
}

/** 이벤트 하나를 알림으로. 이름이 없으면 띄우지 않는다 */
export function toEarnedAchievement(event: TableEvent, nameOfMember: (userId: string) => string): EarnedAchievement | null {
  const payload: Payload = event.payload ?? {};
  const name = textOf(payload, 'name');
  if (name === null) return null;
  const users = Array.isArray(payload.users) ? payload.users : [];
  return {
    key: String(event.sequence),
    name,
    description: textOf(payload, 'description') ?? '',
    imageId: textOf(payload, 'image_id'),
    receivers: users.map((user) => receiverName(user, nameOfMember)).filter((one): one is string => one !== null),
  };
}

/** 방 위에 띄울 업적들. 받은 차례다. events 는 번호 차례이고 되돌린 라운드의 일은 이미 뺐다 */
export function recentAchievements(events: TableEvent[], currentRound: number | null, nameOfMember: (userId: string) => string): EarnedAchievement[] {
  return events
    .filter((event) => event.type === 'achievement_earned' && isRecentRound(eventRound(event), currentRound))
    .map((event) => toEarnedAchievement(event, nameOfMember))
    .filter((one): one is EarnedAchievement => one !== null);
}

/** 받은 사람의 한 줄. "받은 사람: 렌, 미아". 이름 뒤의 조사를 고르지 않아도 되게 */
export function receiversLine(receivers: string[]): string {
  return receivers.length === 0 ? '이 테이블에서 받았습니다' : `받은 사람: ${receivers.join(', ')}`;
}
