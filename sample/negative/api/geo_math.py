"""지구 표면 두 지점 사이의 거리를 계산하는 순수 수학 유틸리티.

지도 SDK, 브라우저 위치 API, 외부 서비스 호출이 전혀 없는
삼각함수 기반 계산 모듈입니다. 입력은 도(degree) 단위 숫자 값입니다.
"""

import math

EARTH_RADIUS_KM = 6371.0088


def to_radians(deg: float) -> float:
    return math.radians(deg)


def haversine_distance_km(
    latitude_deg_a: float,
    longitude_deg_a: float,
    latitude_deg_b: float,
    longitude_deg_b: float,
) -> float:
    """두 지점 사이의 대원 거리를 킬로미터 단위로 반환합니다."""
    phi_a = to_radians(latitude_deg_a)
    phi_b = to_radians(latitude_deg_b)
    delta_phi = to_radians(latitude_deg_b - latitude_deg_a)
    delta_lambda = to_radians(longitude_deg_b - longitude_deg_a)

    h = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def bearing_deg(
    latitude_deg_a: float,
    longitude_deg_a: float,
    latitude_deg_b: float,
    longitude_deg_b: float,
) -> float:
    """A에서 B를 바라보는 방위각을 도 단위(0 이상 360 미만)로 반환합니다."""
    phi_a = to_radians(latitude_deg_a)
    phi_b = to_radians(latitude_deg_b)
    delta_lambda = to_radians(longitude_deg_b - longitude_deg_a)

    y = math.sin(delta_lambda) * math.cos(phi_b)
    x = math.cos(phi_a) * math.sin(phi_b) - math.sin(phi_a) * math.cos(phi_b) * math.cos(
        delta_lambda
    )
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
