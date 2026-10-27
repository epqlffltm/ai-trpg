// web/apps/web/src/pages/story/storyEdit.ts
// 말 고치기의 검사. 순수한 함수다. 규칙은 story 서버와 같다(MessageCreate 4000자, MessageEdit 의 조각은 한 줄이고 빈칸만은 안 됨).

import type { StorySegment } from '../../api/story';
import { MESSAGE_MAX } from '../chat/conversation/Composer';

/** 내 말을 고쳐 보낼 수 있는가. 빈칸만이 아니고, 바뀌었고, 4000자 이하 */
export function canSendEdit(original: string, text: string): boolean {
  return /\S/.test(text) && text !== original && text.length <= MESSAGE_MAX;
}

/** 답의 조각들을 고쳐 저장할 수 있는가. 조각마다 한 줄이고 빈칸만이 아니며, 하나라도 바뀌었다 */
export function canSaveSegments(segments: StorySegment[], texts: string[]): boolean {
  if (texts.length !== segments.length) return false;
  const valid = texts.every((text) => /\S/.test(text) && !/[\r\n]/.test(text) && text.length <= MESSAGE_MAX);
  return valid && texts.some((text, index) => text !== segments[index]?.text);
}
