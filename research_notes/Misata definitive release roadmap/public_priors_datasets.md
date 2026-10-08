# Public, Redistributable Data Sources for Statistical Priors (Misata)

Scope: open datasets that can be distilled into compact distribution tables (quantiles, frequency tables, shares, seasonal indices) shipped inside an MIT/Apache Python package. Research done 2026-10-04. Some licence pages (e.g. ilostat.ilo.org) were blocked by the network proxy, so a few findings rely on secondary summaries; these are flagged.

## Income and wages distributions by country/occupation

### Takeaway
Most aggregate wage tables from official statistics (ILOSTAT, OECD, Eurostat, World Bank, BLS, ONS, e-Stat Japan, India GODL) are reusable commercially with attribution or are public domain, so distilled quantile tables are bundleable. The two main exceptions are microdata-only sources, LIS and EU-SILC scientific-use files, which forbid redistribution. Only their published aggregates should be used.

### Cited Findings
- **ILOSTAT (global, by occupation/sex/country)**: content is licensed CC BY 4.0. — [re3data ILOSTAT entry](https://www.re3data.org/repository/r3d100013044) (secondary; the ILO's own terms page could not be reached through the proxy).
- **OECD**: under the Open Access Policy, most OECD content published from 1 July 2024 is CC BY 4.0, which allows reproduction, distribution and adaptation for any purpose. OECD warns that some data may carry third-party rights or specific terms. — [OECD Terms & Conditions](https://www.oecd.org/en/about/terms-conditions.html); [OECD press release July 2024](https://www.oecd.org/en/about/news/press-releases/2024/07/oecd-data-publications-and-analysis-become-freely-accessible.html)
- **Eurostat (EU aggregates incl. SILC published tables, earnings)**: "Reuse of statistical data, metadata, publications... for commercial or non-commercial purposes is authorised provided the source is acknowledged". Editorial content is CC BY 4.0. Third-party material, logos and trademarks are excluded. — [Eurostat copyright notice](https://ec.europa.eu/eurostat/help/copyright-notice)
- **EU-SILC microdata**: scientific-use files go only to accredited research bodies, for scientific purposes, and must be destroyed when the access period ends. They cannot be bundled. Only Eurostat's published aggregate tables are usable. — [Eurostat microdata overview](https://ec.europa.eu/eurostat/web/microdata); [CROS microdata access](https://cros.ec.europa.eu/microdata-access)
- **World Bank (WDI, income/PPP/Gini)**: CC BY 4.0 unless labelled otherwise, with attribution in the form "The World Bank: Dataset name: Data source". Some WDI indicators come from third parties and are not CC BY. You may not imply endorsement by the World Bank. — [World Bank Datasets terms](https://www.worldbank.org/ext/en/legal/terms-conditions/datasets); [Summary Terms of Use](https://data.worldbank.org/summary-terms-of-use)
- **US BLS (OES/OEWS wages by occupation, CPI, CE)**: "everything that we publish... is in the public domain, except for previously copyrighted photographs and illustrations". Citation is requested, and the BLS emblem is a registered trademark. — [BLS Linking and Copyright Information](https://www.bls.gov/bls/linksite.htm)
- **UK ONS ASHE**: the 2025 provisional results were released 23 Oct 2025. They are based on a 1% sample of PAYE jobs, with tables by age, region, occupation (2-digit and 4-digit SOC, Tables 3, 14, 15, 20) and percentiles, including 90th–99th FOI tables. ONS releases data under the Open Government Licence. — [ONS ASHE 2025 bulletin](https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours/bulletins/annualsurveyofhoursandearnings/2025); [ASHE Table 3](https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours/datasets/regionbyoccupation2digitsocashetable3); [90th–99th percentiles FOI](https://www.ons.gov.uk/aboutus/transparencyandgovernance/freedomofinformationfoi/90thto99thpercentilesforgrossweeklyearningsoffulltimeemployeesintheuk)
- **LIS (Luxembourg Income Study)**: member countries supplied the data "with the restriction that they not be redistributed or otherwise copied". Access is remote-execution only. — [LIS Working Paper 247](https://www.lisdatacenter.org/wps/liswps/247.pdf). LIS key figures (deciles) are republished via [Our World in Data](https://ourworldindata.org/grapher/incomes-across-distribution-lis?decile=all&indicator=thr&period=year&welfare_type=dhi) and [UK Data Service ReShare](https://reshare.ukdataservice.ac.uk/855648/). Check those terms before reuse.
- **Japan (e-Stat)**: e-Stat terms are based on the Government of Japan Standard Terms of Use v2.0, which permit commercial use and modification and are compatible with CC BY 4.0. "Numerical data and data in simple tables, graphs... are not subject to copyright". — [e-Stat Terms of Use](https://www.e-stat.go.jp/en/terms-of-use); [Wikipedia: GoJ Standard Terms](https://en.wikipedia.org/wiki/Government_of_Japan_Standard_Terms_of_Use)
- **India (MoSPI PLFS)**: PLFS unit-level data (e.g. calendar year 2022) is published by MoSPI. GODL-India (Gazette, Feb 2017) allows using, adapting and publishing derivative works "for all lawful commercial and non-commercial purposes". — [MoSPI PLFS 2022](https://www.mospi.gov.in/PLFS-calendar-year-2022); [GODL-India](https://smartcities.data.gov.in/government-open-data-license-india). The PLFS download page's own licence statement was not checked. Applying GODL to it is an inference.
- **South Africa (Stats SA QLFS / LMDSA)**: users may process the data if Stats SA is acknowledged, but "neither the basic data nor any reprocessed version... may be sold or offered for sale... without prior permission". Since 2010, income is only in the annual LMDSA dataset. Some QLFS releases on the World Bank Microdata Library are listed as CC BY. — [Stats SA QLFS Q1 2026 metadata](https://isibaloweb.statssa.gov.za/metadata/QLFS/2026/Qtr01/Quarterly%20Labour%20Force%20Survey%201st%20Quarter%202026%20metadata.pdf); [World Bank microdata QLFS 2025](https://microdata.worldbank.org/index.php/catalog/6791)

### Inferences
- The safest global wage backbone is ILOSTAT (mean/median earnings by ISCO occupation and country) plus World Bank (GNI per capita, PPP, Gini/deciles from PIP). Both are CC BY 4.0, so a single NOTICE/ATTRIBUTION file is enough.
- For within-country shape (log-normal or Pareto tail parameters), fit to published percentiles. Use ONS ASHE (UK), BLS OEWS percentiles (US) and Eurostat SES/SILC aggregate deciles (EU). Bundle only the fitted parameters or quantile vectors.
- The Stats SA "no sale" clause is a real conflict with MIT/Apache, which permit sale. For South Africa, prefer the ILOSTAT/World Bank versions of SA statistics, which are CC BY, or ask Stats SA for permission.

### Gaps
- Brazil (IBGE PNAD Contínua) licence terms were not checked.
- The ILO's primary terms page could not be fetched, so ILOSTAT's licence rests on the re3data summary.

## Prices, consumer spending, retail seasonality, payment methods

### Takeaway
US CPI and CE (public domain) and Eurostat HICP/retail trade (reuse with attribution) can supply category weights and price levels. ECB SPACE and Fed DCPC publish payment-method shares directly as headline numbers.

### Cited Findings
- **BLS Consumer Expenditure Survey**: the 2024 annual tables and public-use microdata (Interview and Diary files, CSV/SAS/Stata) were released in 2025. They hold spending, income and demographics without identifiers, and are public domain like all BLS output. — [CE 2024 release notice](https://www.bls.gov/cex/notices/2025/annual-data-release-2024.htm); [PUMD data files](https://www.bls.gov/cex/pumd_data.htm); [BLS copyright](https://www.bls.gov/bls/linksite.htm)
- **ECB SPACE 2024 (euro area)**: cash was used in 52% of point-of-sale transactions by number (59% in 2022). By value, cards were 45% and cash 39%. Cash dominates small payments, and cards dominate payments over €50. 55% of consumers prefer non-cash payment. — [ECB SPACE 2024](https://www.ecb.europa.eu/stats/ecb_surveys/space/html/ecb.space2024~19d46f0f17.en.html)
- **Fed Diary of Consumer Payment Choice 2025 (data for Oct 2024)**: cash was 14% of payments by number, credit cards 35% and debit cards 30%. Consumers made 48 payments per month on average, 7 of them in cash. — [FRB Services 2025 DCPC findings](https://www.frbservices.org/news/research/2025-findings-from-the-diary-of-consumer-payment-choice); [press release](https://www.frbservices.org/news/press-releases/051325-findings-from-2025-diary-of-consumer-payment-choice/). A 2026 edition exists: [2026 DCPC](https://www.frbservices.org/news/fed360/issues/2026-diary-consumer-payment-choice-cash-essential-consumers/)
- **Eurostat HICP and retail trade**: covered by the general Eurostat reuse authorisation with source acknowledgement. — [Eurostat copyright notice](https://ec.europa.eu/eurostat/help/copyright-notice)

### Inferences
- Headline shares (ECB, Fed) are facts, not copyrightable expression. Encoding "card 45% / cash 39%" as a prior with a citation is low risk. The ECB's specific reuse notice was not checked.
- Purchase frequency and basket size can come from CE Diary PUMD (US) and from the CC BY Online Retail II dataset (UK, see the behavioural section).

### Gaps
- No source was fetched for US Census MARTS seasonal factors, Eurostat retail-trade seasonal indices, or ONS CPI basket weights. As US federal and Eurostat/ONS works they are presumably usable, but this was not verified.
- Price levels by category (Eurostat PPP/price-level indices) were not researched specifically.
- No payment-method share sources were found for India (UPI), Brazil (Pix), Japan or Africa (M-Pesa). Central-bank reports likely exist but were not checked.

## Names: first/last name frequencies by country and era

### Takeaway
Clean options exist for the US (SSA), the UK (ONS) and Brazil (IBGE Census 2022). For global coverage, Wikidata is CC0 but biased towards notable people. The popular "name-dataset" package is Apache-2.0 code built from the 533M-user Facebook leak, which is a provenance and privacy risk, not a licence-clean prior.

### Cited Findings
- **US SSA baby names**: name, year, sex and count from a 100% sample of SSA card applications, 1880–2025. Names with fewer than 5 occurrences are suppressed, and pre-1937 years are undercounted. — [data.gov SSA national data](https://catalog.data.gov/dataset/baby-names-from-social-security-card-applications-national-data). A CC0/public-domain status is stated by an aggregator, [namesovertime.com](https://namesovertime.com/us/en/data-sources/ssa-national/), and is consistent with US federal works, but the SSA page itself was not checked.
- **UK ONS baby names (England & Wales 2024)**: released 31 Jul 2025. Top names were Olivia (2,761 babies) and Muhammad (5,721). The full table has about 7,650 names (count ≥3), with an explorer back to 1996. — [GOV.UK release](https://www.gov.uk/government/statistics/baby-names-in-england-and-wales-2024); [ONS boys dataset](https://www.ons.gov.uk/peoplepopulationandcommunity/birthsdeathsandmarriages/livebirths/datasets/babynamesenglandandwalesbabynamesstatisticsboys). Licence: OGL (ONS standard, see the ASHE note above).
- **Brazil IBGE "Nomes no Brasil" (Census 2022)**: more than 140k given names and 200k surnames, searchable by sex, decade of birth and locality. Silva covers nearly 17% of the population. The API reports frequency by birth decade, with disclosure thresholds of ≥10 per municipality, 15 per state and 20 nationally. — [IBGE 2025 announcement](https://www.ibge.gov.br/novo-portal-destaques/44653-ibge-divulgara-em-4-de-novembro-de-2025-censo-demografico-2022-nomes-no-brasil.html); [IBGE Names API docs](https://servicodados.ibge.gov.br/api/docs/nomes?versao=2). The "CC BY-SA" licence in search results belongs to a third-party processed repo ([turicas/genero-nomes](https://github.com/turicas/genero-nomes)), not to IBGE. IBGE's own terms were not checked.
- **Wikidata**: all structured data in the main, Property and Lexeme namespaces is CC0. P735 is given name and P734 is family name. — [Wikidata:Copyright](https://www.wikidata.org/wiki/Wikidata:Copyright); [P734](https://www.wikidata.org/wiki/Property:P734)
- **philipperemy/name-dataset**: 730k first names and 983k last names across 105 countries with gender and counts, "extracted from the Facebook massive dump (533M users)". Released under Apache-2.0. — [GitHub name-dataset](https://github.com/philipperemy/name-dataset); [PyPI](https://pypi.org/project/names-dataset/)
- **sigpwned popular-names-by-country**: an alternative compiled from Wikipedia lists. — [README](https://github.com/sigpwned/popular-names-by-country-dataset/blob/main/README.md). Its licence was not checked, and Wikipedia text is CC BY-SA.

### Inferences
- The Apache-2.0 label on name-dataset covers the authors' compilation. The data comes from a 2021 breach of personal data, and bundling distilled frequencies from it could draw GDPR and reputational criticism. Prefer official sources plus Wikidata for the top-N names per country, and treat name-dataset as optional and user-installed.
- Era associations: SSA (US, by year), ONS (E&W since 1996) and IBGE (birth decade) all support "name given birth year" sampling.

### Gaps
- No official, openly licensed name-frequency sources were found for India, Japan, Germany, France or Nigeria/Kenya/South Africa. Some national offices publish them (e.g. Statistics Netherlands, INSEE's "Fichier des prénoms"), but these were not researched here.

## Addresses and geography

### Takeaway
GeoNames (CC BY 4.0) and Natural Earth (public domain) are clean to bundle. OSM (ODbL) aggregate statistics count as "Produced Works", which need only attribution, as long as the bundle cannot be used to extract OSM features. Shipping extracted OSM features (e.g. street-name lists), in more than an insubstantial amount, creates a share-alike derivative database. OpenAddresses licences vary per source.

### Cited Findings
- **GeoNames postal codes (allCountries.zip) and gazetteer**: CC BY 4.0. — [GeoNames postal readme](http://download.geonames.org/export/zip/readme.txt); [gazetteer readme](http://download.geonames.org/export/dump/readme.txt)
- **Natural Earth**: "All versions of Natural Earth raster + vector map data... are in the public domain". Commercial use is allowed and credit is unnecessary. — [Natural Earth Terms of Use](https://www.naturalearthdata.com/about/terms-of-use/)
- **OSM/ODbL**: a Produced Work is something created from the database that is not itself a database. If it is used to extract or recreate substantial parts of OSM, it counts as a Derivative Database. Fewer than 100 features, extracted one-off, is regarded as not substantial, and repeated small extractions count as one. — [OSMF Substantial guideline](https://osmfoundation.org/wiki/Licence/Community_Guidelines/Substantial_-_Guideline); [OSMF Produced Work guideline](https://osmfoundation.org/wiki/Licence/Community_Guidelines/Produced_Work_-_Guideline); [ODbL 1.0 text](https://opendatacommons.org/licenses/odbl/1-0/); [OSMF attribution guidelines](https://osmfoundation.org/wiki/Licence/Attribution_Guidelines)
- **OpenAddresses**: data is not relicensed. Each source keeps its own licence, most need only attribution, and a few are share-alike. Downloads come in separate "attribution" and "share-alike" bundles. — [OpenAddresses attribution](https://openaddresses.io/attribution/); [results/download](https://results.openaddresses.io/); [GitHub](https://github.com/openaddresses/openaddresses)
- **Eurostat GISCO postal codes**: a candidate source for EU postcode-to-NUTS mapping. — [GISCO postal codes](https://ec.europa.eu/eurostat/en/web/gisco/geodata/administrative-units/postal-codes). Its licence was not checked.

### Inferences
- Postcode formats are facts and regex patterns, not copyrightable data, so the package can write them itself. City/postcode/population tables from GeoNames go into the package with a "© GeoNames, CC BY 4.0" notice.
- Street-name vocabularies are the riskiest item. Building them from OSM triggers ODbL share-alike, so use the CC BY or public-domain subsets of OpenAddresses, or generate street names grammatically.

### Gaps
- Whether statistics such as "street-type suffix frequency per country" from OSM count as Produced Works has not been tested by OSMF. Ask on legal-talk or avoid it.

## Business demographics

### Takeaway
OECD SDBS (CC BY 4.0), Eurostat SBS (reuse with attribution) and US Census SUSB (US federal) give firm counts, employment and turnover by size class and industry (ISIC/NACE/NAICS). OECD business demography adds birth and death rates for company lifespans.

### Cited Findings
- **OECD SDBS**: data by ISIC Rev.4 at the 4-digit level and by enterprise size class: number of units, employment, value added, turnover and labour costs. The business demography dataflow covers enterprise births and deaths. — [OECD Data Explorer SBS by size class](https://data-explorer.oecd.org/vis?bp=true&df%5Bag%5D=OECD.SDD.TPS&df%5Bds%5D=dsDisseminateFinalDMZ&df%5Bid%5D=DSD_SDBSBSC_ISIC4%40DF_SDBS_ISIC4&df%5Bvs%5D=1.0&dq=A..ENTR+TUTT.C._T+S1T249+S_GE250.&lc=en&ly%5Bcl%5D=TIME_PERIOD%2CSIZE_CLASS&ly%5Brs%5D=MEASURE&ly%5Brw%5D=REF_AREA&pd=2018%2C&pg=0&snb=2&tm=sdbs&to%5BTIME_PERIOD%5D=false); [OECD business demography birth/death](https://data-explorer.oecd.org/vis?lc=en&df%5Bds%5D=dsDisseminateFinalDMZ&df%5Bid%5D=DSD_SDBSBD_ISIC4%40DF_BD_B_D&df%5Bag%5D=OECD.SDD.TPS&df%5Bvs%5D=1.0); [Enterprises by business size](https://www.oecd.org/en/data/indicators/enterprises-by-business-size.html). Licence: CC BY 4.0 per [OECD T&C](https://www.oecd.org/en/about/terms-conditions.html).
- **Eurostat SBS**: metadata at [sbs_esms](https://ec.europa.eu/eurostat/cache/metadata/en/sbs_esms.htm). Reuse is authorised with acknowledgement per the [Eurostat copyright notice](https://ec.europa.eu/eurostat/help/copyright-notice).
- **US Census SUSB 2022**: firms, establishments, employment, payroll and receipts by NAICS, geography and enterprise size. There were 5.52M employer firms with 1–499 employees in 2022. — [SUSB 2022 annual tables](https://census.gov/data/tables/2022/econ/susb/2022-susb-annual.html); [SUSB datasets](https://www.census.gov/programs-surveys/susb/data/datasets.html)

### Inferences
- Firm-size priors can be a per-country table of shares by size class (1–9, 10–49, 50–249, 250+) by NACE section. That is tiny to ship.
- Company lifespan can be approximated from OECD birth/death rates and survival rates (geometric or Weibull fit).

### Gaps
- Non-OECD firm-size data (India MSME census, Brazil IBGE CEMPRE, Nigeria/Kenya) was not researched. The World Bank Enterprise Surveys are a candidate, but their licence was not checked.

## Behavioural patterns: sessions, conversion, churn, tickets, hourly/weekday profiles

### Takeaway
This is the weakest domain for open data. Online Retail II (UCI, CC BY 4.0) is the one clearly commercial-safe transactional dataset. Olist (CC BY-NC-SA) and Instacart (non-commercial) restrict commercial use. No authoritative open sources were found for churn rates, conversion rates, session timing or support-ticket volumes.

### Cited Findings
- **Online Retail II (UCI)**: CC BY 4.0, 1,067,371 transactions from a UK non-store online retailer, Dec 2009 – Dec 2011, DOI 10.24432/C5CG6D. It covers invoice timestamps (hour/weekday), basket sizes, repeat purchase and country mix. — [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii)
- **Olist Brazilian E-commerce**: about 100k orders 2016–2018, with payments (incl. boleto, instalments), freight, reviews and customer location. Licence CC BY-NC-SA 4.0. — [Kaggle Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
- **Instacart 2017**: more than 3M grocery orders from more than 200k users, with order hour-of-day, day-of-week and days since prior order. Released "for non-commercial use" under Instacart's terms. — [Instacart tech blog](https://tech.instacart.com/3-million-instacart-orders-open-sourced-d40d29ead6f2?gi=38a6e5891186)

### Inferences
- NC and NC-SA licences conflict with MIT/Apache, which allow commercial use. Whether a handful of fitted parameters (e.g. Instacart's hour-of-day histogram) is a copyrightable adaptation is legally debatable, since bare facts are generally not protected. A conservative package should not claim those numbers derive from NC data. Use Online Retail II for hour/weekday and basket priors, and Fed DCPC/ECB SPACE for payment frequency.
- Churn, conversion and ticket-volume priors probably need hand-set, documented ranges citing published industry studies, stated as "assumption" rather than "data".

### Gaps
- No open, licence-clear datasets were found for web/app session timing, e-commerce conversion rates, churn by industry or support-ticket volumes. Searches were not done exhaustively due to call budget. Candidates to check: ATUS (American Time Use Survey, BLS, public domain) for hourly activity profiles, Wikimedia pageview dumps (CC0) for diurnal web traffic, and UK ONS time-use surveys.

## Healthcare: Synthea, ICD-10, prescribing, vital signs

### Takeaway
Synthea modules (Apache 2.0) and NHS prescribing data (OGL) are bundle-friendly. NHANES is a US federal public-use file, presumably public domain. ICD-10 and ICD-11 code lists are CC BY-ND 3.0 IGO: the code tables can be redistributed verbatim with attribution, but WHO forbids adaptations such as translations without permission.

### Cited Findings
- **Synthea**: Java tool under Apache 2.0. Its Generic Module Framework JSON modules cover conditions, medications, vitals, labs and SDOH, and its output is "free from cost, privacy, and security restrictions". Locale configs for non-US countries are in synthea-international. — [Synthea GitHub org](https://github.com/synthetichealth); [synthea-international](https://github.com/synthetichealth/synthea-international); [module-builder](https://github.com/synthetichealth/module-builder)
- **ICD-11**: CC BY-ND 3.0 IGO. WHO does not treat incorporating ICD-11 into software as an adaptation, unless you redistribute it under a different name or without attribution. — [ICD-11 License](https://icd.who.int/icdapi/docs2/license/)
- **ICD-10**: CC BY-ND 3.0 IGO, with no adaptations (incl. translations) without WHO permission. — [WHO ICD-10 licensing FAQ](https://cdn.who.int/media/docs/default-source/publishing-policies/copyright/who-faq-licensing-icd-10.pdf?sfvrsn=b2c8a69a_0)
- **NHS English Prescribing Dataset (NHSBSA)**: monthly data on all primary-care prescriptions dispensed in England since Jan 2014. OpenPrescribing uses it "under the terms of the Open Government Licence". — [OpenPrescribing About](https://openprescribing.net/about/); [NHSBSA EPD](https://opendata.nhsbsa.net/dataset/english-prescribing-data-epd) (the original EPD page is marked RETIRED; there is a successor [EPD with SNOMED code](https://opendata.nhsbsa.net/dataset/english-prescribing-dataset-epd-with-snomed-code)).
- **NHANES**: 2-year public-use files incl. Body Measures (BMX) and Blood Pressure (BPX). — [NHANES BPX 2017–18 doc](https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/BPX_J.htm); [NHANES tutorials](https://wwwn.cdc.gov/nchs/nhanes/tutorials/datasets.aspx)

### Inferences
- A table of code frequencies (code, share) that cites WHO and does not rename codes fits the ICD-11 software allowance. The package should not ship modified or translated ICD titles. US ICD-10-CM (CDC/CMS) is a US-government modification and may be public domain, but this was not verified.
- The NHANES licence was not confirmed directly. US federal works are generally not copyrighted (17 U.S.C. §105), consistent with BLS's statement above. Cite NCHS anyway.

### Gaps
- No open sources for ICD-10 code frequency (e.g. NHS Hospital Episode Statistics, CDC mortality) were fetched. NHS Digital HES summary tables (OGL) are a likely candidate.

## Licence implications for bundling distilled statistics

### Takeaway
Permissive tier, safe to bundle with a NOTICE file: public domain/US federal works (BLS, Census, SSA, NHANES), CC0 (Wikidata), Natural Earth, CC BY 4.0 (OECD, World Bank, ILOSTAT, GeoNames, UCI Online Retail II, Eurostat), OGL v3 (ONS, NHSBSA), GoJ Standard Terms 2.0 (e-Stat) and GODL-India. Conditional tier: ODbL is fine for aggregate Produced Works with attribution, but extracted features are share-alike. CC BY-ND (ICD) allows verbatim copies only. Avoid tier: non-commercial licences (Olist, Instacart), "no-sale" clauses (Stats SA) and restricted microdata (LIS, EU-SILC SUFs).

### Cited Findings
- CC BY 4.0 allows sharing and adaptation for any purpose, incl. commercial, with credit, and excludes third-party material. — [OECD CC BY 4.0 explainer](https://www.oecd.org/en/publications/access-to-public-research-data-toolkit_a12e8998-en/the-creative-commons-attribution-4-0-international-cc-by-4-0_723b36be-en.html)
- GoJ Standard Terms 2.0 are CC BY 4.0-compatible. — [e-Stat Terms](https://www.e-stat.go.jp/en/terms-of-use)
- GODL-India permits derivative commercial products. — [GODL-India](https://smartcities.data.gov.in/government-open-data-license-india)
- ODbL Produced Works need only attribution unless they enable extraction. — [OSMF Produced Work guideline](https://osmfoundation.org/wiki/Licence/Community_Guidelines/Produced_Work_-_Guideline)
- Compatibility of OSM with other licences. — [OSMF Licence Compatibility](https://osmfoundation.org/wiki/Licence/Licence_Compatibility)
- World Bank requires a specific attribution format and no implied endorsement. — [World Bank Datasets terms](https://www.worldbank.org/ext/en/legal/terms-conditions/datasets)

### Inferences
- Data licences do not change the package's code licence. Ship the priors under their source licences, as an `ATTRIBUTION.md` or `NOTICE` listing source, licence, URL, retrieval date and transformation, which CC BY's "indicate changes" clause requires. MIT/Apache code can coexist with CC BY or OGL data files.
- Keep CC BY-SA and ODbL derivatives (if any) in a separate optional data package so the core stays permissive.
- Distilled statistics (quantiles, shares) are largely facts. In the EU, though, the sui generis database right could still apply to substantial extraction. That is why relying on explicit licences rather than a "facts are free" argument is the prudent path.

### Gaps
- No legal opinion was found on whether fitted distribution parameters from an NC dataset are "adapted material" under CC BY-NC. Treat it as unresolved.
- The ECB's and IBGE's specific data-reuse licences were not verified.
