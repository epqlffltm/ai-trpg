// web/apps/web/src/api/inquiries.ts
// 문의(고객센터, 인증 서버의 support 앱). 보내기와 내 문의. 운영자의 문의함은 api/inquiryAdmin.ts 다.
// 로그인하지 않아도 보낸다(로그인이 안 되는 문의가 있다). 그때는 답 받을 주소(email)를 싣는다.
//
// 실패(auth-server/README.md 의 "문의"):
//   - 400: 칸이 틀렸거나, 로그인하지 않았는데 email 이 없다(칸마다의 오류)
//   - 429: 한 IP 에 한 시간 다섯 번까지다
// 같은 문의를 두 번 보내면 두 개가 된다. 열쇠(Idempotency-Key)를 붙이지 않는 대신 보내는 동안 단추를 막는다.

import type { components as Auth } from './generated/auth';
import { apiRequest } from './http';

export type InquiryCategory = Auth['schemas']['InquiryCategoryEnum'];
export type InquiryDraft = Auth['schemas']['InquiryRequestRequest'];
export type InquiryCreated = Auth['schemas']['InquiryCreated'];
export type MyInquiry = Auth['schemas']['MyInquiry'];
export type MyInquiryPage = Auth['schemas']['MyInquiryPage'];

const AUTH = '/api/v1/auth';

/** 문의를 보낸다. 로그인했으면 계정의 주소로 답하므로 email 을 싣지 않아도 된다 */
export function sendInquiry(draft: InquiryDraft): Promise<InquiryCreated> {
  return apiRequest<InquiryCreated>(`${AUTH}/inquiries`, { method: 'POST', body: draft });
}

/** 내 문의와 답. 최근 것부터 한 쪽씩. 다음 쪽은 앞 쪽의 next_before 를 before 로 */
export function fetchMyInquiries(before: string | undefined, signal?: AbortSignal): Promise<MyInquiryPage> {
  return apiRequest<MyInquiryPage>(`${AUTH}/me/inquiries`, { query: { before }, ...(signal ? { signal } : {}) });
}
