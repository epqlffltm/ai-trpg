// web/apps/web/src/pages/settings/SettingsPage.tsx
// 설정(A12, /settings). 서버가 모르는 화면 쪽 설정: 밝기, 글자 크기, 테이블 방의 단축키. 로그인하지 않아도 열린다.
// 고르면 바로 입히고 이 브라우저에 둔다(settingsStore.ts). 저장이 막힌 브라우저면 이 창을 닫을 때까지만 둔다고 알린다.
// 선택 동의(마케팅, AI 학습)는 마이페이지(A5)에 있다. 시나리오의 테마는 대표 장르가 정해 여기서 바꾸지 않는다.

import { Button, Checkbox, Notice, Radio } from '@ai-trpg/ui';
import { Link } from 'react-router';
import { DEFAULT_SETTINGS, TEXT_SIZES, textSizeLabel, THEMES, themeLabel } from '../../settings/settings';
import { updateSettings } from '../../settings/settingsStore';
import { useSettings } from '../../settings/useSettings';

const SHORTCUTS = [
  ['C', '캐릭터'],
  ['I', '소지품'],
  ['J', '퀘스트와 장소'],
  ['L', '일어난 일'],
] as const;

export function SettingsPage() {
  const { settings, persistent } = useSettings();
  return (
    <main className="page page--medium">
      <h1>설정</h1>
      <p className="hint">
        이 브라우저에만 적용됩니다. 선택 동의(마케팅 정보, AI 학습)는 <Link to="/me">내 정보</Link>에서 바꿉니다.
      </p>
      {persistent ? null : <Notice>이 브라우저는 저장을 막고 있어 창을 닫으면 설정이 처음으로 돌아갑니다.</Notice>}
      <fieldset className="page-section scenario-choices">
        <legend>밝기</legend>
        {THEMES.map((theme) => (
          <Radio key={theme} name="theme" label={themeLabel(theme)} checked={settings.theme === theme} onChange={() => updateSettings({ theme })} />
        ))}
      </fieldset>
      <fieldset className="page-section scenario-choices">
        <legend>글자 크기</legend>
        {TEXT_SIZES.map((size) => (
          <Radio key={size} name="text-size" label={textSizeLabel(size)} checked={settings.textSize === size} onChange={() => updateSettings({ textSize: size })} />
        ))}
      </fieldset>
      <section className="page-section settings-shortcuts" aria-labelledby="shortcuts-heading">
        <h2 id="shortcuts-heading">단축키</h2>
        <Checkbox
          label="테이블 방에서 단축키 쓰기"
          description="글을 쓰는 칸에 있을 때와 Ctrl, Alt 를 함께 누를 때는 단축키로 보지 않습니다."
          checked={settings.shortcuts}
          onChange={(event) => updateSettings({ shortcuts: event.target.checked })}
        />
        <table className="shortcut-table">
          <caption className="hint">상태 패널의 탭</caption>
          <tbody>
            {SHORTCUTS.map(([key, name]) => (
              <tr key={key}>
                <th scope="row">
                  <kbd>{key}</kbd>
                </th>
                <td>{name}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <p>
        <Button variant="secondary" onClick={() => updateSettings(DEFAULT_SETTINGS)}>
          처음으로 되돌리기
        </Button>
      </p>
    </main>
  );
}
