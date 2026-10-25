// web/apps/web/src/pages/chat/character/CharacterScenes.tsx
// 이 캐릭터의 일러스트(C2). 해금 대상인 이벤트 씬마다 칸 하나, 연 것은 그림, 열지 않은 것은 흐린 그림(갤러리 C7 의 칸과 같다).
// 로그인하지 않았으면 모두 열지 않은 칸이다. 해금 대상인 씬이 없으면 이 칸을 그리지 않는다.

import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import type { EventSceneDocument } from '../../../api/types';
import { useSession } from '../../../auth/useSession';
import { groupUnlocks, openedLabel, sceneCells } from '../../gallery/galleryView';
import { SceneTile } from '../../gallery/SceneTile';
import { unlocksOfQuery } from '../chatQueries';

export function CharacterScenes({ characterId, scenes }: { characterId: string; scenes: EventSceneDocument[] }) {
  const signedIn = useSession() !== null;
  const unlocks = useQuery({ ...unlocksOfQuery(characterId), enabled: signedIn });
  const unlocked = groupUnlocks(signedIn ? (unlocks.data?.items ?? []) : []).get(characterId) ?? new Map<string, string>();
  const cells = sceneCells(scenes, unlocked);
  if (cells.length === 0) return null;
  return (
    <section className="page-section" aria-labelledby="character-scenes">
      <h2 id="character-scenes">
        일러스트 <span className="hint">{openedLabel(cells)}</span>
      </h2>
      {signedIn ? (
        <p>
          <Link to="/gallery?tab=chat">갤러리에서 보기</Link>
        </p>
      ) : (
        <p className="hint">로그인하면 내가 연 일러스트가 보입니다.</p>
      )}
      {unlocks.isError ? <p className="hint">연 일러스트를 불러오지 못했습니다. 모두 닫힌 칸으로 보입니다.</p> : null}
      <ul className="plain-list scene-grid" aria-label="일러스트">
        {cells.map((cell) => (
          <SceneTile key={cell.id} cell={cell} />
        ))}
      </ul>
    </section>
  );
}
