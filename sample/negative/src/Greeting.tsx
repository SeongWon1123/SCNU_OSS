import { useState } from "react";

const EMAIL_PLACEHOLDER = "이메일 주소를 입력하세요";

export default function Greeting() {
  const [name, setName] = useState("");

  return (
    <section>
      <h2>환영합니다</h2>
      <p>아래에 이름을 적고 인사를 남겨 보세요.</p>
      <input
        type="text"
        value={name}
        placeholder={EMAIL_PLACEHOLDER}
        onChange={(event) => setName(event.target.value)}
      />
      <p>{name ? `${name}님, 반갑습니다!` : "아직 이름이 비어 있습니다."}</p>
    </section>
  );
}
