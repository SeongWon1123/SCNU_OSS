export async function checkoutByTransfer(orderId, amount) {
  return guideBankTransfer({
    bank: "데모은행",
    account: "000-00-000000",
    amount,
    orderId,
    note: "PG 대신 계좌이체로만 받기로 했습니다 (통신판매 신고는 별도 확인)",
  });
}
