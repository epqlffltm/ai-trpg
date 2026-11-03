// web/apps/web/src/pages/chat/conversation/screenshotView.ts
// 대화의 스크린샷(#982)을 그리기 전의 순수한 함수. 고른 말들을 줄로 바꾸고, 폭에 맞춰 줄을 나누고, 그릴 자리를 정한다.
// 그리는 것(canvas)은 drawShot.ts 가 한다. 서버에 올리지 않는다. chat 과 story 가 함께 쓴다.

import type { ConversationDetail } from '../../../api/types';
import { speakerName } from './conversationView';

/** 스크린샷에 들어갈 말 한 줄. speaker 가 없으면 서술이나 행동이다 */
export type ShotLine = { speaker: string | null; text: string };
/** 고를 수 있는 말 하나. lines 는 그 말이 그림에 들어갈 모양이다(story 의 답은 조각마다 한 줄) */
export type ShotItem = { id: string; label: string; lines: ShotLine[] };
export type ShotRow = { kind: 'title' | 'subtitle' | 'speaker' | 'text' | 'footer'; text: string; y: number };
export type ShotLayout = { width: number; height: number; rows: ShotRow[] };
export type Measure = (text: string, kind: ShotRow['kind']) => number;

/** 그림의 폭(px)과 여백, 줄의 높이. 휴대폰에서 보기 좋은 폭이다 */
export const SHOT_WIDTH = 720;
export const SHOT_PADDING = 32;
export const LINE_HEIGHT: Record<ShotRow['kind'], number> = { title: 40, subtitle: 26, speaker: 28, text: 28, footer: 24 };
/** 그림의 아래에 작게 넣는 사이트 이름 */
export const SITE_NAME = 'AI TRPG';
/** 한 번에 고를 수 있는 말의 수. 그림이 너무 길어지지 않게 한다 */
export const SHOT_MAX_ITEMS = 30;

/** 고른 말들을 이어진 구간으로. 처음 고른 말부터 마지막 고른 말까지 사이의 말을 모두 넣는다(대화의 차례) */
export function contiguousRange(items: ShotItem[], picked: ReadonlySet<string>): ShotItem[] {
  const indexes = items.flatMap((item, index) => (picked.has(item.id) ? [index] : []));
  if (indexes.length === 0) return [];
  return items.slice(Math.min(...indexes), Math.max(...indexes) + 1);
}

/** 글을 폭에 맞춰 줄로 나눈다. 띄어쓰기에서 나누고, 한 낱말이 폭을 넘으면 글자에서 나눈다. 줄바꿈은 지킨다 */
export function wrapText(text: string, width: number, measure: (text: string) => number): string[] {
  const out: string[] = [];
  for (const paragraph of text.split('\n')) {
    let line = '';
    for (const word of paragraph.split(' ')) {
      const candidate = line ? `${line} ${word}` : word;
      if (measure(candidate) <= width) {
        line = candidate;
        continue;
      }
      if (line) out.push(line);
      line = '';
      for (const char of word) {
        if (measure(line + char) > width && line) {
          out.push(line);
          line = '';
        }
        line += char;
      }
    }
    out.push(line);
  }
  return out;
}

/** 그릴 자리. 위에 제목과 부제(장르, 성인 표시), 말마다 말한 이와 글, 아래에 사이트 이름 */
export function layoutShot(title: string, subtitle: string, items: ShotItem[], measure: Measure): ShotLayout {
  const inner = SHOT_WIDTH - SHOT_PADDING * 2;
  const rows: ShotRow[] = [];
  let y = SHOT_PADDING;
  const push = (kind: ShotRow['kind'], text: string) => {
    y += LINE_HEIGHT[kind];
    rows.push({ kind, text, y });
  };
  push('title', title);
  if (subtitle) push('subtitle', subtitle);
  y += 12;
  for (const line of items.flatMap((item) => item.lines)) {
    if (line.speaker) push('speaker', line.speaker);
    for (const text of wrapText(line.text, inner, (value) => measure(value, 'text'))) push('text', text);
    y += 10;
  }
  push('footer', SITE_NAME);
  return { width: SHOT_WIDTH, height: y + SHOT_PADDING, rows };
}

/** 부제. 장르 이름과 성인 등급의 표시 */
export function shotSubtitle(genre: string | null, adult: boolean): string {
  return [genre, adult ? '성인' : null].filter(Boolean).join(' · ');
}

/** 내려받을 파일의 이름. 파일 이름에 쓸 수 없는 글자는 뺀다 */
export function shotFileName(title: string): string {
  const safe = title.replace(/[\\/:*?"<>|]/g, '').trim();
  return `${safe || '대화'}.png`;
}

/** 고르는 목록에 보일 한 줄. "루나: 비가 오네요…" */
export function itemLabel(lines: ShotLine[]): string {
  const first = lines[0];
  if (!first) return '';
  const text = first.text.length > 40 ? `${first.text.slice(0, 39)}…` : first.text;
  return first.speaker ? `${first.speaker}: ${text}` : text;
}

/** chat 의 지금 가지의 말들. 말 하나가 한 줄이다(행동 말은 말한 이가 없다) */
export function chatShotItems(detail: Pick<ConversationDetail, 'messages' | 'persona' | 'character'>): ShotItem[] {
  return detail.messages.map((message) => {
    const lines = [{ speaker: speakerName(message.role, detail), text: message.content }];
    return { id: message.id, label: itemLabel(lines), lines };
  });
}
