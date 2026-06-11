"""
Geographic coherence: real coordinates, real distances, real travel times.

Synthetic route tables are a classic fake-data giveaway: "Chicago →
San Diego, 145.6 km" or a 61 km hop that takes 8.3 hours. Distances between
named places are not a distribution to sample — they are facts. This module
makes them facts:

    distance_km   = haversine(origin, destination) × circuity factor
    travel_hours  = distance / effective speed + handling overhead

Both are deterministic given the city pair, so the Oracle layer can verify
them exactly. Cities without known coordinates are left untouched
(conservative-rule convention).
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np

from misata.vocab_seeds import CITY_GEODATA

# Roads are not great circles. Empirical road-network circuity averages ~1.2–1.4
# (Ballou et al., transport-geography literature); we use 1.25.
ROAD_CIRCUITY = 1.25

# Effective long-haul ground speed including stops/rest, plus fixed
# pickup/handling overhead.
EFFECTIVE_SPEED_KMH = 65.0
HANDLING_OVERHEAD_H = 0.75

# Coordinates for every city Misata's vocab pools can emit. Base layer comes
# from CITY_GEODATA (city, lat, lng, postal_prefix, country_code); the
# supplement covers pool cities missing from it.
_SUPPLEMENT: Dict[str, Tuple[float, float]] = {
    # United States (pool cities absent from CITY_GEODATA)
    "Fort Worth": (32.7555, -97.3308),
    "Jacksonville": (30.3322, -81.6557),
    "Columbus": (39.9612, -82.9988),
    "Charlotte": (35.2271, -80.8431),
    "Indianapolis": (39.7684, -86.1581),
    "El Paso": (31.7619, -106.4850),
    "Nashville": (36.1627, -86.7816),
    "Las Vegas": (36.1699, -115.1398),
    "Memphis": (35.1495, -90.0490),
    "Louisville": (38.2527, -85.7585),
    "Baltimore": (39.2904, -76.6122),
    "Milwaukee": (43.0389, -87.9065),
    "Albuquerque": (35.0844, -106.6504),
    "Tucson": (32.2226, -110.9747),
    "Washington": (38.9072, -77.0369),
    # United Kingdom
    "Glasgow": (55.8642, -4.2518),
    "Sheffield": (53.3811, -1.4701),
    "Bradford": (53.7960, -1.7594),
    "Liverpool": (53.4084, -2.9916),
    "Cardiff": (51.4816, -3.1791),
    "Coventry": (52.4068, -1.5197),
    "Nottingham": (52.9548, -1.1581),
    "Leicester": (52.6369, -1.1398),
    "Sunderland": (54.9069, -1.3838),
    "Belfast": (54.5973, -5.9301),
    "Newcastle": (54.9783, -1.6178),
    "Brighton": (50.8225, -0.1372),
    "Plymouth": (50.3755, -4.1427),
    "Wolverhampton": (52.5870, -2.1288),
    # Canada
    "Edmonton": (53.5461, -113.4938),
    "Ottawa": (45.4215, -75.6972),
    "Winnipeg": (49.8951, -97.1384),
    "Quebec City": (46.8139, -71.2080),
    "Hamilton": (43.2557, -79.8711),
    "Kitchener": (43.4516, -80.4925),
    "Victoria": (48.4284, -123.3656),
    "Halifax": (44.6488, -63.5752),
    "Oshawa": (43.8971, -78.8658),
    "Windsor": (42.3149, -83.0364),
    "Saskatoon": (52.1332, -106.6700),
    "Regina": (50.4452, -104.6189),
    "Sherbrooke": (45.4042, -71.8929),
    "St. John's": (47.5615, -52.7126),
    "Barrie": (44.3894, -79.6903),
    # Germany
    "Cologne": (50.9375, 6.9603),
    "Stuttgart": (48.7758, 9.1829),
    "Düsseldorf": (51.2277, 6.7735),
    "Leipzig": (51.3397, 12.3731),
    "Dortmund": (51.5136, 7.4653),
    "Essen": (51.4556, 7.0116),
    "Bremen": (53.0793, 8.8017),
    "Dresden": (51.0504, 13.7373),
    "Hanover": (52.3759, 9.7320),
    "Nuremberg": (49.4521, 11.0767),
    "Duisburg": (51.4344, 6.7623),
    "Bochum": (51.4818, 7.2162),
    "Wuppertal": (51.2562, 7.1508),
    "Bielefeld": (52.0302, 8.5325),
    "Bonn": (50.7374, 7.0982),
    "Münster": (51.9607, 7.6261),
    # India
    "Kolkata": (22.5726, 88.3639),
    "Ahmedabad": (23.0225, 72.5714),
    "Pune": (18.5204, 73.8567),
    "Surat": (21.1702, 72.8311),
    "Jaipur": (26.9124, 75.7873),
    "Lucknow": (26.8467, 80.9462),
    "Kanpur": (26.4499, 80.3319),
    "Nagpur": (21.1458, 79.0882),
    "Indore": (22.7196, 75.8577),
    "Thane": (19.2183, 72.9781),
    "Bhopal": (23.2599, 77.4126),
    "Visakhapatnam": (17.6868, 83.2185),
    "Patna": (25.5941, 85.1376),
    "Vadodara": (22.3072, 73.1812),
    "Ghaziabad": (28.6692, 77.4538),
    # Australia
    "Adelaide": (-34.9285, 138.6007),
    "Gold Coast": (-28.0167, 153.4000),
    "Canberra": (-35.2809, 149.1300),
    "Wollongong": (-34.4278, 150.8931),
    "Hobart": (-42.8821, 147.3272),
    "Geelong": (-38.1499, 144.3617),
    "Townsville": (-19.2590, 146.8169),
    "Cairns": (-16.9186, 145.7781),
    "Darwin": (-12.4634, 130.8456),
    "Ballarat": (-37.5622, 143.8503),
    # France
    "Toulouse": (43.6047, 1.4442),
    "Nice": (43.7102, 7.2620),
    "Nantes": (47.2184, -1.5536),
    "Strasbourg": (48.5734, 7.7521),
    "Montpellier": (43.6108, 3.8767),
    "Bordeaux": (44.8378, -0.5792),
    "Lille": (50.6292, 3.0573),
    "Rennes": (48.1173, -1.6778),
    "Reims": (49.2583, 4.0317),
    "Saint-Étienne": (45.4397, 4.3872),
    "Toulon": (43.1242, 5.9280),
    "Grenoble": (45.1885, 5.7245),
    # Brazil
    "Brasília": (-15.7975, -47.8919),
    "Salvador": (-12.9777, -38.5016),
    "Fortaleza": (-3.7319, -38.5267),
    "Belo Horizonte": (-19.9167, -43.9345),
    "Manaus": (-3.1190, -60.0217),
    "Curitiba": (-25.4284, -49.2733),
    "Recife": (-8.0476, -34.8770),
    "Porto Alegre": (-30.0346, -51.2177),
    "Belém": (-1.4558, -48.4902),
    "Goiânia": (-16.6869, -49.2648),
    "Guarulhos": (-23.4538, -46.5333),
    "Campinas": (-22.9099, -47.0626),
    "São Luís": (-2.5391, -44.2829),
    # Japan
    "Nagoya": (35.1815, 136.9066),
    "Sapporo": (43.0618, 141.3545),
    "Fukuoka": (33.5904, 130.4017),
    "Kawasaki": (35.5308, 139.7029),
    "Kobe": (34.6901, 135.1956),
    "Saitama": (35.8617, 139.6455),
    "Hiroshima": (34.3853, 132.4553),
    "Sendai": (38.2682, 140.8694),
    "Kitakyushu": (33.8835, 130.8752),
    "Chiba": (35.6073, 140.1063),
    "Sakai": (34.5733, 135.4830),
    "Kumamoto": (32.8032, 130.7079),
    # Spain (es_ES locale pack)
    "Madrid": (40.4168, -3.7038),
    "Barcelona": (41.3874, 2.1686),
    "Valencia": (39.4699, -0.3763),
    "Sevilla": (37.3891, -5.9845),
    "Zaragoza": (41.6488, -0.8891),
    "Málaga": (36.7213, -4.4214),
    "Murcia": (37.9922, -1.1307),
    "Palma": (39.5696, 2.6502),
    "Las Palmas": (28.1235, -15.4363),
    "Bilbao": (43.2630, -2.9350),
    "Alicante": (38.3452, -0.4810),
    "Córdoba": (37.8882, -4.7794),
    "Valladolid": (41.6523, -4.7245),
    "Vigo": (42.2406, -8.7207),
    "Gijón": (43.5453, -5.6615),
    # Italy (it_IT locale pack)
    "Rome": (41.9028, 12.4964),
    "Milan": (45.4642, 9.1900),
    "Naples": (40.8518, 14.2681),
    "Turin": (45.0703, 7.6869),
    "Palermo": (38.1157, 13.3615),
    "Genoa": (44.4056, 8.9463),
    "Bologna": (44.4949, 11.3426),
    "Florence": (43.7696, 11.2558),
    "Bari": (41.1171, 16.8719),
    "Catania": (37.5079, 15.0830),
    "Venice": (45.4408, 12.3155),
    "Verona": (45.4384, 10.9916),
    "Messina": (38.1938, 15.5540),
    "Padua": (45.4064, 11.8768),
    "Trieste": (45.6495, 13.7768),
    # China (zh_CN locale pack)
    "Beijing": (39.9042, 116.4074),
    "Shanghai": (31.2304, 121.4737),
    "Guangzhou": (23.1291, 113.2644),
    "Shenzhen": (22.5431, 114.0579),
    "Chengdu": (30.5728, 104.0668),
    "Chongqing": (29.4316, 106.9123),
    "Tianjin": (39.3434, 117.3616),
    "Wuhan": (30.5928, 114.3055),
    "Xi'an": (34.3416, 108.9398),
    "Hangzhou": (30.2741, 120.1551),
    "Nanjing": (32.0603, 118.7969),
    "Shenyang": (41.8057, 123.4315),
    "Harbin": (45.8038, 126.5349),
    "Dongguan": (23.0207, 113.7518),
    "Foshan": (23.0218, 113.1219),
    # South Korea (ko_KR locale pack)
    "Incheon": (37.4563, 126.7052),
    "Daegu": (35.8714, 128.6014),
    "Daejeon": (36.3504, 127.3845),
    "Gwangju": (35.1595, 126.8526),
    "Suwon": (37.2636, 127.0286),
    "Ulsan": (35.5384, 129.3114),
    "Changwon": (35.2281, 128.6811),
    "Goyang": (37.6584, 126.8320),
    "Yongin": (37.2411, 127.1776),
    "Seongnam": (37.4200, 127.1265),
    "Bucheon": (37.5034, 126.7660),
    "Cheongju": (36.6424, 127.4890),
    "Ansan": (37.3219, 126.8309),
    # Turkey (tr_TR locale pack)
    "Istanbul": (41.0082, 28.9784),
    "Ankara": (39.9334, 32.8597),
    "İzmir": (38.4237, 27.1428),
    "Bursa": (40.1885, 29.0610),
    "Antalya": (36.8969, 30.7133),
    "Adana": (37.0000, 35.3213),
    "Konya": (37.8667, 32.4833),
    "Gaziantep": (37.0662, 37.3833),
    "Mersin": (36.8121, 34.6415),
    "Diyarbakır": (37.9144, 40.2306),
    # Saudi Arabia (ar_SA locale pack)
    "Riyadh": (24.7136, 46.6753),
    "Jeddah": (21.4858, 39.1925),
    "Mecca": (21.3891, 39.8579),
    "Medina": (24.5247, 39.5692),
    "Dammam": (26.4207, 50.0888),
    "Khobar": (26.2172, 50.1971),
    "Tabuk": (28.3838, 36.5550),
    "Buraidah": (26.3260, 43.9750),
    "Khamis Mushait": (18.3000, 42.7333),
    "Abha": (18.2164, 42.5053),
    "Hail": (27.5114, 41.7208),
    "Najran": (17.4924, 44.1277),
    "Jubail": (27.0046, 49.6460),
    "Yanbu": (24.0895, 38.0618),
    "Al Hofuf": (25.3647, 49.5747),
    # Poland (pl_PL locale pack)
    "Warsaw": (52.2297, 21.0122),
    "Kraków": (50.0647, 19.9450),
    "Łódź": (51.7592, 19.4560),
    "Wrocław": (51.1079, 17.0385),
    "Poznań": (52.4064, 16.9252),
    "Gdańsk": (54.3520, 18.6466),
    "Szczecin": (53.4285, 14.5528),
    "Bydgoszcz": (53.1235, 18.0084),
    "Lublin": (51.2465, 22.5684),
    "Białystok": (53.1325, 23.1688),
    # Native-language aliases used by locale packs
    "München": (48.1351, 11.5820),
    "Köln": (50.9375, 6.9603),
    "Frankfurt am Main": (50.1109, 8.6821),
    "Nürnberg": (49.4521, 11.0767),
    "Hannover": (52.3759, 9.7320),
    "Le Havre": (49.4944, 0.1079),
    "Bengaluru": (12.9716, 77.5946),
    "Niigata": (37.9162, 139.0364),
    # Netherlands
    "Amsterdam": (52.3676, 4.9041),
    "Rotterdam": (51.9244, 4.4777),
    "The Hague": (52.0705, 4.3007),
    "Utrecht": (52.0907, 5.1214),
    "Eindhoven": (51.4416, 5.4697),
    "Tilburg": (51.5555, 5.0913),
    "Groningen": (53.2194, 6.5665),
    "Almere": (52.3508, 5.2647),
    "Breda": (51.5719, 4.7683),
    "Nijmegen": (51.8126, 5.8372),
}

CITY_COORDS: Dict[str, Tuple[float, float]] = {
    city: (lat, lon) for city, lat, lon, _postal, _cc in CITY_GEODATA
}
CITY_COORDS.update(_SUPPLEMENT)


def haversine_km(
    lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray
) -> np.ndarray:
    """Vectorised great-circle distance in km."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 6371.0 * 2.0 * np.arcsin(np.sqrt(a))


def known_city(city: str) -> bool:
    return str(city) in CITY_COORDS


def road_distance_km(origin: str, destination: str) -> Optional[float]:
    """Deterministic road distance between two known cities, else None."""
    a = CITY_COORDS.get(str(origin))
    b = CITY_COORDS.get(str(destination))
    if a is None or b is None:
        return None
    gc = haversine_km(
        np.array(a[0]), np.array(a[1]), np.array(b[0]), np.array(b[1])
    )
    return round(float(gc) * ROAD_CIRCUITY, 1)


def travel_hours(distance_km: float) -> float:
    """Ground travel time from distance: driving at effective speed plus
    fixed handling overhead."""
    return round(distance_km / EFFECTIVE_SPEED_KMH + HANDLING_OVERHEAD_H, 1)
