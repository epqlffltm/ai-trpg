// web/apps/web/src/pages/chat/conversation/drawShot.ts
// 스크린샷(#982)을 canvas 에 그려 PNG 로 내려받는다. 서버에 올리지 않는다.
// 색은 지금 화면의 테마(--ui-bg, --ui-text, --ui-text-muted, --ui-accent)를 그대로 쓴다. 대표 그림이 있으면 제목 옆에 작게 둔다.

import { layoutShot, SHOT_PADDING, type ShotItem, type ShotLayout, type ShotRow } from './screenshotView';

type Theme = { background: string; text: string; muted: string; accent: string };

const FONT_FAMILY = 'system-ui, -apple-system, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif';
const FONTS: Record<ShotRow['kind'], string> = {
  title: `bold 26px ${FONT_FAMILY}`,
  subtitle: `15px ${FONT_FAMILY}`,
  speaker: `bold 17px ${FONT_FAMILY}`,
  text: `17px ${FONT_FAMILY}`,
  footer: `13px ${FONT_FAMILY}`,
};
const AVATAR = 48;

function themeOf(): Theme {
  const style = getComputedStyle(document.documentElement);
  const read = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
  return { background: read('--ui-bg', '#f5f6fb'), text: read('--ui-text', '#0f172a'), muted: read('--ui-text-muted', '#475569'), accent: read('--ui-accent', '#4f46e5') };
}

function colorOf(kind: ShotRow['kind'], theme: Theme): string {
  if (kind === 'speaker') return theme.accent;
  if (kind === 'subtitle' || kind === 'footer') return theme.muted;
  return theme.text;
}

function paint(context: CanvasRenderingContext2D, layout: ShotLayout, theme: Theme, picture: ImageBitmap | null): void {
  context.fillStyle = theme.background;
  context.fillRect(0, 0, layout.width, layout.height);
  const shift = picture ? AVATAR + 12 : 0;
  if (picture) context.drawImage(picture, SHOT_PADDING, SHOT_PADDING, AVATAR, AVATAR);
  for (const row of layout.rows) {
    context.font = FONTS[row.kind];
    context.fillStyle = colorOf(row.kind, theme);
    if (row.kind === 'footer') {
      context.textAlign = 'right';
      context.fillText(row.text, layout.width - SHOT_PADDING, row.y);
      context.textAlign = 'left';
    } else {
      const header = row.kind === 'title' || row.kind === 'subtitle';
      context.fillText(row.text, SHOT_PADDING + (header ? shift : 0), row.y);
    }
  }
}

/** 고른 말들을 그린 PNG. 그리지 못하면(canvas 가 없다) null */
export async function drawShot(title: string, subtitle: string, items: ShotItem[], picture: Blob | null): Promise<Blob | null> {
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');
  if (!context) return null;
  const measure = (text: string, kind: ShotRow['kind']) => {
    context.font = FONTS[kind];
    return context.measureText(text).width;
  };
  const layout = layoutShot(title, subtitle, items, measure);
  canvas.width = layout.width;
  canvas.height = layout.height;
  const bitmap = picture ? await createImageBitmap(picture).catch(() => null) : null;
  paint(context, layout, themeOf(), bitmap);
  return new Promise((resolve) => canvas.toBlob((blob) => resolve(blob), 'image/png'));
}

/** 파일로 내려받는다 */
export function downloadBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
