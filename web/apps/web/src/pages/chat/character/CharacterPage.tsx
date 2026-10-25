// web/apps/web/src/pages/chat/character/CharacterPage.tsx
// 캐릭터 소개(C2, /chat/characters/:characterId). 이 캐릭터와 대화를 시작하거나 이어 간다.
// 로그인하지 않아도 전체이용가면 보인다(#530). 볼 수 없으면(없다, 공개가 내려감, 성인 등급) 서버는 모두 404 이고 화면도 까닭을 가르지 않는다.
// 이 파일은 읽기와 상태만 맡는다. 그리는 것은 CharacterDetail 이다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router';
import { ApiError } from '../../../api/errors';
import { publicCharacterQuery } from '../../gallery/galleryQueries';
import { CharacterDetail } from './CharacterDetail';

export function CharacterPage() {
  const { characterId = '' } = useParams();
  const query = useQuery(publicCharacterQuery(characterId));

  if (query.isPending) return <p className="page page--loading">불러오는 중</p>;
  if (query.isError) return <LoadProblem error={query.error} onRetry={() => void query.refetch()} />;
  return <CharacterDetail character={query.data} />;
}

function LoadProblem({ error, onRetry }: { error: Error; onRetry: () => void }) {
  // 경로의 ID 가 UUID 가 아니면 422 다. 없는 것과 같게 본다
  const missing = error instanceof ApiError && (error.status === 404 || error.status === 422);
  return (
    <main className="page page--narrow">
      <h1>캐릭터</h1>
      {missing ? (
        <Notice>볼 수 없는 캐릭터입니다. 공개가 내려갔거나, 성인 등급이라 성인 확인이 필요할 수 있습니다.</Notice>
      ) : (
        <Notice tone="error">
          캐릭터를 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={onRetry}>
            다시 시도
          </Button>
        </Notice>
      )}
      <Link to="/chat">다른 캐릭터 찾기</Link>
    </main>
  );
}
