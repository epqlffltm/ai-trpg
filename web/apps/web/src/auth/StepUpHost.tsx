// web/apps/web/src/auth/StepUpHost.tsx
// 본인 확인 창(F5)을 띄우는 자리. 화면의 틀(AppLayout)에 하나만 둔다.
// 민감한 작업이 본인 확인을 요구하면 stepUpGate.ts 가 이 자리에 창을 부탁하고, 확인했는지(true)·닫았는지(false)를 기다린다.
// 확인하면 이 세션의 창을 읽어 둔 것(마이페이지의 본인 확인 칸)을 다시 읽는다.

import { Dialog } from '@ai-trpg/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { setStepUpAsker } from '../api/stepUpGate';
import { stepUpQuery } from './queries';
import { StepUpForm } from './StepUpForm';

export function StepUpHost() {
  const [open, setOpen] = useState(false);
  const resolver = useRef<((verified: boolean) => void) | null>(null);
  const queryClient = useQueryClient();

  useEffect(
    () =>
      setStepUpAsker(
        () =>
          new Promise<boolean>((resolve) => {
            resolver.current = resolve;
            setOpen(true);
          }),
      ),
    [],
  );

  // 틀이 사라지면(로그아웃 화면으로 바뀜) 기다리던 작업을 놓아 준다
  useEffect(() => () => resolver.current?.(false), []);

  const finish = useCallback(
    (verified: boolean) => {
      setOpen(false);
      resolver.current?.(verified);
      resolver.current = null;
      if (verified) void queryClient.invalidateQueries({ queryKey: stepUpQuery().queryKey });
    },
    [queryClient],
  );
  const cancel = useCallback(() => finish(false), [finish]);

  return (
    <Dialog title="본인 확인" open={open} onClose={cancel}>
      {open ? <StepUpForm onDone={() => finish(true)} onCancel={cancel} /> : null}
    </Dialog>
  );
}
