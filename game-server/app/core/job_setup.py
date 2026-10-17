# game-server/app/core/job_setup.py

"""
뒤에서 도는 작업의 한도를 설정으로 정해 작업 관리자를 만든다(#275). 앱이 뜰 때 한 번 부른다(app/main.py).

종류(operation)의 이름과 기다리는 줄의 상한은 그 작업을 맡기는 곳에 있다. 동시에 도는 수만 설정에서 온다.
모델이 한 번에 받는 수는 어디서 돌리느냐(로컬 Ollama, 외부 API)에 따라 달라서다.
"""

from app.core.config import Settings
from app.core.jobs import BackgroundJobs, Limit
from app.lore import indexing as lore_indexing
from app.memory import indexing as memory_indexing
from app.rounds import closing


def job_limits(settings: Settings) -> dict[str, Limit]:
    """종류마다의 한도. 서술, 로어북 색인, 기억 색인이다. 그 밖의 종류는 작업 관리자의 기본 한도를 쓴다."""
    index = settings.job_index_concurrency
    return {
        closing.NARRATE_OPERATION: Limit(settings.job_narration_concurrency, closing.NARRATION_CAPACITY),
        lore_indexing.INDEX_OPERATION: Limit(index, lore_indexing.INDEX_CAPACITY),
        memory_indexing.INDEX_OPERATION: Limit(index, memory_indexing.INDEX_CAPACITY),
    }


def build_jobs(settings: Settings) -> BackgroundJobs:
    """설정의 한도를 단 작업 관리자."""
    return BackgroundJobs(job_limits(settings))
