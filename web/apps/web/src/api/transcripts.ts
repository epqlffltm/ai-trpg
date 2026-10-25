// web/apps/web/src/api/transcripts.ts
// 한 판의 기록을 파일로 받는다(게임 서버, #403, #617). 앉은 사람은 받기 시작한 때까지의 서술, 선언, 판정, 상태의 변화, 채팅, 내 쪽지.
// 떠난 사람은 떠난 때까지(채팅과 쪽지도 떠난 시각까지).
// 형식은 md(기본), html, txt. 파일 이름은 Content-Disposition 의 테이블 제목이다.
// 실패: 404(앉아 있지 않거나 없는 테이블), 422(모르는 형식), 429(10분에 10번, Retry-After).

import { apiDownload, type Download } from './http';

export const TRANSCRIPT_FORMATS = ['md', 'html', 'txt'] as const;
export type TranscriptFormat = (typeof TRANSCRIPT_FORMATS)[number];

/** past 면 떠난 테이블의 기록(떠난 때까지, GET /tables/past/{id}/transcript) */
export function fetchTranscript(tableId: string, format: TranscriptFormat, past = false): Promise<Download> {
  const base = past ? '/api/v1/game/tables/past' : '/api/v1/game/tables';
  return apiDownload(`${base}/${encodeURIComponent(tableId)}/transcript`, { query: { format } });
}
