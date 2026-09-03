import { useState } from "react";

const PLANS = [
  { id: "basic", label: "베이직", monthly: 9900, features: ["기본 리포트", "월 5회 진단"] },
  { id: "pro", label: "프로", monthly: 19900, features: ["상세 리포트", "무제한 진단"] },
];

function formatKrw(amount: number): string {
  return `${amount.toLocaleString("ko-KR")}원`;
}

export default function PriceTable() {
  const [selected, setSelected] = useState("basic");

  return (
    <table>
      <caption>요금제 안내 (표시용 가격표입니다)</caption>
      <thead>
        <tr>
          <th scope="col">플랜</th>
          <th scope="col">월 이용료</th>
          <th scope="col">제공 항목</th>
          <th scope="col">선택</th>
        </tr>
      </thead>
      <tbody>
        {PLANS.map((plan) => (
          <tr key={plan.id}>
            <td>{plan.label}</td>
            <td>{formatKrw(plan.monthly)}</td>
            <td>{plan.features.join(", ")}</td>
            <td>
              <label>
                <input
                  type="radio"
                  name="plan"
                  checked={selected === plan.id}
                  onChange={() => setSelected(plan.id)}
                />
                선택
              </label>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
