// web/apps/web/src/routing/lazyPage.ts
// 화면 하나를 처음 갈 때 받도록(React.lazy) 감싼다. 화면 파일은 이름 붙은 내보내기(export function XxxPage)라서
// lazy 가 바라는 기본 내보내기(default)로 바꿔 준다. 받는 동안은 AppLayout 의 Suspense 가, 받지 못하면 RouteBoundary 가 맡는다.

import { lazy, type ComponentType, type LazyExoticComponent } from 'react';

// 화면은 경로의 element 로만 쓴다. 받는 props 가 없다
type Page = ComponentType<Record<string, never>>;

/** load 가 돌려주는 모듈에서 name 의 화면을 꺼내 lazy 로 감싼다 */
export function lazyPage<M extends Record<K, Page>, K extends keyof M & string>(
  load: () => Promise<M>,
  name: K,
): LazyExoticComponent<Page> {
  return lazy(async () => ({ default: (await load())[name] }));
}
