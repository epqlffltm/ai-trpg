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
  /** 지우기 창의 알림. 없으면 재료의 알림(쓰는 시나리오가 있으면 지우지 못한다) */
  deleteNote?: string;
};

export const STUDIO_KINDS: StudioKind[] = ['rulebooks', 'worlds', 'lorebooks', 'bestiaries', 'scenarios'];

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
  lorebooks: {
    label: '로어북',
    title: '내 로어북',
    intro: '로어북은 인물, 장소, 물건 같은 설정의 모음입니다. 서술하는 AI 가 키워드로 찾아 읽습니다. 장소는 맵, 물건은 소지품이 됩니다.',
    create: '새 로어북 만들기',
    empty: '아직 만든 로어북이 없습니다.',
    first: '첫 로어북 만들기',
    missing: '로어북을 찾을 수 없습니다. 지워졌을 수 있습니다.',
  },
  bestiaries: {
    label: '몬스터 모음',
    title: '내 몬스터 모음',
    intro: '몬스터 모음은 몬스터의 이름과 설명입니다. HP 와 공격 같은 숫자는 시나리오에서 정합니다.',
    create: '새 몬스터 모음 만들기',
    empty: '아직 만든 몬스터 모음이 없습니다.',
    first: '첫 몬스터 모음 만들기',
    missing: '몬스터 모음을 찾을 수 없습니다. 지워졌을 수 있습니다.',
  },
  scenarios: {
    label: '시나리오',
    title: '내 시나리오',
    intro: '시나리오는 재료를 모아 규칙을 적은 것입니다. 게시하면 그때의 내용이 판으로 굳고, 판을 공개하면 테이블을 열 수 있습니다.',
    create: '새 시나리오 만들기',
    empty: '아직 만든 시나리오가 없습니다.',
    first: '첫 시나리오 만들기',
    missing: '시나리오를 찾을 수 없습니다. 지워졌을 수 있습니다.',
    deleteNote: '지우면 되돌릴 수 없습니다. 공개했다면 소개 페이지도 더는 열리지 않습니다.',
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
