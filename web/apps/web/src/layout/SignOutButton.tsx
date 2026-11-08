// web/apps/web/src/layout/SignOutButton.tsx
// 로그아웃 단추. 프로필 메뉴(AccountMenu), 다시 동의·탈퇴 유예의 틀(LimitedLayout)과 그 카드가 함께 쓴다.
// 로그아웃하면 읽어 둔 것(내 테이블, 내 대화)을 모두 버리고 첫 화면으로 간다.

import { Button } from '@ai-trpg/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { logout } from '../api/auth';

/** 서버가 거절해도(출처가 맞지 않음 등) 이 화면의 상태는 logout 이 이미 비웠다. 화면은 로그아웃한 것으로 돌아간다 */
export function SignOutButton() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);

  async function signOut() {
    setBusy(true);
    await logout().catch(() => undefined);
    queryClient.clear();
    setBusy(false);
    void navigate('/', { replace: true });
  }

  return (
    <Button variant="quiet" busy={busy} onClick={() => void signOut()}>
      로그아웃
    </Button>
  );
}
