// web/apps/web/src/pages/trpg/room/status/ResourceBars.test.tsx
// HP 말고 다른 수치(#804)의 줄. 시트의 수치를 "이름 값 / 최대" 로 보이고, 수치가 없는 판이면 아무것도 그리지 않는다.

import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { Sheet } from '../../../../api/types';
import { sheet } from '../../../../test/tableFixtures';
import { ResourceBars } from './ResourceBars';

describe('수치 줄', () => {
  it('수치마다 값과 최대를 보인다', () => {
    const mine = sheet({
      resources: [
        { key: 'mana', name: '마나', value: 3, min: 0, max: 7 },
        { key: 'stamina', name: '스태미나', value: 4, min: 0, max: 4 },
      ],
    }) as unknown as Sheet;
    render(<ResourceBars sheet={mine} />);

    const list = within(screen.getByRole('list', { name: '수치' }));
    expect(list.getAllByRole('listitem').map((item) => item.textContent)).toEqual(['마나 3 / 7', '스태미나 4 / 4']);
  });

  it('수치가 없으면 그리지 않는다', () => {
    const { container } = render(<ResourceBars sheet={sheet({ resources: [] }) as unknown as Sheet} />);
    expect(container).toBeEmptyDOMElement();
  });
});
