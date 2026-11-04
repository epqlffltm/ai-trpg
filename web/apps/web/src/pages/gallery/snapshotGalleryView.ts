// web/apps/web/src/pages/gallery/snapshotGalleryView.ts
// 갤러리(C7)의 "내 장면 그림"에 보일 글과 주소. 순수한 함수다.

import type { KeptSnapshot, SnapshotService } from '../../api/snapshots';

/** 그 그림을 그린 대화(세션)의 주소 */
export function conversationPath(service: SnapshotService, conversationId: string): string {
  return service === 'chat' ? `/chat/conversations/${conversationId}` : `/story/sessions/${conversationId}`;
}

/** 칸의 이름. "루나 · 비 오는 오후". 작품과 대화의 이름이 같으면 하나만 */
export function snapshotCaption(snapshot: Pick<KeptSnapshot, 'work_name' | 'conversation_title'>): string {
  const work = snapshot.work_name.trim();
  const title = snapshot.conversation_title.trim();
  return [work, title !== work ? title : ''].filter(Boolean).join(' · ');
}

/** 대화로 가는 길의 글 */
export function conversationLinkLabel(service: SnapshotService): string {
  return service === 'chat' ? '그 대화로' : '그 세션으로';
}
