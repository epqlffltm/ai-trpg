// web/apps/web/src/pages/chat/character/CharacterDetail.tsx
// 캐릭터 소개(C2)를 그린다. 왼쪽(모바일은 위)에 그림과 소개, 호감도의 단계, 오른쪽(모바일은 아래)에 시작 상황과 내 대화.
// 아래에 해금 대상 일러스트의 칸. 보이는 것은 마지막으로 공개한 판이다. 신고는 2단계(E4)다.

import type { PublicCharacterDetail } from '../../../api/types';
import { useSession } from '../../../auth/useSession';
import { formatDate } from '../../../format/dateTime';
import { genreName } from '../../../genres/genres';
import { useImageUrl } from '../../../hooks/useImageUrl';
import { CharacterConversations } from './CharacterConversations';
import { CharacterScenes } from './CharacterScenes';
import { profileLine, stageNames } from './characterView';
import { IntroHtml } from './IntroHtml';
import { StartPicker } from './StartPicker';

export function CharacterDetail({ character }: { character: PublicCharacterDetail }) {
  const document = character.document;
  const signedIn = useSession() !== null;
  return (
    <main className="page character-page">
      <CharacterHead character={character} />
      <div className="character-page__body">
        <div className="character-page__main">
          <section aria-labelledby="character-intro">
            <h2 id="character-intro">소개</h2>
            <IntroHtml html={document.intro_html} />
          </section>
          <AffectionStages names={stageNames(document.affection)} />
        </div>
        <aside className="character-page__side" aria-label="대화">
          <StartPicker characterId={character.id} starts={document.starts} />
          {signedIn ? <CharacterConversations characterId={character.id} latestVersion={character.version} /> : null}
        </aside>
      </div>
      <CharacterScenes characterId={character.id} scenes={document.event_scenes} />
    </main>
  );
}

function CharacterHead({ character }: { character: PublicCharacterDetail }) {
  const document = character.document;
  const image = useImageUrl(document.image_id);
  const profile = profileLine(document);
  return (
    <header className="character-page__head">
      {image.url ? <img src={image.url} alt={document.name} className="character-page__image" /> : null}
      <div>
        <h1>{document.name}</h1>
        {profile ? <p className="character-page__profile">{profile}</p> : null}
        <ul className="tag-links" aria-label="태그">
          {document.rating === 'adult' ? <li className="item-card__tag">성인</li> : null}
          <li className="item-card__tag">{genreName(document.genre)}</li>
          {document.tags.map((tag) => (
            <li key={tag} className="item-card__tag">
              #{tag}
            </li>
          ))}
        </ul>
        <p className="hint">
          {character.version}판 · {formatDate(character.published_at)} 공개
        </p>
      </div>
    </header>
  );
}

function AffectionStages({ names }: { names: string[] }) {
  if (names.length === 0) return null;
  return (
    <section aria-labelledby="character-affection">
      <h2 id="character-affection">호감도의 단계</h2>
      <ol className="character-page__stages">
        {names.map((name, index) => (
          <li key={`${index}-${name}`} className="item-card__tag">
            {index + 1}. {name}
          </li>
        ))}
      </ol>
    </section>
  );
}
