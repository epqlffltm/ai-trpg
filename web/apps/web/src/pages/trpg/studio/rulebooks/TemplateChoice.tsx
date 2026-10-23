// web/apps/web/src/pages/trpg/studio/rulebooks/TemplateChoice.tsx
// 만들 때 고르는 템플릿(#615). 이름, 요약, 서술의 분위기(#616), 방어 규칙, 덧붙인 말과 출처 표시를 함께 보인다.
// 만든 뒤에는 바꿀 수 없다(서버가 받지 않는다).

import { Radio } from '@ai-trpg/ui';
import type { RulebookTemplates, TemplateKey } from '../../../../api/types';
import { armorSummary, templateTone } from './rulebookView';

type Props = { templates: RulebookTemplates; selected: string; onChange: (key: TemplateKey) => void };

export function TemplateChoice({ templates, selected, onChange }: Props) {
  return (
    <fieldset className="choice-list">
      <legend>템플릿</legend>
      <p className="hint">규칙(능력치, 난이도, 부상 같은 것)은 템플릿에서 옵니다. 만든 뒤에는 템플릿을 바꿀 수 없습니다.</p>
      {templates.items.map((template) => (
        <Radio
          key={template.key}
          name="template"
          label={template.name}
          checked={selected === template.key}
          onChange={() => onChange(template.key)}
          description={
            <div className="template-choice__about">
              <p>{template.summary}</p>
              {templateTone(template) ? <p className="hint">서술의 분위기: {templateTone(template)}</p> : null}
              <p className="hint">방어: {armorSummary(template.rules.armor)}</p>
              {template.notes.map((note) => (
                <p key={note} className="hint">
                  {note}
                </p>
              ))}
              {template.attribution.map((line) => (
                <p key={line} className="hint template-attribution">
                  {line}
                </p>
              ))}
            </div>
          }
        />
      ))}
    </fieldset>
  );
}
