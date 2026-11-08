// web/apps/web/src/pages/trpg/room/status/SceneHere.tsx
// 퀘스트·지도(J)의 장소에 붙는 "여기 있는 인물과 몬스터"(#254 의 화면). 이름, 몸 상태와 부상, 지닌 물건을 보인다.
// 몬스터의 HP 숫자는 서버가 주지 않아 보이지 않는다. 고르는 것은 sceneView.ts 다.
// 죽지 않은 것에는 "치기" 단추가 있다. 누르면 선언 입력의 행동 칸을 타격 판정으로 채울 뿐이다(능력치, 피해는 사람이 고른다).
// 장면은 선언 입력과 같은 읽기(sceneCastQuery)를 함께 쓴다. 이벤트가 오면 라운드와 함께 다시 읽는다(useBatchedRefetch).

import { useQuery } from '@tanstack/react-query';
import type { TableDetail } from '../../../../api/types';
import { sceneCastQuery } from '../round/roundQueries';
import { ActionButton, type ActionShortcuts } from './ActionButton';
import { sceneEntryNote, sceneHere } from './sceneView';

type Props = { table: TableDetail; here: string | null | undefined; shortcuts: ActionShortcuts };

export function SceneHere({ table, here, shortcuts }: Props) {
  const enabled = table.status === 'playing';
  const cast = useQuery({ ...sceneCastQuery(table.id), enabled });
  if (!enabled) return null;
  const entries = sceneHere(cast.data, here, table.rules);
  if (entries.length === 0) return null;
  return (
    <>
      <p className="hint">여기 있는 인물과 몬스터</p>
      <ul className="ways" aria-label="여기 있는 인물과 몬스터">
        {entries.map((entry) => {
          const note = sceneEntryNote(entry);
          return (
            <li key={`${entry.kind}:${entry.id}`}>
              {entry.name}
              {entry.kind === 'monster' ? <span className="hint"> (몬스터)</span> : null}
              {note ? <span className="hint"> · {note}</span> : null}{' '}
              {entry.harmable ? (
                <ActionButton
                  shortcuts={shortcuts}
                  patch={{ kind: 'check', purpose: 'harm', target: `${entry.kind}:${entry.id}` }}
                  label="치기"
                  what={entry.name}
                />
              ) : null}
            </li>
          );
        })}
      </ul>
    </>
  );
}
