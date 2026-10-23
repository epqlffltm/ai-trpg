// web/apps/web/src/pages/chat/studio/characters/CharactersPage.tsx
// 내 캐릭터(C6, /chat/studio/characters). 최근에 고친 것부터 한 쪽씩(더 보기). 마이페이지의 "만들기"에서 온다.
// 지금(1~2단계)은 운영자만 만든다. 만들기에서 막히면 그 화면이 알린다.

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import type { AssetCharacterSummary } from '../../../../api/types';
import { formatDate } from '../../../../format/dateTime';
import { characterPath, NEW_CHARACTER_PATH } from './characterPaths';
import { myCharactersQuery } from './characterQueries';

export function CharactersPage() {
  const query = useInfiniteQuery(myCharactersQuery());
  const characters = query.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <main className="page page--medium">
      <h1>내 캐릭터</h1>
      <p className="hint">chat 에서 1:1 로 대화하는 캐릭터를 만듭니다. 게시한 판으로 대화합니다.</p>
      <p>
        <Link to={NEW_CHARACTER_PATH}>캐릭터 만들기</Link>
      </p>
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError ? (
        <Notice tone="error">
          불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void query.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {query.isSuccess && characters.length === 0 ? (
        <div className="empty-state">
          <p>아직 만든 캐릭터가 없습니다.</p>
          <Link to={NEW_CHARACTER_PATH}>첫 캐릭터 만들기</Link>
        </div>
      ) : null}
      <ul className="plain-list studio-list" aria-label="내 캐릭터">
        {characters.map((character) => (
          <CharacterItem key={character.id} character={character} />
        ))}
      </ul>
      {query.hasNextPage ? (
        <div className="load-more">
          <Button variant="secondary" busy={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
            더 보기
          </Button>
        </div>
      ) : null}
    </main>
  );
}

function CharacterItem({ character }: { character: AssetCharacterSummary }) {
  return (
    <li className="studio-list__item">
      <Link to={characterPath(character.id)}>{character.name}</Link>{' '}
      {character.hidden_at ? <span className="badge">운영자가 숨김</span> : null}
      <p className="hint">
        {character.visibility === 'public' ? '공개' : '비공개'} ·{' '}
        {character.latest_version === null ? '아직 게시하지 않음' : `${character.latest_version}판까지 게시`} · 고친 날{' '}
        {formatDate(character.updated_at)}
      </p>
    </li>
  );
}
