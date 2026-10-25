// web/apps/web/src/components/saveFile.ts
// 받은 파일(Blob)을 이름을 붙여 내려받게 한다. 화면 안의 링크를 잠깐 만들어 누르고 지운다.
// 주소(object URL)는 내려받기가 시작된 뒤에 놓는다.

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.rel = 'noopener';
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
