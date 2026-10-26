// web/apps/web/src/pages/operator/moderationPure.ts
// 신고 처리(E4)의 순수한 함수. 사유와 처리의 이름, 사유마다의 수를 한 줄로, 운영자가 쓰는 사유의 검사, 쪽(offset 과 쪽 번호).

import type { ReportOutcome, ReportReason } from '../../api/types';

/** 한 쪽의 수. 더 보기로 이어 읽는다 */
export const PAGE_SIZE = 20;

/** 운영자가 쓰는 사유(조치, 보기)의 길이. 서버의 상한과 같다(operator_actions.reason) */
export const REASON_MAX_LENGTH = 200;

/** 신고의 사유를 화면의 말로. 사유의 차례도 이것이다(미성년이 먼저) */
export const REASON_LABELS: Record<ReportReason, string> = {
  minor: '미성년 인물을 성적으로',
  sexual: '성적인 내용',
  illegal: '불법',
  abuse: '욕설·괴롭힘',
  spam: '스팸·광고',
  other: '기타',
};

const OUTCOME_LABELS: Record<ReportOutcome, string> = {
  actioned: '받아들임',
  dismissed: '기각',
};

export function reasonLabel(reason: ReportReason): string {
  return REASON_LABELS[reason];
}

/** 처리한 결과. 아직이면 "열림" */
export function outcomeLabel(outcome: ReportOutcome | null): string {
  return outcome === null ? '열림' : OUTCOME_LABELS[outcome];
}

/** 사유마다의 수를 한 줄로. 0 은 뺀다. 미성년이 먼저, 그다음 REASON_LABELS 의 차례다 */
export function reasonSummary(reasons: Record<string, number>): string {
  return (Object.keys(REASON_LABELS) as ReportReason[])
    .filter((reason) => (reasons[reason] ?? 0) > 0)
    .map((reason) => `${REASON_LABELS[reason]} ${reasons[reason]}`)
    .join(' · ');
}

/** 운영자가 쓴 사유가 맞지 않으면 그 까닭, 맞으면 null. 앞뒤 빈칸은 세지 않는다 */
export function reasonProblem(reason: string): string | null {
  const length = reason.trim().length;
  if (length === 0) return '사유를 적어 주세요. 감사 기록에 남습니다.';
  if (length > REASON_MAX_LENGTH) return `사유는 ${REASON_MAX_LENGTH}자까지입니다.`;
  return null;
}

/** 다음 쪽의 offset. 다 읽었으면 undefined(더 보기를 숨긴다) */
export function nextOffset(total: number, pagesRead: number): number | undefined {
  const read = pagesRead * PAGE_SIZE;
  return read < total ? read : undefined;
}

/** 쪽 번호로 읽는 목록(게시판)의 다음 쪽. 다 읽었으면 undefined */
export function nextPage(total: number, pagesRead: number, size: number): number | undefined {
  return pagesRead * size < total ? pagesRead + 1 : undefined;
}

/** 굳힌 대화의 말을 누가 했는가. 사람과 캐릭터, 그 밖은 그대로 */
export function speakerLabel(role: string, characterName: string): string {
  if (role === 'user') return '사람';
  if (role === 'assistant') return characterName;
  return role;
}
