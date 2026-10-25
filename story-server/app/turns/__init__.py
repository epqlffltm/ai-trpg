# story-server/app/turns/__init__.py

"""
한 번의 말(docs/architecture/story.md 의 "한 번의 말"). 사람의 말을 받아 장면의 인물들과 서술의 답을 흘려보낸다.

  - service.py: 말 한 번의 차례. 세션을 잡고, 사람의 말을 저장하고, 홀드를 걸고, 모델을 부르고, 답을 저장하고, 확정한다
  - segments.py: 모델의 답을 말하는 사람의 표식(@인물:, @narration:)으로 잘라 말 조각으로. 장면 밖의 인물을 버린다
  - prompt.py, briefing.py: 모델에 보낼 메시지(세계관, 지금, 장면의 인물, 쓰는 법, 최근의 말)
  - states.py: 엔진의 상태를 말에 붙여 저장하는 모양으로. 가지의 끝의 상태를 읽는다
  - charging.py, settler.py: 홀드를 걸고 확정하거나 돌려주는 것과, 못 한 것을 마저 끝내는 정리 작업
  - providers.py: 모델의 이름표로 그 모델을 부를 provider 를 고르는 것(ai_core 의 ModelRouter)
  - models.py, repository.py: 호출과 청구의 기록(generations), 차례 잡기, 말에 붙은 상태
  - router.py, schemas.py, frames.py: 말을 보내는 주소. 바로 SSE 로 답한다

chat 의 말 한 번(chat-server/app/turns/)과 같은 차례다.
함께 쓰는 것은 공용 코드 conversation_core 에 있다(창, SSE, 흘려보내기).
"""
