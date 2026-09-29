"""좌표 변환·거리 계산 유틸리티.

VAL-11: 외부 소스 좌표는 저장 전 WGS84(EPSG:4326)로 변환한다. 지방행정 인허가 데이터는
EPSG:5174(보정계수 미적용 Bessel 중부원점 TM)로 제공된다.
PostGIS를 쓰지 않으므로(2-prd.md 10장 미해결 이슈 11) 반경 검색은 위경도 박스 + 하버사인으로 한다.
"""

from __future__ import annotations

import math
from functools import lru_cache

from pyproj import Transformer

WGS84 = "EPSG:4326"
PERMIT_SOURCE_CRS = "EPSG:5174"
EARTH_RADIUS_KM = 6371.0088

# 대한민국 영역(대략). 변환 결과가 이 밖이면 좌표 오류로 보고 저장하지 않는다.
_KOREA_LAT = (33.0, 38.9)
_KOREA_LNG = (124.5, 131.9)


@lru_cache(maxsize=8)
def _transformer(source_crs: str) -> Transformer:
    # always_xy=True: 입력 (x=동향, y=북향), 출력 (lng, lat) 순서를 고정한다.
    return Transformer.from_crs(source_crs, WGS84, always_xy=True)


def to_wgs84(x: float, y: float, source_crs: str = PERMIT_SOURCE_CRS) -> tuple[float, float] | None:
    """원본 좌표를 WGS84 (lat, lng)로 변환한다. 변환 결과가 국내 범위를 벗어나면 None."""
    if source_crs.upper() == WGS84:
        lng, lat = x, y
    else:
        lng, lat = _transformer(source_crs.upper()).transform(x, y)
    if not (_KOREA_LAT[0] <= lat <= _KOREA_LAT[1] and _KOREA_LNG[0] <= lng <= _KOREA_LNG[1]):
        return None
    return round(lat, 7), round(lng, 7)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bounding_box(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    """(min_lat, max_lat, min_lng, max_lng) — SQL 1차 필터용. 정밀 판정은 haversine_km으로 한다."""
    d_lat = radius_km / 111.32
    d_lng = radius_km / (111.32 * max(math.cos(math.radians(lat)), 1e-6))
    return lat - d_lat, lat + d_lat, lng - d_lng, lng + d_lng


# 주소 첫 토큰 → 시도 약칭. 기상특보 관서·유가 시도코드 매핑에 쓴다.
_SIDO_ALIASES: dict[str, str] = {
    "서울": "서울", "서울특별시": "서울", "서울시": "서울",
    "부산": "부산", "부산광역시": "부산",
    "대구": "대구", "대구광역시": "대구",
    "인천": "인천", "인천광역시": "인천",
    "광주": "광주", "광주광역시": "광주",
    "대전": "대전", "대전광역시": "대전",
    "울산": "울산", "울산광역시": "울산",
    "세종": "세종", "세종특별자치시": "세종",
    "경기": "경기", "경기도": "경기",
    "강원": "강원", "강원도": "강원", "강원특별자치도": "강원",
    "충북": "충북", "충청북도": "충북",
    "충남": "충남", "충청남도": "충남",
    "전북": "전북", "전라북도": "전북", "전북특별자치도": "전북",
    "전남": "전남", "전라남도": "전남",
    "경북": "경북", "경상북도": "경북",
    "경남": "경남", "경상남도": "경남",
    "제주": "제주", "제주도": "제주", "제주특별자치도": "제주",
}


def extract_sido(address: str | None) -> str | None:
    if not address:
        return None
    first = address.strip().split()[0] if address.strip() else ""
    return _SIDO_ALIASES.get(first)
