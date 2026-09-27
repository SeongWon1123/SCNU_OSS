import { loadTossPayments } from "@tosspayments/payment-sdk";

const toss = loadTossPayments("test_ck_demo");
export async function checkout(orderId, amount) {
  return toss.requestPayment("카드", { orderId, amount, orderName: "달고나 10개" });
}
