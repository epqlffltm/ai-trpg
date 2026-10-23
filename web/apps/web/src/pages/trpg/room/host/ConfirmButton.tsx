// web/apps/web/src/pages/trpg/room/host/ConfirmButton.tsx
// 한 번 더 묻는 단추. 누르면 창을 열어 무엇이 일어나는지 알리고, 창의 단추로 한다. 되돌리기 어려운 동작(내보내기, 끝내기)에 쓴다.

import { Button, Dialog, type ButtonVariant } from '@ai-trpg/ui';
import { useCallback, useState, type ReactNode } from 'react';
import type { FormProblem } from '../../../../auth/problem';
import { ProblemNotice } from '../../../../components/ProblemNotice';

type Props = {
  label: string;
  /** 단추에 읽히는 이름(누구를 내보내는지). 없으면 label */
  ariaLabel?: string;
  title: string;
  confirm: string;
  children: ReactNode;
  busy: boolean;
  problem: FormProblem | undefined;
  /** 하고 나서 창을 닫을지. 실패하면 false 를 돌려 열어 둔다 */
  onConfirm: () => Promise<boolean>;
  variant?: ButtonVariant;
};

export function ConfirmButton({ label, ariaLabel, title, confirm, children, busy, problem, onConfirm, variant = 'quiet' }: Props) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);

  async function act() {
    if (await onConfirm()) setOpen(false);
  }

  return (
    <>
      <Button variant={variant} aria-label={ariaLabel ?? label} onClick={() => setOpen(true)}>
        {label}
      </Button>
      <Dialog title={title} open={open} onClose={close}>
        {children}
        <ProblemNotice problem={problem} />
        <div className="actions">
          <Button busy={busy} onClick={act}>
            {confirm}
          </Button>
        </div>
      </Dialog>
    </>
  );
}
