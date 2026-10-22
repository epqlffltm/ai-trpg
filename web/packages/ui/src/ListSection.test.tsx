// web/packages/ui/src/ListSection.test.tsx
// 목록 한 줄의 틀이 상태마다 맞는 것을 그리는지 본다.

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ListSection } from './ListSection';

describe('ListSection', () => {
  it('불러오지 못하면 다시 시도를 보이고, 누르면 onRetry 를 부른다', async () => {
    const onRetry = vi.fn();
    render(<ListSection title="공개 시나리오" status="error" onRetry={onRetry} />);

    await userEvent.click(screen.getByRole('button', { name: '다시 시도' }));

    expect(screen.getByRole('alert')).toHaveTextContent('불러오지 못했습니다.');
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('비었으면 다음에 할 일을 보이고 내용은 그리지 않는다', () => {
    render(
      <ListSection title="이어하기" status="empty" emptyText="첫 테이블을 만들어 보세요.">
        <p>내용</p>
      </ListSection>,
    );

    expect(screen.getByText('첫 테이블을 만들어 보세요.')).toBeInTheDocument();
    expect(screen.queryByText('내용')).not.toBeInTheDocument();
  });

  it('준비되면 내용을 그린다', () => {
    render(
      <ListSection title="이어하기" status="ready">
        <p>내용</p>
      </ListSection>,
    );

    expect(screen.getByRole('heading', { name: '이어하기' })).toBeInTheDocument();
    expect(screen.getByText('내용')).toBeInTheDocument();
  });
});
