// web/apps/web/src/pages/personas/personaForm.ts
// 페르소나 폼의 값과 검사, 보낼 본문. 순수한 함수다. 상한은 asset 서버(PersonaCreate)와 같다.
// 이름만 꼭 적는다. 나머지는 비워도 된다. 나이와 성별은 적어 두는 글이고 서버도 화면도 거르지 않는다.

import type { Persona, PersonaCreate } from '../../api/types';

export type PersonaDraft = {
  name: string;
  formOfAddress: string;
  age: string;
  gender: string;
  description: string;
  personality: string;
  speechExamples: string;
  imageId: string | null;
};

type TextField = Exclude<keyof PersonaDraft, 'imageId'>;

/** 칸마다의 글자 수 상한 */
export const PERSONA_LIMITS: Record<TextField, number> = {
  name: 50,
  formOfAddress: 30,
  age: 20,
  gender: 20,
  description: 1000,
  personality: 1000,
  speechExamples: 1000,
};

export const EMPTY_PERSONA: PersonaDraft = { name: '', formOfAddress: '', age: '', gender: '', description: '', personality: '', speechExamples: '', imageId: null };

export function draftOf(persona: Persona): PersonaDraft {
  return {
    name: persona.name,
    formOfAddress: persona.form_of_address,
    age: persona.age,
    gender: persona.gender,
    description: persona.description,
    personality: persona.personality,
    speechExamples: persona.speech_examples,
    imageId: persona.image_id,
  };
}

/** 칸마다의 문제. 없으면 빈 객체. 길이는 서버처럼 앞뒤 공백을 뗀 이름으로 본다 */
export function draftProblems(draft: PersonaDraft): Partial<Record<TextField, string>> {
  const problems: Partial<Record<TextField, string>> = {};
  if (draft.name.trim() === '') problems.name = '이름을 적어 주세요.';
  for (const field of Object.keys(PERSONA_LIMITS) as TextField[]) {
    const value = field === 'name' ? draft.name.trim() : draft[field];
    if (value.length > PERSONA_LIMITS[field]) problems[field] = `${PERSONA_LIMITS[field]}자까지입니다.`;
  }
  return problems;
}

/** 보낼 본문. 만들기와 고치기가 같다(고치기는 모든 칸을 보내고, 바뀌지 않은 칸은 서버가 revision 을 올리지 않는다) */
export function personaBody(draft: PersonaDraft): Required<PersonaCreate> {
  return {
    name: draft.name.trim(),
    form_of_address: draft.formOfAddress.trim(),
    age: draft.age.trim(),
    gender: draft.gender.trim(),
    description: draft.description,
    personality: draft.personality,
    speech_examples: draft.speechExamples,
    image_id: draft.imageId,
  };
}

/** 서버의 칸 이름 → 폼의 칸 이름 */
export const SERVER_FIELDS: Record<string, TextField | 'imageId'> = {
  name: 'name',
  form_of_address: 'formOfAddress',
  age: 'age',
  gender: 'gender',
  description: 'description',
  personality: 'personality',
  speech_examples: 'speechExamples',
  image_id: 'imageId',
};
