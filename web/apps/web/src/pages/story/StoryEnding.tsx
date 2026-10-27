// web/apps/web/src/pages/story/StoryEnding.tsx
// 엔딩 화면(D2). 엔딩 장면의 답이 끝나면 대사창 위에 띄운다. 엔딩의 이름과 "엔딩 3/7"(기록에 남는 엔딩 가운데 본 수),
// "새로 시작"(같은 세계관의 새 세션), "내 이야기로", 그리고 제작자가 후일담을 골랐으면 "후일담 이어 가기"(닫기).
// 엔딩의 그림과 D6 의 기록 화면은 다음에 더한다.

import { Button } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import type { StoryView } from '../../api/story';
import { countedEndings, endingName, hasEpilogue } from './storyWorld';
import { storyEndingsQuery } from './storyQueries';

type Props = {
  worldId: string;
  view: StoryView;
  endingId: string;
  starting: boolean;
  onRestart: () => void;
  onClose: () => void;
};

export function StoryEnding({ worldId, view, endingId, starting, onRestart, onClose }: Props) {
  const seen = useQuery(storyEndingsQuery(worldId));
  const total = countedEndings(view);
  return (
    <section className="story-ending" aria-label="엔딩">
      <p className="hint">엔딩</p>
      <h2>{endingName(view, endingId)}</h2>
      {seen.data && total > 0 ? <p>엔딩 {Math.min(seen.data.items.length, total)}/{total}</p> : null}
      <div className="actions">
        <Button busy={starting} onClick={onRestart}>
          새로 시작
        </Button>
        <Link to="/story">내 이야기로</Link>
        {hasEpilogue(view) ? (
          <Button variant="secondary" onClick={onClose}>
            후일담 이어 가기
          </Button>
        ) : (
          <Button variant="quiet" onClick={onClose}>
            닫기
          </Button>
        )}
      </div>
    </section>
  );
}
