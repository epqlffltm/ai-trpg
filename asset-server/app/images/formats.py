# asset-server/app/images/formats.py

"""
받는 그림의 형식(#566). PNG, JPEG, WebP 셋이다.

형식은 확장자나 요청의 Content-Type 이 아니라 파일의 머리(첫 몇 바이트)로 본다. 둘 다 보내는 쪽이 마음대로 적는다.
머리로 고른 형식은 디코더가 연 형식과도 같아야 한다(app/images/decoder.py). 머리만 흉내 낸 파일은 거기서 걸린다.
"""

import enum


class ImageFormat(enum.StrEnum):
    """받는 형식. 값은 표(images.format)에 적는 이름이다."""

    PNG = 'png'
    JPEG = 'jpeg'
    WEBP = 'webp'


# 저장소의 객체에 적고 nginx 가 그대로 내보내는 형식(Content-Type)
CONTENT_TYPES = {
    ImageFormat.PNG: 'image/png',
    ImageFormat.JPEG: 'image/jpeg',
    ImageFormat.WEBP: 'image/webp',
}

PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
JPEG_SIGNATURE = b'\xff\xd8\xff'


def check_image_header(head: bytes) -> ImageFormat | None:
    """파일의 머리로 형식을 고른다. 받는 형식이 아니면 None."""
    if head.startswith(PNG_SIGNATURE):
        return ImageFormat.PNG
    if head.startswith(JPEG_SIGNATURE):
        return ImageFormat.JPEG
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return ImageFormat.WEBP
    return None
