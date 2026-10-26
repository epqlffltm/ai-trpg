// web/apps/web/src/test/renderApp.tsx
// 앱 전체를 정한 경로에서 그린다. 읽기의 저장소는 시험마다 새로 만들고, 다시 시도하지 않게 한다.
// 이 파일을 불러오면 화면의 모듈을 모두 받아 둔다(최상위 await). 앱 전체를 그리는 시험 파일만 이 값을 치르고,
// 그 뒤의 시험은 처음 가는 화면의 모듈을 읽느라 기다리지 않는다. 처음 갈 때 받는 길 자체는 RouteBoundary.test 가 본다.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { App } from '../App';
import { preloadPages } from '../routing/lazyPage';

await preloadPages();

export function renderApp(path = '/') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
