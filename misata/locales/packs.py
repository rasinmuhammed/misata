"""
Locale data packs for Misata.

Each pack carries:
  - Faker locale code (for name / address / phone generation)
  - Currency metadata
  - Salary distributions (median, std — log-normal params in local currency)
    Sources: OECD, World Bank, ILO, national statistics offices (2023-24 data)
  - National ID label and format hint
  - Date / number formatting conventions
  - Top cities (population-ranked)
  - Common banks
  - Company legal suffixes
  - Age distribution (mean ± std from UN population data)
  - Postcode pattern (regex)
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class LocalePack:
    # ── Identity ──────────────────────────────────────────────────────────────
    locale_code: str          # BCP-47 / Faker code, e.g. "de_DE"
    country_name: str
    language: str

    # ── Faker integration ─────────────────────────────────────────────────────
    faker_locale: str         # Faker() locale string

    # ── Currency ──────────────────────────────────────────────────────────────
    currency_code: str        # ISO 4217
    currency_symbol: str
    decimal_separator: str = "."
    thousands_separator: str = ","

    # ── Salary (annual, local currency, individual) ───────────────────────────
    salary_min: float = 10_000
    salary_median: float = 40_000
    salary_max: float = 200_000
    salary_lognormal_mean: float = 10.6    # ln(salary); ln(40000) ≈ 10.60
    salary_lognormal_std: float = 0.5

    # ── Formats ───────────────────────────────────────────────────────────────
    date_format: str = "YYYY-MM-DD"
    phone_prefix: str = "+1"
    postcode_pattern: str = r"\d{5}"

    # ── National ID ───────────────────────────────────────────────────────────
    national_id_label: str = "National ID"
    national_id_pattern: str = r"\d{9}"   # hint for generators

    # ── Age distribution (mean ± std, truncated normal) ───────────────────────
    age_mean: float = 38.0
    age_std: float = 14.0

    # ── Geography ─────────────────────────────────────────────────────────────
    top_cities: List[str] = field(default_factory=list)

    # ── Finance ───────────────────────────────────────────────────────────────
    common_banks: List[str] = field(default_factory=list)
    tax_rate_typical: float = 0.25   # rough effective rate

    # ── Business ──────────────────────────────────────────────────────────────
    company_suffixes: List[str] = field(default_factory=list)

    # ── Misc ──────────────────────────────────────────────────────────────────
    vat_rate: float = 0.20
    timezone: str = "UTC"


# ── Locale packs ──────────────────────────────────────────────────────────────
# Salary data sources:
#   US: BLS Occupational Employment Statistics 2023 (~$59k median annual)
#   UK: ONS Annual Survey of Hours and Earnings 2023 (~£35k → ~$44k)
#   DE: Destatis 2023 (~€45k)
#   FR: INSEE 2023 (~€36k)
#   BR: IBGE PNAD Contínua 2023 (~R$2,800/month → R$33,600/year)
#   ES: INE 2023 (~€24k)
#   IN: NITI Aayog / PLFS 2023 (~₹350k/year median formal sector)
#   JP: Ministry of Health, Labour and Welfare 2023 (~¥4.4M)
#   CN: NBS China 2023 (~¥97k urban average)
#   SA: GASTAT 2023 (~SAR 96k median private sector)
#   KR: Statistics Korea 2023 (~₩40M)
#   NL: CBS 2023 (~€42k)
#   IT: ISTAT 2023 (~€29k)
#   PL: GUS 2023 (~PLN 72k)
#   TR: TÜİK 2023 (~TRY 300k; high inflation, use carefully)

import math

def _lognorm(median: float) -> tuple:
    """Return (lognormal_mean, std=0.5) for a given median salary."""
    return math.log(median), 0.5


LOCALE_PACKS: dict = {}

def _reg(pack: LocalePack) -> None:
    LOCALE_PACKS[pack.locale_code] = pack


# ── United States ─────────────────────────────────────────────────────────────
_lm, _ls = _lognorm(59_000)
_reg(LocalePack(
    locale_code="en_US",
    country_name="United States",
    language="English",
    faker_locale="en_US",
    currency_code="USD",
    currency_symbol="$",
    salary_min=15_000,
    salary_median=59_000,
    salary_max=500_000,
    salary_lognormal_mean=_lm,
    salary_lognormal_std=_ls,
    date_format="MM/DD/YYYY",
    phone_prefix="+1",
    postcode_pattern=r"\d{5}",
    national_id_label="SSN",
    national_id_pattern=r"\d{3}-\d{2}-\d{4}",
    age_mean=38.5,
    age_std=15.0,
    top_cities=[
        "New York", "Los Angeles", "Chicago", "Houston", "Phoenix",
        "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose",
        "Austin", "Jacksonville", "Fort Worth", "Columbus", "Charlotte",
        "Seattle", "Denver", "Boston", "Nashville", "Portland",
    ],
    common_banks=["JPMorgan Chase", "Bank of America", "Wells Fargo", "Citibank",
                  "U.S. Bancorp", "Truist", "Capital One", "PNC Bank"],
    tax_rate_typical=0.22,
    company_suffixes=["Inc.", "LLC", "Corp.", "Ltd.", "Co.", "LP", "LLP"],
    vat_rate=0.0,
    timezone="America/New_York",
))

# ── United Kingdom ────────────────────────────────────────────────────────────
_lm, _ls = _lognorm(35_000)
_reg(LocalePack(
    locale_code="en_GB",
    country_name="United Kingdom",
    language="English",
    faker_locale="en_GB",
    currency_code="GBP",
    currency_symbol="£",
    salary_min=12_000,
    salary_median=35_000,
    salary_max=250_000,
    salary_lognormal_mean=_lm,
    salary_lognormal_std=_ls,
    date_format="DD/MM/YYYY",
    phone_prefix="+44",
    postcode_pattern=r"[A-Z]{1,2}\d[A-Z\d]? \d[A-Z]{2}",
    national_id_label="NI Number",
    national_id_pattern=r"[A-Z]{2}\d{6}[A-Z]",
    age_mean=40.5,
    age_std=15.5,
    top_cities=[
        "London", "Birmingham", "Manchester", "Glasgow", "Liverpool",
        "Bristol", "Sheffield", "Leeds", "Edinburgh", "Leicester",
        "Coventry", "Bradford", "Nottingham", "Cardiff", "Belfast",
    ],
    common_banks=["Barclays", "HSBC UK", "NatWest", "Lloyds Bank", "Santander UK",
                  "Halifax", "TSB", "Nationwide"],
    tax_rate_typical=0.20,
    company_suffixes=["Ltd", "PLC", "LLP", "CIC"],
    vat_rate=0.20,
    timezone="Europe/London",
))

# ── Germany ───────────────────────────────────────────────────────────────────
_lm, _ls = _lognorm(45_000)
_reg(LocalePack(
    locale_code="de_DE",
    country_name="Germany",
    language="German",
    faker_locale="de_DE",
    currency_code="EUR",
    currency_symbol="€",
    decimal_separator=",",
    thousands_separator=".",
    salary_min=18_000,
    salary_median=45_000,
    salary_max=300_000,
    salary_lognormal_mean=_lm,
    salary_lognormal_std=_ls,
    date_format="DD.MM.YYYY",
    phone_prefix="+49",
    postcode_pattern=r"\d{5}",
    national_id_label="Steuer-ID",
    national_id_pattern=r"\d{11}",
    age_mean=44.6,
    age_std=17.0,
    top_cities=[
        "Berlin", "Hamburg", "München", "Köln", "Frankfurt am Main",
        "Stuttgart", "Düsseldorf", "Leipzig", "Dortmund", "Essen",
        "Bremen", "Dresden", "Hannover", "Nürnberg", "Duisburg",
    ],
    common_banks=["Deutsche Bank", "Commerzbank", "Sparkasse", "Volksbank",
                  "ING-DiBa", "Postbank", "HypoVereinsbank", "DZ Bank"],
    tax_rate_typical=0.30,
    company_suffixes=["GmbH", "AG", "KG", "GbR", "e.V.", "UG", "OHG"],
    vat_rate=0.19,
    timezone="Europe/Berlin",
))

# ── France ────────────────────────────────────────────────────────────────────
_lm, _ls = _lognorm(36_000)
_reg(LocalePack(
    locale_code="fr_FR",
    country_name="France",
    language="French",
    faker_locale="fr_FR",
    currency_code="EUR",
    currency_symbol="€",
    decimal_separator=",",
    thousands_separator=" ",
    salary_min=14_000,
    salary_median=36_000,
    salary_max=250_000,
    salary_lognormal_mean=_lm,
    salary_lognormal_std=_ls,
    date_format="DD/MM/YYYY",
    phone_prefix="+33",
    postcode_pattern=r"\d{5}",
    national_id_label="NIR",
    national_id_pattern=r"\d{15}",
    age_mean=41.7,
    age_std=16.0,
    top_cities=[
        "Paris", "Marseille", "Lyon", "Toulouse", "Nice",
        "Nantes", "Strasbourg", "Montpellier", "Bordeaux", "Lille",
        "Rennes", "Reims", "Saint-Étienne", "Toulon", "Le Havre",
    ],
    common_banks=["BNP Paribas", "Crédit Agricole", "Société Générale",
                  "Banque Populaire", "LCL", "Caisse d'Épargne", "La Banque Postale"],
    tax_rate_typical=0.27,
    company_suffixes=["SARL", "SA", "SAS", "SASU", "SNC", "EURL", "EI"],
    vat_rate=0.20,
    timezone="Europe/Paris",
))

# ── Brazil ────────────────────────────────────────────────────────────────────
_lm, _ls = _lognorm(33_600)
_reg(LocalePack(
    locale_code="pt_BR",
    country_name="Brazil",
    language="Portuguese",
    faker_locale="pt_BR",
    currency_code="BRL",
    currency_symbol="R$",
    decimal_separator=",",
    thousands_separator=".",
    salary_min=15_600,    # minimum wage 2024: R$1,412/month
    salary_median=33_600,
    salary_max=300_000,
    salary_lognormal_mean=_lm,
    salary_lognormal_std=_ls,
    date_format="DD/MM/YYYY",
    phone_prefix="+55",
    postcode_pattern=r"\d{5}-\d{3}",
    national_id_label="CPF",
    national_id_pattern=r"\d{3}\.\d{3}\.\d{3}-\d{2}",
    age_mean=33.5,
    age_std=14.0,
    top_cities=[
        "São Paulo", "Rio de Janeiro", "Brasília", "Salvador", "Fortaleza",
        "Belo Horizonte", "Manaus", "Curitiba", "Recife", "Porto Alegre",
        "Belém", "Goiânia", "Guarulhos", "Campinas", "São Luís",
    ],
    common_banks=["Banco do Brasil", "Itaú Unibanco", "Bradesco", "Caixa Econômica Federal",
                  "Santander Brasil", "Nubank", "BTG Pactual", "Banco Inter"],
    tax_rate_typical=0.27,
    company_suffixes=["Ltda.", "S.A.", "EIRELI", "MEI", "S/A"],
    vat_rate=0.17,   # ICMS average
    timezone="America/Sao_Paulo",
))

# ── Spain ─────────────────────────────────────────────────────────────────────
_lm, _ls = _lognorm(24_000)
_reg(LocalePack(
    locale_code="es_ES",
    country_name="Spain",
    language="Spanish",
    faker_locale="es_ES",
    currency_code="EUR",
    currency_symbol="€",
    decimal_separator=",",
    thousands_separator=".",
    salary_min=10_000,
    salary_median=24_000,
    salary_max=200_000,
    salary_lognormal_mean=_lm,
    salary_lognormal_std=_ls,
    date_format="DD/MM/YYYY",
    phone_prefix="+34",
    postcode_pattern=r"\d{5}",
    national_id_label="DNI/NIE",
    national_id_pattern=r"\d{8}[A-Z]",
    age_mean=44.0,
    age_std=17.0,
    top_cities=[
        "Madrid", "Barcelona", "Valencia", "Sevilla", "Zaragoza",
        "Málaga", "Murcia", "Palma", "Las Palmas", "Bilbao",
        "Alicante", "Córdoba", "Valladolid", "Vigo", "Gijón",
    ],
    common_banks=["Santander", "BBVA", "CaixaBank", "Sabadell", "Bankinter",
                  "Unicaja", "Ibercaja"],
    tax_rate_typical=0.25,
    company_suffixes=["S.L.", "S.A.", "S.L.U.", "S.C.", "S.Coop."],
    vat_rate=0.21,
    timezone="Europe/Madrid",
))

# ── India ─────────────────────────────────────────────────────────────────────
_lm, _ls = _lognorm(350_000)
_reg(LocalePack(
    locale_code="hi_IN",
    country_name="India",
    language="Hindi/English",
    faker_locale="en_IN",
    currency_code="INR",
    currency_symbol="₹",
    decimal_separator=".",
    thousands_separator=",",
    salary_min=120_000,
    salary_median=350_000,
    salary_max=5_000_000,
    salary_lognormal_mean=_lm,
    salary_lognormal_std=_ls,
    date_format="DD/MM/YYYY",
    phone_prefix="+91",
    postcode_pattern=r"\d{6}",
    national_id_label="Aadhaar",
    national_id_pattern=r"\d{4} \d{4} \d{4}",
    age_mean=28.4,
    age_std=12.0,
    top_cities=[
        "Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Ahmedabad",
        "Chennai", "Kolkata", "Pune", "Jaipur", "Surat",
        "Lucknow", "Kanpur", "Nagpur", "Indore", "Thane",
    ],
    common_banks=["State Bank of India", "HDFC Bank", "ICICI Bank", "Axis Bank",
                  "Bank of Baroda", "Punjab National Bank", "Kotak Mahindra Bank", "IDBI Bank"],
    tax_rate_typical=0.20,
    company_suffixes=["Pvt. Ltd.", "Ltd.", "LLP", "OPC Pvt. Ltd.", "& Co."],
    vat_rate=0.18,   # GST standard rate
    timezone="Asia/Kolkata",
))

# ── Japan ─────────────────────────────────────────────────────────────────────
_lm, _ls = _lognorm(4_400_000)
_reg(LocalePack(
    locale_code="ja_JP",
    country_name="Japan",
    language="Japanese",
    faker_locale="ja_JP",
    currency_code="JPY",
    currency_symbol="¥",
    decimal_separator=".",
    thousands_separator=",",
    salary_min=2_000_000,
    salary_median=4_400_000,
    salary_max=30_000_000,
    salary_lognormal_mean=_lm,
    salary_lognormal_std=_ls,
    date_format="YYYY/MM/DD",
    phone_prefix="+81",
    postcode_pattern=r"\d{3}-\d{4}",
    national_id_label="My Number",
    national_id_pattern=r"\d{12}",
    age_mean=48.6,
    age_std=18.0,
    top_cities=[
        "Tokyo", "Osaka", "Nagoya", "Sapporo", "Fukuoka",
        "Kobe", "Kyoto", "Kawasaki", "Saitama", "Hiroshima",
        "Sendai", "Chiba", "Kitakyushu", "Sakai", "Niigata",
    ],
    common_banks=["MUFG Bank", "Sumitomo Mitsui", "Mizuho Bank", "Japan Post Bank",
                  "Resona Bank", "Shizuoka Bank", "Seven Bank"],
    tax_rate_typical=0.20,
    company_suffixes=["株式会社", "有限会社", "合同会社", "一般社団法人"],
    vat_rate=0.10,
    timezone="Asia/Tokyo",
))

# ── China ─────────────────────────────────────────────────────────────────────
_lm, _ls = _lognorm(97_000)
_reg(LocalePack(
    locale_code="zh_CN",
    country_name="China",
    language="Mandarin Chinese",
    faker_locale="zh_CN",
    currency_code="CNY",
    currency_symbol="¥",
    decimal_separator=".",
    thousands_separator=",",
    salary_min=30_000,
    salary_median=97_000,
    salary_max=1_000_000,
    salary_lognormal_mean=_lm,
    salary_lognormal_std=_ls,
    date_format="YYYY/MM/DD",
    phone_prefix="+86",
    postcode_pattern=r"\d{6}",
    national_id_label="居民身份证",
    national_id_pattern=r"\d{18}",
    age_mean=38.5,
    age_std=14.5,
    top_cities=[
        "Shanghai", "Beijing", "Chongqing", "Guangzhou", "Shenzhen",
        "Chengdu", "Wuhan", "Xi'an", "Hangzhou", "Nanjing",
        "Tianjin", "Dongguan", "Foshan", "Shenyang", "Harbin",
    ],
    common_banks=["Industrial and Commercial Bank of China", "China Construction Bank",
                  "Agricultural Bank of China", "Bank of China", "Bank of Communications",
                  "China Merchants Bank", "Ping An Bank", "Postal Savings Bank"],
    tax_rate_typical=0.20,
    company_suffixes=["有限公司", "股份有限公司", "集团有限公司"],
    vat_rate=0.13,
    timezone="Asia/Shanghai",
))

# ── Saudi Arabia ──────────────────────────────────────────────────────────────
_lm, _ls = _lognorm(96_000)
_reg(LocalePack(
    locale_code="ar_SA",
    country_name="Saudi Arabia",
    language="Arabic",
    faker_locale="ar_SA",
    currency_code="SAR",
    currency_symbol="﷼",
    decimal_separator=".",
    thousands_separator=",",
    salary_min=24_000,
    salary_median=96_000,
    salary_max=600_000,
    salary_lognormal_mean=_lm,
    salary_lognormal_std=_ls,
    date_format="DD/MM/YYYY",
    phone_prefix="+966",
    postcode_pattern=r"\d{5}",
    national_id_label="Iqama/NID",
    national_id_pattern=r"\d{10}",
    age_mean=29.5,
    age_std=11.0,
    top_cities=[
        "Riyadh", "Jeddah", "Mecca", "Medina", "Dammam",
        "Khobar", "Tabuk", "Abha", "Hail", "Najran",
        "Yanbu", "Khamis Mushait", "Buraidah", "Al Hofuf", "Jubail",
    ],
    common_banks=["Al Rajhi Bank", "Saudi National Bank", "Riyad Bank",
                  "Banque Saudi Fransi", "Arab National Bank", "Alinma Bank", "Bank Albilad"],
    tax_rate_typical=0.20,
    company_suffixes=["شركة ذات مسؤولية محدودة", "شركة مساهمة", "مؤسسة فردية"],
    vat_rate=0.15,
    timezone="Asia/Riyadh",
))

# ── South Korea ───────────────────────────────────────────────────────────────
_lm, _ls = _lognorm(40_000_000)
_reg(LocalePack(
    locale_code="ko_KR",
    country_name="South Korea",
    language="Korean",
    faker_locale="ko_KR",
    currency_code="KRW",
    currency_symbol="₩",
    decimal_separator=".",
    thousands_separator=",",
    salary_min=24_000_000,
    salary_median=40_000_000,
    salary_max=200_000_000,
    salary_lognormal_mean=_lm,
    salary_lognormal_std=_ls,
    date_format="YYYY.MM.DD",
    phone_prefix="+82",
    postcode_pattern=r"\d{5}",
    national_id_label="주민등록번호",
    national_id_pattern=r"\d{6}-\d{7}",
    age_mean=43.7,
    age_std=16.5,
    top_cities=[
        "Seoul", "Busan", "Incheon", "Daegu", "Daejeon",
        "Gwangju", "Suwon", "Ulsan", "Changwon", "Goyang",
        "Seongnam", "Yongin", "Bucheon", "Cheongju", "Ansan",
    ],
    common_banks=["Kookmin Bank", "Shinhan Bank", "KEB Hana Bank", "Woori Bank",
                  "NH Agricultural Bank", "IBK", "Kakao Bank", "Toss Bank"],
    tax_rate_typical=0.22,
    company_suffixes=["주식회사", "유한회사", "합자회사"],
    vat_rate=0.10,
    timezone="Asia/Seoul",
))

# ── Netherlands ───────────────────────────────────────────────────────────────
_lm, _ls = _lognorm(42_000)
_reg(LocalePack(
    locale_code="nl_NL",
    country_name="Netherlands",
    language="Dutch",
    faker_locale="nl_NL",
    currency_code="EUR",
    currency_symbol="€",
    decimal_separator=",",
    thousands_separator=".",
    salary_min=20_000,
    salary_median=42_000,
    salary_max=300_000,
    salary_lognormal_mean=_lm,
    salary_lognormal_std=_ls,
    date_format="DD-MM-YYYY",
    phone_prefix="+31",
    postcode_pattern=r"\d{4} [A-Z]{2}",
    national_id_label="BSN",
    national_id_pattern=r"\d{9}",
    age_mean=42.7,
    age_std=16.5,
    top_cities=[
        "Amsterdam", "Rotterdam", "The Hague", "Utrecht", "Eindhoven",
        "Tilburg", "Groningen", "Almere", "Breda", "Nijmegen",
    ],
    common_banks=["ING Bank", "ABN AMRO", "Rabobank", "SNS Bank",
                  "ASN Bank", "Triodos Bank", "Knab"],
    tax_rate_typical=0.37,
    company_suffixes=["B.V.", "N.V.", "V.O.F.", "Stichting", "C.V."],
    vat_rate=0.21,
    timezone="Europe/Amsterdam",
))

# ── Italy ─────────────────────────────────────────────────────────────────────
_lm, _ls = _lognorm(29_000)
_reg(LocalePack(
    locale_code="it_IT",
    country_name="Italy",
    language="Italian",
    faker_locale="it_IT",
    currency_code="EUR",
    currency_symbol="€",
    decimal_separator=",",
    thousands_separator=".",
    salary_min=12_000,
    salary_median=29_000,
    salary_max=200_000,
    salary_lognormal_mean=_lm,
    salary_lognormal_std=_ls,
    date_format="DD/MM/YYYY",
    phone_prefix="+39",
    postcode_pattern=r"\d{5}",
    national_id_label="Codice Fiscale",
    national_id_pattern=r"[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]",
    age_mean=46.2,
    age_std=17.5,
    top_cities=[
        "Rome", "Milan", "Naples", "Turin", "Palermo",
        "Genoa", "Bologna", "Florence", "Bari", "Catania",
        "Venice", "Verona", "Messina", "Padua", "Trieste",
    ],
    common_banks=["UniCredit", "Intesa Sanpaolo", "Mediobanca", "Banco BPM",
                  "BPER Banca", "Cassa Depositi e Prestiti", "FinecoBank"],
    tax_rate_typical=0.27,
    company_suffixes=["S.r.l.", "S.p.A.", "S.n.c.", "S.a.s.", "Soc. Coop."],
    vat_rate=0.22,
    timezone="Europe/Rome",
))

# ── Poland ────────────────────────────────────────────────────────────────────
_lm, _ls = _lognorm(72_000)
_reg(LocalePack(
    locale_code="pl_PL",
    country_name="Poland",
    language="Polish",
    faker_locale="pl_PL",
    currency_code="PLN",
    currency_symbol="zł",
    decimal_separator=",",
    thousands_separator=" ",
    salary_min=30_000,
    salary_median=72_000,
    salary_max=600_000,
    salary_lognormal_mean=_lm,
    salary_lognormal_std=_ls,
    date_format="DD.MM.YYYY",
    phone_prefix="+48",
    postcode_pattern=r"\d{2}-\d{3}",
    national_id_label="PESEL",
    national_id_pattern=r"\d{11}",
    age_mean=41.9,
    age_std=16.5,
    top_cities=[
        "Warsaw", "Kraków", "Łódź", "Wrocław", "Poznań",
        "Gdańsk", "Szczecin", "Bydgoszcz", "Lublin", "Białystok",
    ],
    common_banks=["PKO Bank Polski", "Bank Pekao", "ING Bank Śląski",
                  "mBank", "Santander Bank Polska", "Alior Bank", "Bank Millennium"],
    tax_rate_typical=0.17,
    company_suffixes=["Sp. z o.o.", "S.A.", "Sp. k.", "S.K.A."],
    vat_rate=0.23,
    timezone="Europe/Warsaw",
))

# ── Turkey ────────────────────────────────────────────────────────────────────
_lm, _ls = _lognorm(300_000)
_reg(LocalePack(
    locale_code="tr_TR",
    country_name="Turkey",
    language="Turkish",
    faker_locale="tr_TR",
    currency_code="TRY",
    currency_symbol="₺",
    decimal_separator=",",
    thousands_separator=".",
    salary_min=100_000,
    salary_median=300_000,
    salary_max=3_000_000,
    salary_lognormal_mean=_lm,
    salary_lognormal_std=_ls,
    date_format="DD.MM.YYYY",
    phone_prefix="+90",
    postcode_pattern=r"\d{5}",
    national_id_label="TC Kimlik No",
    national_id_pattern=r"\d{11}",
    age_mean=32.5,
    age_std=13.5,
    top_cities=[
        "Istanbul", "Ankara", "İzmir", "Bursa", "Antalya",
        "Adana", "Konya", "Gaziantep", "Mersin", "Diyarbakır",
    ],
    common_banks=["Ziraat Bankası", "Türkiye İş Bankası", "Garanti BBVA",
                  "Akbank", "Yapı ve Kredi Bankası", "Halkbank", "VakıfBank"],
    tax_rate_typical=0.20,
    company_suffixes=["A.Ş.", "Ltd. Şti.", "Koll. Şti.", "Kom. Şti."],
    vat_rate=0.20,
    timezone="Europe/Istanbul",
))
