// web/apps/web/src/pages/story/StoryCastPanel.tsx
// 장면(D2)의 왼쪽 열 "인물" 창(Stitch 22번). 세계관의 인물 목록(만나지 않은 인물은 "???")과, 고른 인물의 그림, 이름, 인물 창(D5)의 칸.
// 숨김인 인물은 만나기 전에는 서버가 목록에 싣지 않는다. 실루엣 인물은 이름과 칸이 비어 온다.
// 건네기와 고백은 여기 두지 않는다. 장면의 인물을 눌러 연다(StoryCastRow).

import { useState } from 'react';
import type { StoryState, StoryView } from '../../api/story';
import { CastPortrait, CastProfile } from './StoryCastProfile';
import { castName, castOf } from './storyWorld';

type Props = { view: StoryView; state: StoryState };

export function StoryCastPanel({ view, state }: Props) {
  const [chosen, setChosen] = useState<string | null>(null);
  if (view.cast.length === 0) return <p className="hint">아직 만난 인물이 없습니다.</p>;
  const cast = chosen ? castOf(view, chosen) : undefined;
  return (
    <div className="story-cast-panel">
      <ul className="plain-list story-cast-panel__list" aria-label="인물 목록">
        {view.cast.map((entry) => (
          <li key={entry.id}>
            <button type="button" className="story-cast-panel__member" aria-pressed={chosen === entry.id} onClick={() => setChosen(chosen === entry.id ? null : entry.id)}>
              <CastPortrait cast={entry} expression={null} />
              <span>{castName(view, entry.id)}</span>
            </button>
          </li>
        ))}
      </ul>
      {cast ? (
        <section className="story-cast-panel__detail" aria-label={`${castName(view, cast.id)}의 정보`}>
          <CastPortrait cast={cast} expression={null} large />
          <p className="story-cast-panel__name">{castName(view, cast.id)}</p>
          {cast.reveal === 'silhouette' ? <p className="hint">아직 만나지 않은 인물입니다.</p> : <CastProfile view={view} state={state} cast={cast} />}
        </section>
      ) : (
        <p className="hint">인물을 고르면 소개와 호감도를 봅니다.</p>
      )}
    </div>
  );
}
