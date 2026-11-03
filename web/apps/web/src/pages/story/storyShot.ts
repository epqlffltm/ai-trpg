// web/apps/web/src/pages/story/storyShot.ts
// 장면의 스크린샷(#982)에 넣을 말들. 답은 말 조각마다 한 줄(서술은 말한 이가 없다), 사람의 말은 "나", 행동 말은 글 그대로다.
// 순수한 함수다. 그리는 것은 chat 의 스크린샷 창이 한다(ScreenshotDialog).

import type { StoryMessage, StoryView } from '../../api/story';
import { itemLabel, type ShotItem, type ShotLine } from '../chat/conversation/screenshotView';
import { speakerName } from './storyWorld';

function linesOf(message: StoryMessage, view: StoryView): ShotLine[] {
  if (message.role === 'assistant') return message.segments.map((segment) => ({ speaker: speakerName(view, segment.speaker), text: segment.text }));
  return [{ speaker: message.role === 'user' ? '나' : null, text: message.content }];
}

export function storyShotItems(messages: StoryMessage[], view: StoryView): ShotItem[] {
  return messages.map((message) => {
    const lines = linesOf(message, view);
    return { id: message.id, label: itemLabel(lines), lines };
  });
}
