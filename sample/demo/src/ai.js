import OpenAI from "openai";

const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
export async function describeGoods(name) {
  const r = await client.chat.completions.create({
    model: "demo-model",
    messages: [{ role: "user", content: `${name} 상품 설명을 써줘` }],
  });
  return r.choices[0].message.content;
}
