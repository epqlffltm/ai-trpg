# asset-server/app/images/decoder.py

"""
올린 그림을 여는 따로 된 프로세스(#566). 서버가 이 파일을 python -I 로 돌린다(app/images/isolation.py).

    python -I decoder.py <형식> <최대 픽셀> <메모리 바이트> <CPU 초>
    표준 입력: 올린 파일의 바이트
    표준 출력: 첫 줄에 {"width": .., "height": ..} 와 줄바꿈, 그 뒤에 다시 인코딩한 그림의 바이트
    끝내는 번호: 0 이면 됐다. 그 밖은 열 수 없는 그림이다(까닭은 나누지 않는다)

따로 두는 까닭: 망가진 파일이나 압축 폭탄(작은 파일이 풀면 수십 GB)이 서버의 프로세스를 쓰러뜨리지 않게 한다.
  - 메모리(주소 공간)와 CPU 시간의 상한을 이 프로세스가 맨 처음 스스로 건다. 넘으면 MemoryError 나 SIGXCPU 로 끝난다.
    서버는 벽시계의 상한도 따로 걸고 넘으면 죽인다(입력을 기다리며 멈춘 경우).
  - 픽셀 수의 상한을 Pillow 에도 건다. 넘는 그림은 풀기 전에 거절한다.
  - 다시 인코딩한다. 위치 정보(EXIF) 같은 메타데이터와 그림 뒤에 붙여 숨긴 바이트가 없어진다.
    방향(EXIF orientation)은 지우기 전에 픽셀에 적용한다. 지우기만 하면 돌아간 사진이 된다.
  - 움직이는 그림(애니메이션 WebP, APNG)은 첫 장만 남긴다(유저 결정, 2026-10-22).

-I 로 돌아서 서버의 코드(app.*)와 현재 폴더를 가져오지 않는다. 표준 라이브러리와 Pillow 만 쓴다.
"""

import io
import json
import resource
import sys
import warnings

# Pillow 가 연 형식의 이름. 서버의 형식 이름(app/images/formats.py 의 ImageFormat)과 짝이다
PILLOW_FORMATS = {'png': 'PNG', 'jpeg': 'JPEG', 'webp': 'WEBP'}
# 손실 압축 형식의 품질. 다시 인코딩해도 눈에 띄게 나빠지지 않는 값이다
LOSSY_QUALITY = 90
# JPEG 이 받는 색의 방식. 나머지(CMYK, 투명이 있는 것)는 RGB 로 바꾼다
JPEG_MODES = frozenset({'RGB', 'L'})


def limit_resources(memory_bytes: int, cpu_seconds: int) -> None:
    """이 프로세스의 주소 공간과 CPU 시간에 상한을 건다. 그림을 열기 전에 부른다."""
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))


def open_image(data: bytes, expected: str, max_pixels: int):
    """
    그림을 열고 픽셀을 읽는다. 형식이 다르면 ValueError, 픽셀이 상한을 넘으면 Pillow 의 DecompressionBombError 다.

    픽셀 수는 Pillow 가 머리만 읽고(풀기 전에) 본다.
    """
    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = max_pixels
    # 상한을 넘으면 Pillow 는 경고만 한다(두 배를 넘어야 오류다). 경고도 오류로 친다
    warnings.simplefilter('error', Image.DecompressionBombWarning)
    image = Image.open(io.BytesIO(data))
    if image.format != PILLOW_FORMATS[expected]:
        raise ValueError('형식이 머리와 다르다')
    image.load()
    return ImageOps.exif_transpose(image)


def encode(image, expected: str) -> bytes:
    """메타데이터 없이 다시 인코딩한다. 움직이는 그림은 지금 장(첫 장)만 남는다."""
    # 저장할 때 Pillow 가 info 의 것(EXIF, ICC, 글 조각)을 다시 쓰는 형식이 있다. 비우고 저장한다
    image.info.clear()
    output = io.BytesIO()
    if expected == 'jpeg':
        rgb = image if image.mode in JPEG_MODES else image.convert('RGB')
        rgb.save(output, format='JPEG', quality=LOSSY_QUALITY)
    elif expected == 'webp':
        image.save(output, format='WEBP', quality=LOSSY_QUALITY)
    else:
        image.save(output, format='PNG')
    return output.getvalue()


def main(argv: list[str]) -> int:
    """표준 입력의 그림을 열고 다시 인코딩해 표준 출력에 쓴다. 끝낼 번호를 돌려준다."""
    expected, max_pixels, memory_bytes, cpu_seconds = argv[0], int(argv[1]), int(argv[2]), int(argv[3])
    limit_resources(memory_bytes, cpu_seconds)
    data = sys.stdin.buffer.read()
    try:
        image = open_image(data, expected, max_pixels)
        encoded = encode(image, expected)
    except Exception:  # noqa: BLE001 — 어떤 까닭이든 "열 수 없는 그림"이다. 서버에 까닭을 넘기지 않는다
        return 1
    header = json.dumps({'width': image.width, 'height': image.height})
    sys.stdout.buffer.write(header.encode() + b'\n' + encoded)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
