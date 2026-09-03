"""정규식 픽스처 테스트 — 패턴 리터럴만 다룹니다."""

import re

ORDER_ID_PATTERN = re.compile(r"^ORD-[A-Z0-9]+$")
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def test_order_id_pattern_matches():
    assert ORDER_ID_PATTERN.fullmatch("ORD-FAKE-0001") is not None


def test_order_id_pattern_rejects_lowercase():
    assert ORDER_ID_PATTERN.fullmatch("ord-abc") is None


def test_slug_pattern_matches():
    assert SLUG_PATTERN.fullmatch("my-first-post") is not None


def test_slug_pattern_rejects_double_hyphen():
    assert SLUG_PATTERN.fullmatch("my--post") is None
