// web/apps/web/src/pages/chat/character/characterView.ts
// 캐릭터 소개(C2)에 보이는 글을 짓는다. 순수한 함수다.

import type { ConversationSummary, PublicCharacterDetail } from '../../../api/types';
import { formatDateTime } from '../../../format/dateTime';

type CharacterDocument = PublicCharacterDetail['document'];

/** 호감도의 단계 이름들(낮은 것부터). 제작자가 단계로 보이기를 골랐을 때만이고, 숫자로 보이면 숨긴다 */
export function stageNames(affection: CharacterDocument['affection']): string[] {
  if (!affection || affection.display !== 'stage') return [];
  return [...affection.stages].sort((a, b) => a.at - b.at).map((stage) => stage.name);
}

/** 시작 상황의 시각. 판에 없으면 서버가 정오로 시작한다 */
export function startTimeLabel(hour: number | undefined): string {
  return `1일째 ${hour ?? 12}시에 시작`;
}

/** 머리의 한 줄: 나이, 성별 */
export function profileLine(document: Pick<CharacterDocument, 'age' | 'gender'>): string {
  return [document.age, document.gender].map((value) => value.trim()).filter(Boolean).join(' · ');
}

/** 대화 목록의 한 줄: 마지막으로 말한 때와 모델 */
export function conversationLine(conversation: Pick<ConversationSummary, 'updated_at' | 'model'>): string {
  const model = conversation.model;
  const modelText = !model ? '모델을 아직 고르지 않음' : model.usable ? model.display_name : `${model.display_name}(지금은 쓸 수 없음)`;
  return `${formatDateTime(conversation.updated_at)} · ${modelText}`;
}

/** 대화가 가져온 판보다 새 판이 공개되었는가. 대화는 시작할 때의 판을 그대로 쓴다 */
export function hasNewerVersion(conversation: Pick<ConversationSummary, 'character'>, latestVersion: number): boolean {
  return conversation.character.version < latestVersion;
}
