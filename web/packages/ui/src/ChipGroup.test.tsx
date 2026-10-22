// web/packages/ui/src/ChipGroup.test.tsx
// 칩의 줄이 고른 것을 알리고, 다시 누르면 푸는지 본다.

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ChipGroup } from './ChipGroup';

const CHIPS = [
  { value: 'horror', label: '호러' },
  { value: 'sf', label: 'SF' },
];

describe('ChipGroup', () => {
  it('고른 칩은 눌린 것으로 알리고, 다른 칩을 누르면 그 값을 넘긴다', async () => {
    const onChange = vi.fn();
    render(<ChipGroup label="장르" chips={CHIPS} selected="horror" onChange={onChange} />);

    expect(screen.getByRole('button', { name: '호러' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'SF' })).toHaveAttribute('aria-pressed', 'false');
    await userEvent.click(screen.getByRole('button', { name: 'SF' }));

    expect(onChange).toHaveBeenCalledWith('sf');
  });

  it('고른 칩을 다시 누르면 푼다', async () => {
    const onChange = vi.fn();
    render(<ChipGroup label="장르" chips={CHIPS} selected="horror" onChange={onChange} />);

    await userEvent.click(screen.getByRole('button', { name: '호러' }));

    expect(onChange).toHaveBeenCalledWith(undefined);
  });
});
