// web/apps/web/src/routing/lazyPage.ts
// 화면 하나를 처음 갈 때 받도록(React.lazy) 감싼다. 화면 파일은 이름 붙은 내보내기(export function XxxPage)라서
// lazy 가 바라는 기본 내보내기(default)로 바꿔 준다. 받는 동안은 AppLayout 의 Suspense 가, 받지 못하면 RouteBoundary 가 맡는다.
// 받는 함수는 목록에 모아 둔다. 시험은 그리기 전에 모두 받아 둔다(preloadPages, test/renderApp.tsx). 앱은 부르지 않는다.

import { lazy, type ComponentType, type LazyExoticComponent } from 'react';

// 화면은 경로의 element 로만 쓴다. 받는 props 가 없다
type Page = ComponentType<Record<string, never>>;

// 만든 화면들의 받는 함수. 같은 모듈을 다시 부르면 모듈의 캐시에서 바로 온다
const loaders: (() => Promise<unknown>)[] = [];

/** load 가 돌려주는 모듈에서 name 의 화면을 꺼내 lazy 로 감싼다 */
export function lazyPage<M extends Record<K, Page>, K extends keyof M & string>(
  load: () => Promise<M>,
  name: K,
): LazyExoticComponent<Page> {
  loaders.push(load);
  return lazy(async () => ({ default: (await load())[name] }));
}

/**
 * 만든 화면의 모듈을 모두 받아 둔다. 그 뒤에는 처음 그릴 때도 모듈을 읽느라 기다리지 않는다.
 * 시험이 시간을 걸고 기다리는 동안(findBy) 큰 화면의 모듈을 처음 읽다 시간을 넘기던 것(#827)을 없앤다
 */
export async function preloadPages(): Promise<void> {
  await Promise.all(loaders.map((load) => load()));
}
