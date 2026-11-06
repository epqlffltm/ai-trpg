// web/apps/web/src/pages/chat/conversation/PicturePane.tsx
// 그림 창(C3 의 위). 배경 위에 캐릭터 그림을 겹친다. 이벤트 씬이 붙은 답이면 이벤트 씬이 둘을 대신한다.
// 무엇을 띄울지는 conversationView 의 pictureOf 가 고른다. 그림은 토큰을 실어 받는다(성인 등급의 그림).
// 배경과 캐릭터를 띄울 때는 왼쪽 아래에 캐릭터의 이름표를 단다(Stitch 21번). 이름은 그림의 대체 글로도 읽히므로 이름표는 꾸밈이다.

import { useImageUrl } from '../../../hooks/useImageUrl';
import type { pictureOf } from './conversationView';

type Picture = ReturnType<typeof pictureOf>;

export function PicturePane({ picture, name }: { picture: Picture; name: string }) {
  return (
    <section className="conversation__picture" aria-label="그림">
      {picture.scene ? <SceneImage title={picture.scene.title} imageId={picture.scene.imageId} /> : <Stage background={picture.background} sprite={picture.sprite} name={name} />}
    </section>
  );
}

function SceneImage({ title, imageId }: { title: string; imageId: string }) {
  const image = useImageUrl(imageId);
  return (
    <figure className="conversation__scene">
      {image.url ? <img src={image.url} alt={title} /> : null}
      <figcaption>{title}</figcaption>
    </figure>
  );
}

function Stage({ background, sprite, name }: { background: string | null; sprite: string | null; name: string }) {
  const backgroundImage = useImageUrl(background);
  const spriteImage = useImageUrl(sprite);
  return (
    <div className="conversation__stage">
      {backgroundImage.url ? <img className="conversation__background" src={backgroundImage.url} alt="" /> : null}
      {spriteImage.url ? <img className="conversation__sprite" src={spriteImage.url} alt={name} /> : null}
      <p className="conversation__nameplate" aria-hidden="true">
        {name}
      </p>
    </div>
  );
}
