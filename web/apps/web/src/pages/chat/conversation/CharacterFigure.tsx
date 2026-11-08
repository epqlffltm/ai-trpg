// web/apps/web/src/pages/chat/conversation/CharacterFigure.tsx
// chat 의 그림 창(StagePicture)에 세우는 캐릭터 하나. 배경 위 가운데에 캐릭터 그림(표정), 왼쪽 아래에 이름표(Stitch 21번).
// 무엇을 세울지(표정의 그림)는 conversationView 의 pictureOf 가 고른다. 이름은 그림의 대체 글로도 읽히므로 이름표는 꾸밈이다.

import { useImageUrl } from '../../../hooks/useImageUrl';

export function CharacterFigure({ sprite, name }: { sprite: string | null; name: string }) {
  const image = useImageUrl(sprite);
  return (
    <>
      {image.url ? <img className="conversation__sprite" src={image.url} alt={name} /> : null}
      <p className="conversation__nameplate" aria-hidden="true">
        {name}
      </p>
    </>
  );
}
