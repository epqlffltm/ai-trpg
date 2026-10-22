// web/apps/web/src/pages/me/LogoutAllSection.tsx
// 모든 기기에서 로그아웃(POST /logout-all). 이 기기도 끊긴다. 한 번 더 묻고 보낸다.
// 마치면 읽어 둔 것을 모두 버리고 로그인으로 보낸다. 다른 서버도 끊긴 세션의 목록(30초쯤)으로 곧 거절한다.

import { Button, Dialog } from '@ai-trpg/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router';
import { logoutAll } from '../../api/account';
import { describeAccountProblem } from '../../auth/accountProblem';
import type { FormProblem } from '../../auth/problem';
import { ProblemNotice } from '../../components/ProblemNotice';

const DONE = '모든 기기에서 로그아웃했습니다. 다시 로그인해 주세요.';

export function LogoutAllSection() {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const close = useCallback(() => setAsking(false), []);

  async function confirm() {
    setBusy(true);
    setProblem(undefined);
    try {
      await logoutAll();
      queryClient.clear();
      navigate('/login', { replace: true, state: { notice: DONE } });
    } catch (error) {
      setProblem(describeAccountProblem(error));
      setBusy(false);
    }
  }

  return (
    <section className="page-section" aria-labelledby="sessions-heading">
      <h2 id="sessions-heading">로그인한 기기</h2>
      <p>다른 기기에서 로그인한 것이 의심되면 모든 기기에서 로그아웃하고 비밀번호를 바꾸세요.</p>
      <Button variant="secondary" onClick={() => setAsking(true)}>
        모든 기기에서 로그아웃
      </Button>
      <Dialog title="모든 기기에서 로그아웃" open={asking} onClose={close}>
        <p>이 기기를 포함해 로그인한 모든 기기에서 로그아웃합니다. 다시 쓰려면 기기마다 새로 로그인해야 합니다.</p>
        <ProblemNotice problem={problem} />
        <div className="actions">
          <Button busy={busy} onClick={confirm}>
            로그아웃하기
          </Button>
        </div>
      </Dialog>
    </section>
  );
}
