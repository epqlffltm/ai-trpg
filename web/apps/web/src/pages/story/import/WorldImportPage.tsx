// web/apps/web/src/pages/story/import/WorldImportPage.tsx
// JSON 으로 세계관 넣기(D7 전의 운영자 도구, /story/worlds/import). 운영자만 열린다(RequireOperator, 서버도 403 operator_only).
// 시험용 세계관(sampleWorld.ts)이 채워져 있다. 인물마다 게시한 판이 있는 내 chat 캐릭터를 고르고 만든 뒤 게시한다.
// 칸의 검사는 asset 서버가 한다. 만들기의 거절(칸의 오류, 남의 캐릭터)과 게시를 막는 것(409 problems)을 줄마다 보인다.
// 게시하면 내 이야기(/story)의 "새로 시작"에 나온다. 세계관을 고치는 화면(D7)이 생기면 이 화면은 내려놓는다.

import { Button, Notice, SelectField, TextField } from '@ai-trpg/ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { fetchMyCharacters } from '../../../api/characters';
import { createStoryWorld, publishStoryWorld, type StoryWorldCreate, type StoryWorldDetail } from '../../../api/storyWorlds';
import { TextAreaField } from '../../../components/TextAreaField';
import { STORY_KEY } from '../storyQueries';
import { SAMPLE_WORLD } from './sampleWorld';
import { allChosen, castSlots, describeImportProblem, parseWorld, warningText, withCharacters } from './worldImport';

const CHARACTERS_LIMIT = 100;

export function WorldImportPage() {
  const [text, setText] = useState(() => JSON.stringify(SAMPLE_WORLD, null, 2));
  const [chosen, setChosen] = useState<Record<number, string>>({});
  const [created, setCreated] = useState<StoryWorldDetail | null>(null);
  const parsed = useMemo(() => parseWorld(text), [text]);
  const slots = 'world' in parsed ? castSlots(parsed.world) : [];
  const characters = useQuery({ queryKey: ['asset', 'characters', 'mine', 'import'], queryFn: ({ signal }) => fetchMyCharacters({ limit: CHARACTERS_LIMIT, offset: 0 }, signal) });
  const published = (characters.data?.items ?? []).filter((character) => character.latest_version !== null);
  const creating = useMutation({ mutationFn: (body: StoryWorldCreate) => createStoryWorld(body), onSuccess: setCreated });

  function create() {
    if ('world' in parsed) creating.mutate(withCharacters(parsed.world, chosen) as StoryWorldCreate);
  }

  return (
    <main className="page page--medium">
      <p>
        <Link to="/story">내 이야기</Link>
      </p>
      <h1>JSON 으로 세계관 넣기</h1>
      <p className="hint">운영자의 시험 도구입니다. 시험용 세계관 "시험 마을"이 채워져 있습니다. 인물마다 내 캐릭터를 고른 뒤 만들고 게시하세요.</p>
      <TextAreaField label="세계관 JSON" rows={18} value={text} onChange={(event) => setText(event.target.value)} error={'error' in parsed ? parsed.error : undefined} />
      <section className="page-section" aria-labelledby="import-cast">
        <h2 id="import-cast">인물의 캐릭터</h2>
        {characters.isError ? <Notice tone="error">내 캐릭터를 불러오지 못했습니다.</Notice> : null}
        {characters.isSuccess && published.length === 0 ? (
          <p className="empty-state">
            게시한 chat 캐릭터가 없습니다. <Link to="/chat/studio/characters">캐릭터 만들기</Link>에서 만들고 게시해 주세요.
          </p>
        ) : null}
        {slots.length === 0 && 'world' in parsed ? <p className="hint">cast 에 인물이 없습니다.</p> : null}
        {slots.map((slot) => (
          <SelectField
            key={slot.index}
            label={`인물 ${slot.id}`}
            value={chosen[slot.index] ?? ''}
            onChange={(event) => setChosen((current) => ({ ...current, [slot.index]: event.target.value }))}
          >
            <option value="">고르세요</option>
            {published.map((character) => (
              <option key={character.id} value={character.id}>
                {character.name} ({character.latest_version}판)
              </option>
            ))}
          </SelectField>
        ))}
      </section>
      <Problems lines={creating.error ? describeImportProblem(creating.error) : []} />
      <div className="form-actions">
        <Button busy={creating.isPending} disabled={!('world' in parsed) || !allChosen(slots, chosen) || created !== null} onClick={create}>
          만들기
        </Button>
      </div>
      {created ? <PublishStep world={created} /> : null}
    </main>
  );
}

function PublishStep({ world }: { world: StoryWorldDetail }) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState('');
  const publishing = useMutation({
    mutationFn: () => publishStoryWorld(world.id, note.trim()),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: [...STORY_KEY, 'my-worlds'] }),
  });
  return (
    <section className="page-section" aria-labelledby="import-publish">
      <h2 id="import-publish">게시</h2>
      <p>
        "{world.name}"을 만들었습니다. 비공개 초안입니다. 게시하면 그 판으로 이야기를 시작할 수 있습니다.
      </p>
      <TextField label="이번 판의 메모(비워도 됩니다)" maxLength={500} value={note} onChange={(event) => setNote(event.target.value)} />
      <Problems lines={publishing.error ? describeImportProblem(publishing.error) : []} />
      {publishing.data ? (
        <Notice tone="info">
          {publishing.data.number}판을 게시했습니다. <Link to="/story">내 이야기에서 새로 시작</Link>
          {publishing.data.warnings.length > 0 ? (
            <ul aria-label="알리는 것">
              {publishing.data.warnings.map((name) => (
                <li key={name}>{warningText(name)}</li>
              ))}
            </ul>
          ) : null}
        </Notice>
      ) : (
        <Button busy={publishing.isPending} onClick={() => publishing.mutate()}>
          게시
        </Button>
      )}
    </section>
  );
}

function Problems({ lines }: { lines: string[] }) {
  if (lines.length === 0) return null;
  return (
    <Notice tone="error">
      <ul className="plain-list" aria-label="문제">
        {lines.map((line, index) => (
          <li key={index}>{line}</li>
        ))}
      </ul>
    </Notice>
  );
}
