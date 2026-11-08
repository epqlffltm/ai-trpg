// web/apps/web/src/hooks/useHashScroll.ts
// 주소의 #(칸의 id)까지 화면을 내린다. 프로필 메뉴의 길(차단 관리, 팔로잉 제작자, 내 초대 코드, 활동 배지, 성향 필터)이
// 마이페이지와 설정의 칸을 가리킬 때 쓴다. 라우터는 #로 내려 주지 않으므로 화면이 그린 뒤에 찾는다.
// 로그인을 확인한 뒤에 그리는 칸도 있어, 없으면 잠깐씩(HASH_RETRY_MS) 몇 번(HASH_TRIES) 더 찾는다. 끝내 없으면 그대로 둔다.

import { useEffect } from 'react';
import { useLocation } from 'react-router';

export const HASH_TRIES = 10;
export const HASH_RETRY_MS = 100;

export function useHashScroll(): void {
  const { hash, search } = useLocation();
  useEffect(() => {
    if (!hash) return undefined;
    const id = decodeURIComponent(hash.slice(1));
    let tries = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const find = () => {
      const target = document.getElementById(id);
      if (target) {
        target.scrollIntoView?.({ block: 'start' });
        return;
      }
      tries += 1;
      if (tries < HASH_TRIES) timer = setTimeout(find, HASH_RETRY_MS);
    };
    find();
    return () => clearTimeout(timer);
  }, [hash, search]);
}
