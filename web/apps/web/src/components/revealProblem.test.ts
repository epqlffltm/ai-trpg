// web/apps/web/src/components/revealProblem.test.ts
// 폼의 실패를 눈앞에 데려오는지 본다: 틀린 칸이 있으면 첫 칸, 없으면 실패의 한 줄로 초점과 스크롤을 옮긴다.

import { afterEach, describe, expect, it, vi } from 'vitest';
import { revealProblem } from './revealProblem';

function form(html: string): HTMLFormElement {
  const element = document.createElement('form');
  element.innerHTML = html;
  document.body.append(element);
  return element;
}

afterEach(() => {
  document.body.innerHTML = '';
  vi.restoreAllMocks();
});

describe('revealProblem', () => {
  it('틀린 첫 칸으로 스크롤하고 커서를 둔다', () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    const element = form(
      '<div id="notice" tabindex="-1">실패</div><input id="a"><input id="b" aria-invalid="true"><input id="c" aria-invalid="true">',
    );

    revealProblem(element.querySelector<HTMLElement>('#notice')!);

    expect(document.activeElement?.id).toBe('b');
    expect(scroll).toHaveBeenCalledWith({ block: 'center' });
  });

  it('틀린 칸이 없으면 실패의 한 줄에 초점을 둔다', () => {
    const element = form('<div id="notice" tabindex="-1">실패</div><input id="a">');

    revealProblem(element.querySelector<HTMLElement>('#notice')!);

    expect(document.activeElement?.id).toBe('notice');
  });

  it('폼 밖의 줄이면 그 줄에 초점을 둔다', () => {
    const notice = document.createElement('div');
    notice.tabIndex = -1;
    document.body.append(notice);

    revealProblem(notice);

    expect(document.activeElement).toBe(notice);
  });
});
