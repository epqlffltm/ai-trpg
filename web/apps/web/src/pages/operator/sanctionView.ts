// web/apps/web/src/pages/operator/sanctionView.ts
// 게임 서버의 제재 결과를 한 줄로. 순수한 함수다.

import type { PublishingBan, SanctionResult } from '../../api/gameOperator';

export function sanctionNotice(result: SanctionResult): string {
  const ban = result.publishing_banned ? ' 제작자는 지금 공개 금지 중입니다.' : '';
  return `${result.version_number}판을 제재했습니다. 공개가 내려갔고 이 판은 다시 공개하지 못합니다.${ban}`;
}

export function banNotice(ban: PublishingBan, who: string): string {
  return ban.banned ? `${who}의 공개를 금지했습니다.` : `${who}의 공개 금지를 풀었습니다.`;
}
