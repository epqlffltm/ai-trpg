# game-server/app/drafts/__init__.py

"""
장부 초안. 서술한 장면에서 "물건을 손에 넣었다", "퀘스트가 이루어졌다"를 구조화한 데이터로 뽑는다.

AI 는 상태를 바꾸지 못한다. 초안은 서버가 검증하고, 방장이 받아들여야 상태가 된다.
  - output.py: 모델의 답(JSON)의 모양과 읽기
  - context.py: 모델에게 보일 목록과 짧은 이름표(p1, i1, q1)
  - validation.py: 답을 테이블의 지금 상태에 대어 받을 것과 버릴 것을 가른다
  - prompt.py: 모델에게 줄 메시지
  - writer.py: 모델을 부르고, 읽고, 검증하고, 기록한다
  - models.py, records.py, repository.py: 검증을 거친 초안을 줄로 적고 읽는다
  - drafting.py: 서술이 끝난 뒤에 테이블을 읽고, 쓰고, 적는다(app/rounds/closing.py 가 부른다)
  - setup.py: 설정을 보고 초안을 쓸 것을 고른다
  - router.py, schemas.py: 방장이 기다리는 줄을 보는 API
"""
