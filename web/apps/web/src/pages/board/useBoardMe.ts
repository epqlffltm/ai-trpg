// web/apps/web/src/pages/board/useBoardMe.ts
// 게시판 화면이 쓸 "나". 로그인하지 않았으면 부르지 않는다. 쓰기 단추를 보일지 정하는 데만 쓴다(서버가 다시 막는다).

import { useQuery } from '@tanstack/react-query';
import type { BoardMe } from '../../api/types';
import { useSession } from '../../auth/useSession';
import { boardMeQuery } from './boardQueries';

export type BoardViewer = {
  signedIn: boolean;
  /** 서버가 아는 나. 로그인하지 않았거나 아직 읽는 중이면 undefined */
  me: BoardMe | undefined;
};

export function useBoardMe(): BoardViewer {
  const signedIn = useSession() !== null;
  const me = useQuery(boardMeQuery(signedIn));
  return { signedIn, me: signedIn ? me.data : undefined };
}
