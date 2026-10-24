# story-server/app/engine/__init__.py

"""
story 의 엔진. 판(세계관의 문서)과 지금의 상태만 보고 정하는 순수 함수들이다. DB 와 모델(LLM)을 모른다.

결과는 엔진이 정하고 말은 모델이 쓴다(docs/architecture/story.md 의 "한눈에").
지금은 조건 맞추기(conditions.py)와 장면의 인물(scene.py)이 있다. 시각, 효과, 고백과 엔딩이 차례로 붙는다.
"""
