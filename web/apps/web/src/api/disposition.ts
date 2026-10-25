// web/apps/web/src/api/disposition.ts
// 응답의 Content-Disposition 에서 파일 이름을 꺼낸다. 순수한 함수다.
// filename*(RFC 5987, UTF-8 로 퍼센트 인코딩)을 먼저 보고, 없으면 filename 을 본다. 한글 제목은 filename* 로 온다.
// 경로의 구분(/, \)은 이름에 남기지 않는다.

const EXTENDED = /filename\*\s*=\s*([^']*)'[^']*'([^;]+)/i;
const PLAIN = /filename\s*=\s*"?([^";]+)"?/i;

function clean(name: string): string | null {
  const base = name.replace(/[/\\]/g, '_').trim();
  return base === '' ? null : base;
}

export function filenameFromDisposition(header: string | null): string | null {
  if (!header) return null;
  const extended = EXTENDED.exec(header);
  if (extended?.[2]) {
    try {
      return clean(decodeURIComponent(extended[2].trim()));
    } catch {
      return null;
    }
  }
  const plain = PLAIN.exec(header);
  return plain?.[1] ? clean(plain[1]) : null;
}
