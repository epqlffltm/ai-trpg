// web/apps/web/src/pages/gallery/CharacterGallery.tsx
// 캐릭터 하나의 갤러리. 공개 판을 읽어 해금 대상 씬의 칸을 늘어놓는다. 판을 읽지 못하면(공개를 내림, 숨김) 연 수만 적는다.

import { useQuery } from '@tanstack/react-query';
import { openedLabel, sceneCells } from './galleryView';
import { publicCharacterQuery } from './galleryQueries';
import { SceneTile } from './SceneTile';

export function CharacterGallery({ characterId, unlocked }: { characterId: string; unlocked: Map<string, string> }) {
  const character = useQuery(publicCharacterQuery(characterId));
  if (character.isPending) return <p className="hint">불러오는 중</p>;
  if (character.isError) {
    return (
      <section className="page-section">
        <h2>볼 수 없는 캐릭터</h2>
        <p className="hint">공개를 내렸거나 가려진 캐릭터입니다. 연 장면 {unlocked.size}개는 기록에 남아 있습니다.</p>
      </section>
    );
  }
  const cells = sceneCells(character.data.document.event_scenes, unlocked);
  const heading = `gallery-${characterId}`;
  return (
    <section className="page-section" aria-labelledby={heading}>
      <h2 id={heading}>
        {character.data.document.name} <span className="hint">{openedLabel(cells)}</span>
      </h2>
      <ul className="plain-list scene-grid" aria-label={`${character.data.document.name}의 장면`}>
        {cells.map((cell) => (
          <SceneTile key={cell.id} cell={cell} />
        ))}
      </ul>
    </section>
  );
}
