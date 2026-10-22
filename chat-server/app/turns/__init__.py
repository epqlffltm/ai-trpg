# chat-server/app/turns/__init__.py

"""
한 번의 말(docs/architecture/chat-server.md 의 "한 번의 말이 지나가는 길"). 사람의 말을 받아 모델의 답을 흘려보낸다.

  - service.py: 말 한 번의 차례. 대화를 잡고, 사람의 말을 저장하고, 홀드를 걸고, 모델을 부르고, 답을 저장하고, 확정한다
  - prompt.py: 모델에 보낼 메시지(캐릭터의 판, 페르소나, 시작 상황, 최근 대화)
  - charging.py: 홀드를 걸고 확정하거나 돌려주는 것(결제 서버의 답을 이 서버의 상태로)
  - settler.py: 확정이나 반환을 못 한 청구를 몇 초마다 마저 끝내는 정리 작업
  - providers.py: 모델의 이름표로 그 모델을 부를 provider 를 고르는 것(ai_core 의 ModelRouter)
  - models.py, repository.py: 호출과 청구의 기록(generations)
  - router.py, schemas.py: 말을 보내는 주소. 바로 SSE 로 답한다

대화의 트리와 프롬프트를 붙이는 일 가운데 chat 과 story 가 함께 쓸 것은 app/conversation/ 에 있다(창, SSE, 흘려보내기).
"""
