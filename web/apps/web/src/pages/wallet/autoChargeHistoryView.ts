// web/apps/web/src/pages/wallet/autoChargeHistoryView.ts
// 최근 자동 결제(#980)의 한 줄이 보일 글. 순수한 함수다. 상태와 까닭은 서버가 정한 것만 본다.
// 까닭의 글은 잔액 기준과 날짜 기준(#1167)에 함께 맞게 쓴다. 한 줄에는 어느 방식으로 적은 일인지가 없다.

import type { AutoChargeHistoryItem } from '../../api/types';

const STATUS: Record<AutoChargeHistoryItem['status'], string> = {
  processing: '처리 중',
  paid: '결제됨',
  declined: '거절됨',
  skipped: '하지 않음',
};

/** 하지 않은 까닭. 서버가 새 까닭을 먼저 보내면 한 말이다(historyNote) */
const REASON: Record<NonNullable<AutoChargeHistoryItem['reason']>, string> = {
  disabled: '결제하기 전에 자동 충전을 껐거나 언제 살지를 바꿨습니다.',
  no_card: '등록한 카드가 없어 결제하지 않았습니다.',
  not_eligible: '지금은 결제할 수 없어 결제하지 않았습니다. 본인인증이나 보호자 동의를 확인하세요.',
  monthly_limit: '이번 달 자동 충전 상한에 닿아 결제하지 않았습니다.',
  withdrawn: '탈퇴해 결제하지 않았습니다.',
  stale: '처리가 늦어져 결제하지 않았습니다. 다음에 살 때(골드가 떨어질 때나 다음 달의 그날) 다시 삽니다.',
  terms_outdated: '자동 결제 동의가 필요해 결제하지 않았습니다. 지갑에서 동의하고 저장하면 다시 삽니다.',
};

export function historyStatusLabel(status: AutoChargeHistoryItem['status']): string {
  return STATUS[status];
}

/** 상태마다 한 줄의 설명. 덧붙일 것이 없으면 null */
export function historyNote(item: AutoChargeHistoryItem): string | null {
  const off = item.turned_off ? ' 이어서 실패해 자동 충전을 껐습니다.' : '';
  switch (item.status) {
    case 'processing':
      return '결제 대행사의 결과를 기다리거나 보낼 차례를 기다립니다.';
    case 'declined':
      return `카드사가 결제를 거절했습니다. 돈은 나가지 않았습니다.${off}`;
    case 'skipped':
      return `${(item.reason ? (REASON[item.reason] as string | undefined) : undefined) ?? '결제하지 않았습니다.'}${off}`;
    default:
      return null;
  }
}
