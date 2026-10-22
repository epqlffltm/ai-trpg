// web/apps/web/src/layout/AccountMenu.tsx
// 로그인한 사람의 닉네임과 로그아웃. 로그아웃하면 읽어 둔 것(내 테이블, 내 대화)을 모두 버린다.

import { Button } from '@ai-trpg/ui';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { fetchMe, logout } from '../api/auth';

export function AccountMenu() {
  const me = useQuery({ queryKey: ['auth', 'me'], queryFn: ({ signal }) => fetchMe(signal) });
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);

  // 서버가 거절해도(출처가 맞지 않음 등) 이 화면의 상태는 logout 이 이미 비웠다. 화면은 로그아웃한 것으로 돌아간다
  async function signOut() {
    setBusy(true);
    await logout().catch(() => undefined);
    queryClient.clear();
    setBusy(false);
    navigate('/', { replace: true });
  }

  return (
    <>
      <span className="app-header__nickname">{me.data?.nickname ?? ''}</span>
      <Button variant="quiet" busy={busy} onClick={signOut}>
        로그아웃
      </Button>
    </>
  );
}
