# story-server/app/engine/__init__.py

"""
story 의 엔진. 판(세계관의 문서)과 지금의 상태만 보고 정하는 순수 함수들이다. DB 와 모델(LLM)을 모른다.

결과는 엔진이 정하고 말은 모델이 쓴다(docs/architecture/story.md 의 "한눈에").
시각의 셈(clock.py), 시각을 흘리는 행동(actions.py), 조건 맞추기(conditions.py), 장면의 인물(scene.py),
효과(effects.py), 이벤트와 선택지(events.py), 고백(confession.py), 엔딩의 판정(endings.py)이 있다.
세션과 말에 붙이는 일(행동을 받고 상태를 저장하는 것)은 말을 주고받는 조각에서 한다.
"""
