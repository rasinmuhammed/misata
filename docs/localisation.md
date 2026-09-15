---
title: Localisation, Country-Accurate Synthetic Data in 20 Locales
description: Misata generates country-accurate synthetic data for 20 locales including US, UK, Germany, Japan, India, and all six GCC states, with real salary distributions, national ID formats, and currencies.
---

# Localisation

Misata generates country-accurate data automatically, names, salary distributions, national ID formats, currencies, postcodes, and company suffixes, from a geographic signal in your story.

## Automatic detection

```python
import misata

# Locale detected from story — no extra flag needed
tables = misata.generate("German SaaS company in Berlin with 2k enterprise customers")
# → de_DE names, salary ~ lognormal median €45k, 5-digit postcodes, GmbH/AG suffixes

tables = misata.generate("Brazilian fintech with R$ payments and CPF verification")
# → pt_BR names, salary median ~R$33.6k, national IDs in CPF format ###.###.###-##

tables = misata.generate("Indian startup in Bangalore with ₹ salary bands and Aadhaar KYC")
# → hi_IN names, salary median ~₹350k/yr, Aadhaar 12-digit national IDs
```

## Explicit locale

```python
# Override detected locale
tables = misata.generate("Ecommerce store with 10k orders", locale="ja_JP")

# Or via CLI
# misata generate --story "Ecommerce store" --locale ja_JP
```

## 20 built-in locales

| Locale | Country | Currency | Salary median | National ID |
|:--|:--|:--|--:|:--|
| `en_US` | United States | USD / $ | $62 000 | SSN `###-##-####` |
| `en_GB` | United Kingdom | GBP / £ | £34 000 | NIN `AA######A` |
| `de_DE` | Germany | EUR / € | €45 000 | Steuer-IdNr |
| `fr_FR` | France | EUR / € | €38 000 | NIR |
| `pt_BR` | Brazil | BRL / R$ | R$33 600 | CPF `###.###.###-##` |
| `es_ES` | Spain | EUR / € | €27 000 | NIE |
| `hi_IN` | India | INR / ₹ | ₹350 000 | Aadhaar `####-####-####` |
| `ja_JP` | Japan | JPY / ¥ | ¥4 400 000 | My Number |
| `zh_CN` | China | CNY / ¥ | ¥90 000 | Resident ID |
| `ar_SA` | Saudi Arabia | SAR | SAR 96 000 | Iqama/NID |
| `ko_KR` | South Korea | KRW / ₩ | ₩42 000 000 | RRN |
| `nl_NL` | Netherlands | EUR / € | €42 000 | BSN |
| `it_IT` | Italy | EUR / € | €29 000 | Codice Fiscale |
| `pl_PL` | Poland | PLN | PLN 72 000 | PESEL |
| `tr_TR` | Turkey | TRY | TRY 720 000 | TC Kimlik |
| `ar_QA` | Qatar | QAR | QAR 149 000 | QID |
| `ar_AE` | United Arab Emirates | AED | AED 166 000 | Emirates ID |
| `ar_KW` | Kuwait | KWD | KWD 14 400 | Civil ID |
| `ar_BH` | Bahrain | BHD | BHD 6 900 | CPR number |
| `ar_OM` | Oman | OMR | OMR 4 320 | Civil Number |

Salary data sourced from OECD, World Bank, ILO (2023–24), plus national
statistics offices for the GCC states: Qatar National Planning Council,
UAE Federal Competitiveness and Statistics Centre, MenaJobs GCC Salary
Report 2026, Bahrain's official national-median figure, and Oman's National
Centre for Statistics and Information — see `misata/locales/packs.py` for
per-locale citations. Qatar and the UAE have no median published; those two
figures are the official average instead, called out as such in the source
code.

## Inspect a locale pack

```python
pack = misata.get_locale_pack("de_DE")

print(pack.salary_median)        # 45000
print(pack.currency_symbol)      # €
print(pack.top_cities[:3])       # ['Berlin', 'Hamburg', 'Munich']
print(pack.company_suffixes)     # ['GmbH', 'AG', 'UG', 'KG', 'e.K.']
print(pack.postcode_pattern)     # \d{5}
print(pack.national_id_label)    # Steuer-IdNr
```

## Detect from a story

```python
locale = misata.detect_locale("South Korean company in Seoul with KRW salaries")
# → "ko_KR"

locale = misata.detect_locale("A generic SaaS company")
# → "en_US"  (default)
```

## What locale affects

- **Names**: Faker locale pool (`de_DE` Faker generates German names, `ja_JP` generates Japanese names)
- **Salary & age distributions**: lognormal/normal priors from national statistics replace the en_US defaults
- **Postcodes**: pattern-generated to match the country format (e.g. 5 digits for DE, `SW1A 1AA` format for GB)
- **National IDs**: pattern-generated to match country format (CPF, SSN, Aadhaar, etc.)
- **Company suffixes**: GmbH/AG for Germany, S.A./SARL for France, Ltd/PLC for UK
- **Phone prefixes**: country dialling code prepended

!!! note "Asset-backed vocabulary takes priority"
    If you have ingested Kaggle vocabulary assets for name columns, those always win over locale-based Faker names. Locale is the fallback, not the override.
