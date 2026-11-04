// web/apps/web/src/pages/create/CreatePage.tsx
// 만들기의 입구(Stitch 설계서의 19번 첫 칸). 왼쪽 메뉴 열의 "만들기"와 아래 탭 바의 "만들기"가 여기로 온다.
// "무엇을 만들까요"에서 서비스를 고르고 "다음"을 누르면 그 서비스의 제작 화면으로 간다.
// 고르기 전에는 "다음"이 꺼져 있다. 제작 화면을 하나로 합치는 것(설계서의 조합 화면)은 아직 하지 않는다.

import { Button, SelectField } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router';
import { CREATE_TARGETS, createTargetPath, type CreateTarget } from './createTargets';

export function CreatePage() {
  const navigate = useNavigate();
  const [target, setTarget] = useState<CreateTarget | ''>('');

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (target) void navigate(createTargetPath(target));
  }

  return (
    <main className="page page--narrow">
      <h1>만들기</h1>
      <form onSubmit={submit} aria-label="만들 것 고르기">
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
        <Button type="submit" disabled={!target}>
          다음
        </Button>
      </form>
    </main>
  );
}
