// web/apps/web/src/pages/story/StoryPicture.tsx
// 그림 창(D2 의 위). 이벤트나 엔딩의 일러스트가 열렸으면 그것을, 아니면 지금 장소와 시간대의 배경을 띄운다.
// 그림은 토큰을 실어 받는다. 그림이 없거나 받지 못하면 그림 창을 그리지 않는다(장면의 인물 줄은 따로 있다).

import { useImageUrl } from '../../hooks/useImageUrl';

type Props = { scene: { title: string; imageId: string } | null; background: string | null; placeName: string };

export function StoryPicture({ scene, background, placeName }: Props) {
  const image = useImageUrl(scene?.imageId ?? background);
  if (!image.url) return null;
  return (
    <figure className="story-picture" aria-label="그림 창">
      <img src={image.url} alt={scene ? scene.title : placeName} className="story-picture__image" />
      {scene ? <figcaption className="story-picture__caption">{scene.title}</figcaption> : null}
    </figure>
  );
}
