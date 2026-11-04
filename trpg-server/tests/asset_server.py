# trpg-server/tests/asset_server.py

"""
가짜 asset 서버(app/asset_server/client.py 의 AssetClient 자리). 장면 그림(#983)을 맡기고 내주고 지운다.

맡긴 그림은 kept 에(그림의 id → 바이트), 그 그림을 맡긴 토큰은 owners 에 남는다. 지운 것은 discarded 에 남는다.
down 이면 모든 요청이 AssetUnavailableError 다. kept 에 없는 그림은 404(AssetNotFoundError)다.
"""

import uuid
from dataclasses import dataclass, field

from app.asset_server.client import AssetNotFoundError, AssetUnavailableError, ImageContent

MIME_TYPE = 'image/png'


@dataclass
class FakeAsset:
    """가짜 asset 서버."""

    kept: dict[uuid.UUID, bytes] = field(default_factory=dict)
    owners: dict[uuid.UUID, str] = field(default_factory=dict)
    discarded: list[uuid.UUID] = field(default_factory=list)
    down: bool = False

    def require_up(self) -> None:
        if self.down:
            raise AssetUnavailableError('asset 서버가 죽었다(테스트)')

    async def keep_image(self, token: str, data: bytes) -> uuid.UUID:
        self.require_up()
        image_id = uuid.uuid4()
        self.kept[image_id] = data
        self.owners[image_id] = token
        return image_id

    async def fetch_kept(self, image_id: uuid.UUID) -> ImageContent:
        self.require_up()
        if image_id not in self.kept:
            raise AssetNotFoundError
        return ImageContent(data=self.kept[image_id], mime_type=MIME_TYPE)

    async def discard_image(self, token: str, image_id: uuid.UUID) -> None:
        self.require_up()
        self.kept.pop(image_id, None)
        self.discarded.append(image_id)
