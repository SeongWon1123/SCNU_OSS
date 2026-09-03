// 애플리케이션 로거 — 문자열 메시지만 출력합니다.
function logInfo(message) {
  console.log(`[info] ${new Date().toISOString()} ${message}`);
}

function logWarn(message) {
  console.log(`[warn] ${new Date().toISOString()} ${message}`);
}

function main() {
  logInfo("애플리케이션을 시작합니다.");
  logInfo("설정 파일을 읽었습니다.");
  logWarn("캐시 디렉터리가 비어 있어 기본값을 사용합니다.");
  logInfo("예약 작업을 등록했습니다.");
  logInfo("애플리케이션을 정상 종료합니다.");
}

main();
