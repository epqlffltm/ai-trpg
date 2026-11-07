// web/apps/web/src/genres/genreTheme.test.tsx
// 장르 테마(Stitch 23~33번): 아는 장르만 data-genre 로 달고, 장르마다 라이트·다크(기기 설정과 고정) 색과 모양이 모두 있으며, 소개 화면의 main 이 단다.

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../api/refresh';
import { installFakeFetch, json } from '../test/fakeFetch';
import { renderApp } from '../test/renderApp';
import { genreTheme } from './genreTheme';
import { GENRE_VALUES } from './genres';

const themes = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'genreThemes.css'), 'utf8');
const WORLD = '00000000-0000-4000-8000-00000000b801';

describe('장르 테마', () => {
  it('아는 장르만 고르고, 모르거나 없으면 테마가 없다', () => {
    expect(genreTheme('horror')).toBe('horror');
    expect(genreTheme('slice_of_life')).toBe('slice_of_life');
    expect(genreTheme('cooking')).toBeUndefined();
    expect(genreTheme('')).toBeUndefined();
    expect(genreTheme(null)).toBeUndefined();
    expect(genreTheme(undefined)).toBeUndefined();
  });

  it('장르마다 라이트, 기기의 다크, 고정한 다크의 색과 모양(무늬, 칸의 테) 한 벌이 있다', () => {
    for (const genre of GENRE_VALUES) {
      expect(themes.match(new RegExp(`\\[data-genre='${genre}'\\] \\{`, 'g'))?.length, genre).toBe(4);
      const shape = themes.slice(themes.lastIndexOf(`[data-genre='${genre}'] {`));
      expect(shape.slice(0, shape.indexOf('}')), genre).toMatch(/--genre-pattern:[\s\S]*--genre-card-border:/);
    }
  });

  it('세계관 소개의 main 이 그 세계관의 장르를 단다', async () => {
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
      [`GET /api/v1/asset/listings/worlds/${WORLD}`]: () =>
        json(200, {
          id: WORLD,
          version: 1,
          name: '달빛 고도',
          image_id: null,
          rating: 'all',
          genre: 'horror',
          tags: [],
          deadline_days: 100,
          published_at: '2026-10-26T00:00:00Z',
          creator_id: 'c',
          heart_count: 0,
          start_count: 0,
          intro_html: '',
          after_ending: 'epilogue',
          ending_count: 1,
          cast: [],
        }),
      'GET /api/v1/auth/public-names': () => json(200, { names: [] }),
    });
    renderApp(`/story/worlds/${WORLD}`);

    expect(await screen.findByRole('heading', { level: 1, name: '달빛 고도' })).toBeInTheDocument();
    expect(screen.getByRole('main')).toHaveAttribute('data-genre', 'horror');
  });
});
