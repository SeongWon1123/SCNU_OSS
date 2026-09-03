"""S3 업로드 옵션 — SPEC.md §4.2. S3_BUCKET이 비어 있으면 스킵.

boto3는 Phase 6(투두 18, 배포 준비) 전까지 의존성에 추가하지 않는다 — 계획 ⑥에
사유를 기재했다. S3_BUCKET이 설정된 경우 현재 단계에서는 NotImplementedError로
상향하고, pipeline의 upload 단계가 이를 받아 스캔을 계속한다(절대규칙 5).
"""


def upload(scan_id: str, files: dict[str, str]) -> None:
    """스캔 산출물(방침·고지 등)을 S3로 업로드한다.

    S3_BUCKET 미설정 → no-op(스킵). 설정됨 + boto3 미탑재 → NotImplementedError
    (Phase 6에서 boto3와 함께 연결).
    """
    from app.config import Settings

    if not Settings().s3_bucket:
        return
    raise NotImplementedError("S3 업로드는 Phase 6에서 boto3와 함께 연결됩니다(계획 ⑥)")
