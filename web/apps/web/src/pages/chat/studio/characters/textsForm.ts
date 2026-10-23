// web/apps/web/src/pages/chat/studio/characters/textsForm.ts
// 캐릭터의 글 탭 둘의 입력. 순수한 함수다.
//   - 소개(intro_html): 남에게 보이는 소개. 제작자가 꾸민 HTML 이고 게시할 때 서버가 거른다(UTF-8 로 50KB 까지)
//   - 말(greeting, speech_examples): 대화의 첫 인사와 말투의 예시. 모델이 읽는다(2,000자씩)

import type { AssetCharacterDetail, AssetCharacterUpdate } from '../../../../api/types';

export const INTRO_MAX_BYTES = 50 * 1024;
export const GREETING_MAX = 2000;
export const SPEECH_MAX = 2000;

/** 글의 UTF-8 바이트 수. 서버가 소개의 크기를 이것으로 잰다 */
export function utf8Bytes(text: string): number {
  return new TextEncoder().encode(text).length;
}

export function introHint(intro: string): string | undefined {
  return utf8Bytes(intro) > INTRO_MAX_BYTES ? `소개는 ${INTRO_MAX_BYTES / 1024}KB 까지입니다.` : undefined;
}

export function toIntroBody(intro: string): AssetCharacterUpdate {
  return { intro_html: intro };
}

export type SpeechDraft = { greeting: string; speechExamples: string };

export function speechDraft(character: AssetCharacterDetail): SpeechDraft {
  return { greeting: character.greeting, speechExamples: character.speech_examples };
}

/** 보내기 전에 알릴 것. 칸 이름(서버의 칸 이름) → 글 */
export function speechHints(draft: SpeechDraft): Record<string, string> {
  const hints: Record<string, string> = {};
  if (draft.greeting.length > GREETING_MAX) hints.greeting = `인사말은 ${GREETING_MAX}자까지입니다.`;
  if (draft.speechExamples.length > SPEECH_MAX) hints.speech_examples = `말투 예시는 ${SPEECH_MAX}자까지입니다.`;
  return hints;
}

/** 글은 다듬지 않는다(앞뒤의 줄바꿈도 제작자의 글이다) */
export function toSpeechBody(draft: SpeechDraft): AssetCharacterUpdate {
  return { greeting: draft.greeting, speech_examples: draft.speechExamples };
}
