// web/apps/web/src/pages/story/StoryCastProfile.tsx
// 인물의 그림과 인물 창(D5)의 칸. 장면의 인물 줄(StoryCastRow)과 왼쪽 열의 인물 창(StoryCastPanel)이 함께 쓴다.
// 인물 창의 칸은 소개, 나이·성별, 호감도(숫자나 단계), 고백 대기, 건넨 선물, 함께 본 이벤트다. 제작자가 고른 항목만 서버가 보낸다.
// 그림은 그 표정의 스프라이트(없으면 기본 표정, 대표 그림)다. 실루엣 인물은 검은 칸이다.

import type { StoryState, StoryView, StoryViewCast } from '../../api/story';
import { useImageUrl } from '../../hooks/useImageUrl';
import { IntroHtml } from '../chat/character/IntroHtml';
import { affectionText, coolingText, eventNames, giftNames, portraitOf, profileLine } from './storyCastView';

type PortraitProps = { cast: StoryViewCast | undefined; expression: string | null; large?: boolean };

export function CastPortrait({ cast, expression, large = false }: PortraitProps) {
  const image = useImageUrl(portraitOf(cast, expression));
  const silhouette = !cast || cast.reveal === 'silhouette';
  const size = large ? ' story-cast__portrait--large' : '';
  if (image.url) return <img src={image.url} alt="" className={`story-cast__portrait${size}`} />;
  return <span className={`story-cast__portrait${size}${silhouette ? ' story-cast__portrait--silhouette' : ''}`} aria-hidden="true" />;
}

/** 인물 창(D5). 서버가 보낸 항목만 그린다 */
export function CastProfile({ view, state, cast }: { view: StoryView; state: StoryState; cast: StoryViewCast }) {
  const profile = profileLine(cast);
  const affection = affectionText(cast, state.affection[cast.id]);
  const cooling = coolingText(cast, state.minutes);
  const gifts = giftNames(view, cast);
  const events = eventNames(view, cast);
  return (
    <div className="story-profile">
      {profile ? <p className="hint">{profile}</p> : null}
      {affection ? <p>{affection}</p> : null}
      {cooling ? <p className="hint">{cooling}</p> : null}
      {cast.intro_html ? <IntroHtml html={cast.intro_html} /> : null}
      {gifts.length > 0 ? <p className="hint">건넨 선물: {gifts.join(', ')}</p> : null}
      {events.length > 0 ? <p className="hint">함께 본 이벤트: {events.join(', ')}</p> : null}
    </div>
  );
}
