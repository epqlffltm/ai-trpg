// web/apps/web/src/pages/attendance/ChestOdds.tsx
// 보물 상자의 확률표(A9). 결과마다 이름, 실버, 확률. 표의 판과 평균을 함께 적는다.
// 확률을 공개하는 것은 서비스의 약속이므로 서버가 준 값을 그대로 보인다(화면이 계산하지 않는다).

import type { AttendanceRewards } from '../../api/types';

export function ChestOdds({ chest }: { chest: AttendanceRewards['chest'] }) {
  return (
    <section className="page-section" aria-labelledby="chest-odds-heading">
      <h2 id="chest-odds-heading">보물 상자의 확률</h2>
      <p className="hint">
        주기의 마지막 날에 출석하면 상자를 엽니다. 확률표 {chest.table} · 평균 실버 {chest.expected_silver}
      </p>
      <table className="odds-table">
        <thead>
          <tr>
            <th scope="col">결과</th>
            <th scope="col">실버</th>
            <th scope="col">확률</th>
          </tr>
        </thead>
        <tbody>
          {chest.outcomes.map((outcome) => (
            <tr key={outcome.outcome}>
              <th scope="row">{outcome.name}</th>
              <td>{outcome.silver}</td>
              <td>{outcome.percent}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
