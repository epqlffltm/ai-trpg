// web/apps/web/src/pages/operator/inquiries/inquiryBoxView.ts
// 운영자 문의함(메일함 모양)의 순수한 함수. 상자, 줄의 보낸 사람, 고르기, 지운 일의 한 줄, 실패의 글.

import type { AdminInquiry, InquiryAction, InquiryCounts, InquiryFolder } from '../../../api/inquiryAdmin';
import { ApiError } from '../../../api/errors';
import { formatDateTime } from '../../../format/dateTime';

export type Box = InquiryFolder | 'actions';

/** 상자들. 주소의 ?box= 다. actions 는 지운 일의 기록이다 */
export const BOXES: { value: Box; label: string }[] = [
  { value: 'all', label: '모두' },
  { value: 'open', label: '답 기다림' },
  { value: 'answered', label: '답함' },
  { value: 'actions', label: '지운 기록' },
];

export function boxOf(param: string | null): Box {
  return BOXES.find((box) => box.value === param)?.value ?? 'open';
}

/** 서버의 상태 고르기. 모두면 고르지 않는다 */
export function statusOf(box: InquiryFolder): 'open' | 'answered' | undefined {
  return box === 'all' ? undefined : box;
}

export function boxLabel(box: Box, counts: InquiryCounts | undefined): string {
  const label = BOXES.find((item) => item.value === box)?.label ?? box;
  if (!counts || box === 'actions') return label;
  return `${label} ${counts[box]}`;
}

/** 줄의 보낸 사람. 로그인했으면 닉네임, 아니면 주소 */
export function senderLabel(inquiry: Pick<AdminInquiry, 'sender' | 'email'>): string {
  return inquiry.sender?.nickname ?? inquiry.email;
}

/** 고른 것에 하나를 넣거나 뺀다 */
export function toggled(selected: ReadonlySet<string>, id: string): Set<string> {
  const next = new Set(selected);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

/** 보이는 줄을 모두 골랐는가 */
export function allSelected(selected: ReadonlySet<string>, ids: readonly string[]): boolean {
  return ids.length > 0 && ids.every((id) => selected.has(id));
}

/** 보이는 줄에 없는 것은 고른 것에서 뺀다(지워졌거나 다른 상자로 갔다) */
export function keepVisible(selected: ReadonlySet<string>, ids: readonly string[]): Set<string> {
  return new Set(ids.filter((id) => selected.has(id)));
}

const ACTION_KIND: Record<InquiryAction['kind'], string> = {
  delete_one: '하나 지움',
  delete_selected: '고른 것 지움',
  empty_folder: '상자 비움',
  retention: '보관 기간이 지나 지움',
};

/** 지운 일의 한 줄: 누가, 어떻게, 몇 개 */
export function actionLine(action: InquiryAction): string {
  const who = action.operator?.nickname ?? (action.kind === 'retention' ? '정리 명령' : '(비운 계정)');
  const folder = action.kind === 'empty_folder' ? `(${BOXES.find((box) => box.value === action.folder)?.label ?? action.folder})` : '';
  return `${who} · ${ACTION_KIND[action.kind]}${folder} · ${action.deleted_count}개`;
}

/** 답 메일이 어떻게 됐는가 */
export function replyMailLine(inquiry: Pick<AdminInquiry, 'reply_sent_at' | 'reply_discarded_at'>): string {
  if (inquiry.reply_sent_at) return `답 메일을 보냈습니다(${formatDateTime(inquiry.reply_sent_at)}).`;
  if (inquiry.reply_discarded_at) return `답 메일을 보내지 못했습니다(${formatDateTime(inquiry.reply_discarded_at)}). 다른 길로 알려 주세요.`;
  return '답 메일을 보내는 중입니다.';
}

/** 문의함의 쓰기가 실패한 까닭 */
export function boxProblemText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'inquiry.already_answered') return '이미 답한 문의입니다. 다시 읽어 확인하세요.';
    if (error.status === 404) return '이미 지워진 문의입니다.';
    if (error.status === 400) return '내용을 다시 확인해 주세요.';
  }
  return '처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.';
}
