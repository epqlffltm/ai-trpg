// web/apps/web/src/pages/trpg/studio/studioKinds.ts
// 제작 도구(B9)의 재료마다 보일 글과 경로. 목록, 만들기 허브, 실패의 글이 함께 쓴다.
// 이름 뒤의 조사를 고르지 않아도 되게 글을 통째로 적는다(받침에 따라 "을/를"이 갈린다).

import type { StudioKind } from '../../../api/studio';

export type StudioKindText = {
  /** 보일 이름. "룰북" */
  label: string;
  /** 목록의 제목. "내 룰북" */
  title: string;
  /** 목록 위의 설명 */
  intro: string;
  /** 새로 만들기의 글. "새 룰북 만들기" */
  create: string;
  /** 빈 목록의 글과 첫 만들기 */
  empty: string;
  first: string;
  /** 찾지 못했을 때(404) */
  missing: string;
};

export const STUDIO_KINDS: StudioKind[] = ['rulebooks', 'worlds'];

const TEXTS: Record<StudioKind, StudioKindText> = {
  rulebooks: {
    label: '룰북',
    title: '내 룰북',
    intro: '룰북은 시나리오가 쓰는 규칙입니다. 규칙은 템플릿에서 오고, 방어 규칙만 고를 수 있습니다.',
    create: '새 룰북 만들기',
    empty: '아직 만든 룰북이 없습니다.',
    first: '첫 룰북 만들기',
    missing: '룰북을 찾을 수 없습니다. 지워졌을 수 있습니다.',
  },
  worlds: {
    label: '세계관',
    title: '내 세계관',
    intro: '세계관은 시나리오의 배경입니다. 설정은 서술하는 AI 가 읽고, GM 메모는 앉은 사람에게 가지 않습니다.',
    create: '새 세계관 만들기',
    empty: '아직 만든 세계관이 없습니다.',
    first: '첫 세계관 만들기',
    missing: '세계관을 찾을 수 없습니다. 지워졌을 수 있습니다.',
  },
};

export function kindText(kind: StudioKind): StudioKindText {
  return TEXTS[kind];
}

/** 그 종류의 목록, 새로 만들기, 하나의 경로 */
export function studioPath(kind: StudioKind, assetId?: string): string {
  return assetId ? `/trpg/studio/${kind}/${assetId}` : `/trpg/studio/${kind}`;
}

export function studioNewPath(kind: StudioKind): string {
  return `/trpg/studio/${kind}/new`;
}
