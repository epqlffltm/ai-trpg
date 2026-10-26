// web/apps/web/src/pages/personas/personaProblem.ts
// 페르소나를 저장하거나 지우지 못한 까닭을 폼의 모양(FormProblem)으로. 순수한 함수다. 까닭은 api/personas.ts 의 머리말을 본다.

import { ApiError } from '../../api/errors';
import { commonProblem, unknownProblem, type FormProblem } from '../../auth/problem';
import { SERVER_FIELDS } from './personaForm';

export function describePersonaProblem(error: unknown): FormProblem {
  const common = commonProblem(error);
  if (common) return common;
  const api = error as ApiError;
  if (api.code === 'persona_limit') return { message: '페르소나는 50개까지 만듭니다. 쓰지 않는 것을 지운 뒤에 만들어 주세요.' };
  if (api.code === 'image_not_owned') return { message: '내가 올린 그림만 붙일 수 있습니다. 그림을 다시 올려 주세요.', fields: { imageId: '내가 올린 그림이 아닙니다.' } };
  if (api.status === 404) return { message: '없거나 지운 페르소나입니다.' };
  if (api.status === 422 && Object.keys(api.fields).length > 0) return { message: '적은 것을 확인해 주세요.', fields: formFields(api) };
  return unknownProblem(api);
}

function formFields(error: ApiError): Record<string, string> {
  const fields: Record<string, string> = {};
  for (const [name, messages] of Object.entries(error.fields)) {
    const field = SERVER_FIELDS[name];
    if (field && messages[0]) fields[field] = messages[0];
  }
  return fields;
}
