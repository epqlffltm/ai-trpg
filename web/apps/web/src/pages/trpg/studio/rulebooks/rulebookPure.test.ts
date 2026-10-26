// web/apps/web/src/pages/trpg/studio/rulebooks/rulebookPure.test.ts
// 룰북 화면(B9)의 순수한 함수. 처음 값(템플릿의 방어 규칙), 템플릿 바꾸기, 검사, 보내는 본문, 409 의 쓰는 시나리오, 요약 글.

import { describe, expect, it } from 'vitest';
import { ApiError } from '../../../../api/errors';
import type { RulebookDetail, RulebookTemplates } from '../../../../api/types';
import { newRulebookDraft, rulebookDraft, rulebookHints, toRulebookCreate, toRulebookUpdate, wholeNumber, withTemplate } from './rulebookForm';
import { describeDeleteProblem, describeSaveProblem, usedByTitles } from '../studioProblem';
import { armorSummary, templateDie, templateName } from './rulebookView';

function rules(template: string, armor: unknown, die = 20) {
  return { template, die, armor, abilities: [], resources: [], narration: { tone: `${template}의 분위기`, outcomes: [], avoid: [] } };
}

const TEMPLATES = {
  default: 'srd5',
  items: [
    { key: 'srd5', name: 'd20 판타지', summary: '기본', attribution: [], notes: [], rules: rules('srd5', { mode: 'ac', save_target: null, pierce_base: 10 }) },
    { key: 'horror', name: '공포', summary: '무섭다', attribution: [], notes: [], rules: rules('horror', { mode: 'reduce', save_target: null, pierce_base: 10 }, 10) },
  ],
} as unknown as RulebookTemplates;

describe('룰북의 입력', () => {
  it('처음에는 기본 템플릿과 그 방어 규칙. 템플릿을 바꾸면 방어 규칙도 그 템플릿의 것', () => {
    const draft = newRulebookDraft(TEMPLATES);
    expect(draft).toMatchObject({ template: 'srd5', armor: 'ac', pierceBase: '10', saveTarget: '' });
    const changed = withTemplate({ ...draft, title: '내 규칙', armor: 'save', saveTarget: '7' }, TEMPLATES, 'horror');
    expect(changed).toMatchObject({ title: '내 규칙', template: 'horror', armor: 'reduce', saveTarget: '' });
  });

  it('고칠 때는 지금 룰북의 것. 방어 규칙이 없으면 막지 않음', () => {
    const rulebook = { title: '룰', description: '', gm_guide: '지침', rules: rules('srd5', null) } as unknown as RulebookDetail;
    expect(rulebookDraft(rulebook)).toMatchObject({ title: '룰', gmGuide: '지침', template: 'srd5', armor: 'none', pierceBase: '10' });
    const saving = { ...rulebook, rules: rules('srd5', { mode: 'save', save_target: 7, pierce_base: 12 }) } as unknown as RulebookDetail;
    expect(rulebookDraft(saving)).toMatchObject({ armor: 'save', saveTarget: '7', pierceBase: '12' });
  });

  it('제목은 공백을 떼고 1~100자, 세이브면 목표값이, 막는 방식이면 관통 기준값이 정수여야 한다', () => {
    const draft = { ...newRulebookDraft(TEMPLATES), title: '  ' };
    expect(Object.keys(rulebookHints(draft))).toEqual(['title']);
    expect(rulebookHints({ ...draft, title: 'x'.repeat(101) }).title).toContain('100자');
    expect(Object.keys(rulebookHints({ ...draft, title: '룰', armor: 'save', saveTarget: '' }))).toEqual(['save_target']);
    expect(Object.keys(rulebookHints({ ...draft, title: '룰', pierceBase: '1.5' }))).toEqual(['pierce_base']);
    expect(rulebookHints({ ...draft, title: '룰', armor: 'none', pierceBase: '' })).toEqual({});
    expect(wholeNumber(' 7 ', 1, 1000)).toBe(7);
    expect(wholeNumber('0', 1, 1000)).toBeNull();
    expect(wholeNumber('1001', 1, 1000)).toBeNull();
  });

  it('보내는 본문. 세이브 목표값은 save 일 때만, 막지 않음이면 armor 가 null', () => {
    const draft = { ...newRulebookDraft(TEMPLATES), title: '  내 규칙 ', gmGuide: '지침' };
    expect(toRulebookCreate(draft)).toEqual({ title: '내 규칙', description: '', gm_guide: '지침', template: 'srd5', armor: { mode: 'ac', pierce_base: 10 }, resources: [] });
    expect(toRulebookUpdate({ ...draft, armor: 'save', saveTarget: '7', pierceBase: '12' }).armor).toEqual({ mode: 'save', pierce_base: 12, save_target: 7 });
    expect(toRulebookUpdate({ ...draft, armor: 'none' })).toEqual({ title: '내 규칙', description: '', gm_guide: '지침', armor: null, resources: [] });
  });
});

describe('룰북의 글', () => {
  it('방어 규칙의 요약, 템플릿의 이름과 주사위', () => {
    expect(armorSummary({ mode: 'save', save_target: 7, pierce_base: 10 })).toBe('세이브로 막음 · 목표 7 · 관통 기준 10');
    expect(armorSummary({ mode: 'ac', pierce_base: 10 })).toBe('맞히기 어렵게 · 관통 기준 10');
    expect(armorSummary(null)).toBe('방어구가 막지 않음');
    expect(templateName(TEMPLATES, 'horror')).toBe('공포');
    expect(templateName(undefined, 'srd5')).toBe('srd5');
    expect(templateDie(TEMPLATES, 'horror')).toBe(10);
  });

  it('지우지 못하면 쓰는 시나리오의 제목을 함께 적는다', () => {
    const body = { detail: 'x', used_by: [{ id: 'a', title: '안개 마을' }, { id: 'b', title: '등대' }, { id: 'c' }] };
    expect(usedByTitles(body)).toEqual(['안개 마을', '등대']);
    expect(usedByTitles({ used_by: 'x' })).toEqual([]);
    const problem = describeDeleteProblem(new ApiError({ status: 409, detail: 'x', body }), 'rulebooks');
    expect(problem.message).toContain('쓰는 시나리오: 안개 마을, 등대.');
  });

  it('규칙 한 벌로 맞지 않는 룰북(422 의 field)은 서버의 문장을 보인다', () => {
    const error = new ApiError({ status: 422, detail: '수치의 최대에 쓰는 능력치가 규칙에 없습니다.', body: { detail: '수치의 최대에 쓰는 능력치가 규칙에 없습니다.', field: 'resources' } });
    expect(describeSaveProblem(error, 'rulebooks')).toEqual({ message: '수치의 최대에 쓰는 능력치가 규칙에 없습니다.' });
    expect(describeSaveProblem(new ApiError({ status: 422, detail: 'x' }), 'rulebooks').message).toBe('서버가 받지 않는 값이 있습니다. 칸을 다시 확인해 주세요.');
  });
});
