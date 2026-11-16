// web/packages/ui/src/Dialog.test.tsx
// 창 하나: Esc 와 바깥 누르기로 닫히는지, 창 위에 창이 뜨면 Esc 가 맨 위의 창만 닫는지 본다.

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Dialog } from './Dialog';

describe('Dialog', () => {
  it('Esc 를 누르면 닫는다', async () => {
    const onClose = vi.fn();
    render(
      <Dialog title="청약철회" open onClose={onClose}>
        <p>내용</p>
      </Dialog>,
    );

    await userEvent.keyboard('{Escape}');

    expect(onClose).toHaveBeenCalledOnce();
  });

  it('창 위에 창이 뜨면 Esc 는 맨 위의 창만 닫는다', async () => {
    const closeBelow = vi.fn();
    const closeAbove = vi.fn();
    render(
      <>
        <Dialog title="청약철회" open onClose={closeBelow}>
          <p>아래</p>
        </Dialog>
        <Dialog title="본인 확인" open onClose={closeAbove}>
          <p>위</p>
        </Dialog>
      </>,
    );

    await userEvent.keyboard('{Escape}');

    expect(closeAbove).toHaveBeenCalledOnce();
    expect(closeBelow).not.toHaveBeenCalled();
  });

  it('닫혀 있으면 그리지 않는다', () => {
    render(
      <Dialog title="청약철회" open={false} onClose={() => {}}>
        <p>내용</p>
      </Dialog>,
    );

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
