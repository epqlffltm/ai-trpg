// web/apps/web/src/pages/trpg/room/transcript/transcriptView.ts
// 기록 내려받기의 글과 파일 이름. 순수한 함수다.

import type { TranscriptFormat } from '../../../../api/transcripts';

const LABELS: Record<TranscriptFormat, string> = {
  md: '마크다운(.md)',
  html: '웹 문서(.html)',
  txt: '글(.txt)',
};

const HINTS: Record<TranscriptFormat, string> = {
  md: '다른 도구에 붙여 넣기 좋습니다',
  html: '브라우저로 열어 읽습니다',
  txt: '어떤 편집기로도 읽습니다',
};

export function formatLabel(format: TranscriptFormat): string {
  return LABELS[format];
}

export function formatHint(format: TranscriptFormat): string {
  return HINTS[format];
}

/** 서버가 이름을 주지 않았을 때의 파일 이름. 테이블 제목에 확장자. 경로의 구분은 남기지 않는다 */
export function fallbackFilename(title: string, format: TranscriptFormat): string {
  const base = title.replace(/[/\\:*?"<>|]/g, '_').trim() || '기록';
  return `${base}.${format}`;
}
