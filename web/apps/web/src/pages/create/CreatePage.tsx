// web/apps/web/src/pages/create/CreatePage.tsx
// 만들기의 입구(Stitch 19번의 맨 앞 칸). 왼쪽 메뉴 열의 "만들기"와 아래 탭 바의 "만들기"가 여기로 온다.
// "무엇을 만들까요"에서 서비스를 고른다. TRPG 면 "만들 것"(시나리오, 캠페인, 재료)이 하나 더 나온다.
// story 면 "JSON 으로 세계관 넣기"도 함께 보인다(지금은 운영자만 연다).
// 다 고르기 전에는 "다음"이 꺼져 있다. "다음"은 고른 것을 새로 만드는 화면으로 간다.
// 탭으로 나뉜 조합 화면은 저마다의 고치기 화면이다(시나리오·캐릭터·세계관 고치기).

import { Button, SelectField } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router';
import { isOperator } from '../../auth/roles';
import { useSession } from '../../auth/useSession';
import type { StudioKind } from '../../api/studio';
import { CREATE_TARGETS, TRPG_KINDS, WORLD_IMPORT_PATH, createPath, type CreateTarget } from './createTargets';

export function CreatePage() {
  const navigate = useNavigate();
  const session = useSession();
  const [target, setTarget] = useState<CreateTarget | ''>('');
  const [kind, setKind] = useState<StudioKind | ''>('');
  const path = createPath(target, kind);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (path) void navigate(path);
  }

  return (
    <main className="page page--narrow create-page">
      <h1>만들기</h1>
      <form className="create-page__form" onSubmit={submit} aria-label="만들 것 고르기">
        <SelectField label="무엇을 만들까요" value={target} onChange={(event) => setTarget(event.target.value as CreateTarget | '')}>
          <option value="" disabled>
            고르세요
          </option>
          {CREATE_TARGETS.map((one) => (
            <option key={one.value} value={one.value}>
              {one.label}
            </option>
          ))}
        </SelectField>
        {target === 'trpg' ? (
          <SelectField label="만들 것" value={kind} onChange={(event) => setKind(event.target.value as StudioKind | '')}>
            <option value="" disabled>
              고르세요
            </option>
            {TRPG_KINDS.map((one) => (
              <option key={one.value} value={one.value}>
                {one.label}
              </option>
            ))}
          </SelectField>
        ) : null}
        {target === 'story' && isOperator(session) ? (
          <p className="hint">
            세계관을 JSON 파일로 가지고 있으면 <Link to={WORLD_IMPORT_PATH}>JSON 으로 세계관 넣기</Link>
          </p>
        ) : null}
        <div className="form-actions">
          <Button type="submit" disabled={path === null}>
            다음
          </Button>
        </div>
      </form>
    </main>
  );
}
