// web/apps/web/src/pages/support/inquiryView.ts
// 문의를 보이고 받기 전의 순수한 함수. 종류의 이름, 상태의 이름, 보내기 전에 미리 알려 줄 것, 실패의 글.
// 길이의 상한은 인증 서버(support/models.py)와 같다.

import type { InquiryCategory, InquiryDraft } from '../../api/inquiries';
import { ApiError } from '../../api/errors';
import { commonProblem, fieldProblem, type FormProblem } from '../../auth/problem';

export const TITLE_MAX = 100;
export const BODY_MAX = 5000;

/** 종류와 그 이름. 고르는 칸의 차례다 */
export const CATEGORIES: { value: InquiryCategory; label: string }[] = [
  { value: 'account', label: '계정·로그인' },
  { value: 'payment', label: '결제·환불' },
  { value: 'report', label: '신고' },
  { value: 'bug', label: '오류' },
  { value: 'other', label: '그 밖' },
];

export function categoryLabel(category: InquiryCategory): string {
  return CATEGORIES.find((item) => item.value === category)?.label ?? category;
}

export function statusLabel(status: 'open' | 'answered'): string {
  return status === 'answered' ? '답함' : '답을 기다림';
}

export type InquiryForm = { category: InquiryCategory | ''; title: string; body: string; email: string };

export const EMPTY_FORM: InquiryForm = { category: '', title: '', body: '', email: '' };

/** 보낼 수 있는가. 로그인하지 않았으면 답 받을 주소가 있어야 한다. 최종 판단은 서버가 한다 */
export function canSend(form: InquiryForm, signedIn: boolean): boolean {
  return Boolean(form.category && form.title.trim() && form.body.trim() && (signedIn || form.email.trim()));
}

/** 서버에 보낼 모양. 로그인했으면 주소를 싣지 않는다(계정의 주소로 답한다) */
export function toDraft(form: InquiryForm, signedIn: boolean): InquiryDraft {
  const draft: InquiryDraft = { category: form.category as InquiryCategory, title: form.title.trim(), body: form.body.trim() };
  return signedIn ? draft : { ...draft, email: form.email.trim() };
}

/** 보내기의 실패를 화면의 글로 */
export function describeSendProblem(error: unknown): FormProblem {
  const common = commonProblem(error);
  if (common) return common;
  const apiError = error as ApiError;
  if (apiError.status === 400) return fieldProblem(apiError, '입력을 다시 확인해 주세요.');
  return { message: '문의를 보내지 못했습니다. 잠시 뒤에 다시 시도하세요.' };
}
