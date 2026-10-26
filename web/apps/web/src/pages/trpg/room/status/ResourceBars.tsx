// web/apps/web/src/pages/trpg/room/status/ResourceBars.tsx
// HP 말고 다른 수치(#804) 줄들. "마나 3 / 7" 과 막대. HP 줄(HpBar.tsx)과 같은 모양이다. 수치가 없는 판이면 그리지 않는다.
// 막대는 꾸밈이다. 읽는 값은 글(그리고 meter 의 값)에 있다. 바꾸는 것은 서버뿐이다(쉬기, 물건의 맞추기).

import type { Sheet } from '../../../../api/types';

export function ResourceBars({ sheet }: { sheet: Sheet }) {
  const resources = sheet.resources ?? [];
  if (resources.length === 0) return null;
  return (
    <ul className="plain-list" aria-label="수치">
      {resources.map((resource) => (
        <li key={resource.key} className="hp">
          <span className="hp__text">
            {resource.name} {resource.value} / {resource.max}
          </span>
          <meter className="hp__meter" min={resource.min} max={resource.max} value={resource.value} aria-hidden="true" />
        </li>
      ))}
    </ul>
  );
}
