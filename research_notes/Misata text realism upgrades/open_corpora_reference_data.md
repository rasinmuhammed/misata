# Open corpora and reference data for an MIT-licensed synthetic-data library (Misata)

Research method note: direct fetches of most primary pages (geonames.org, huggingface.co, onetcenter.org, yelp.com, amazon-reviews-2023.github.io) were blocked by the sandbox egress proxy on 2026-10-03, so most findings come from search-result extracts of the primary pages (URLs cited are the primary pages where the search engine surfaced them). Items marked "(unverified, prior knowledge)" were not confirmed in this session and must be checked before relying on them. Nothing here is legal advice.

## Geography: GeoNames, OpenAddresses, OSM, Natural Earth, SimpleMaps, US Census, Eurostat

### Takeaway
GeoNames (CC BY 4.0) is the best single source for ship-able city tables with population, admin1 regions and postal codes; Natural Earth (public domain) is the zero-obligation fallback for a few thousand populated places. Avoid shipping anything derived from OSM/Nominatim or OpenAddresses in the wheel: ODbL share-alike and per-source licences turn a bundled table into a Derivative Database that has to stay under ODbL.

### Cited Findings
- GeoNames data is "licensed under a Creative Commons Attribution 4.0 License". It can be used for free, including commercially, if you credit GeoNames (a link to www.geonames.org is enough). — [About GeoNames](https://www.geonames.org/about.html); [GeoNames export](https://www.geonames.org/export)
- GeoNames cities15000 covers more than 33,000 cities with population ≥15,000. Each row has the GeoNames ID, name, ASCII name, country code, admin1 code, population, coordinates and timezone. Download: https://download.geonames.org/export/dump/cities15000.zip (smaller-threshold files cities500/1000/5000 sit in the same dump directory). — [GeoNames export](http://download.geonames.org/export/); [Trailtale issue summarising cities15000](https://github.com/maestroDev3/Trailtale/issues/115)
- GeoNames publishes a daily dump (allCountries.zip). Postal codes are a separate download, and for CA, NL and UK the postal files hold only the first part of the code. They are tab-delimited UTF-8 with country code, postal code, place name, admin names/codes, lat and lon. Postal codes are also CC BY. — [GeoNames postal readme](http://download.geonames.org/export/zip/readme.txt); [GeoNames export](https://www.geonames.org/export)
- OpenAddresses: "The license for each individual source within OpenAddresses differs, with many of the sources requiring attribution and others having a share-alike clause". The pipeline output is not relicensed, and users must research each source's licence themselves. — [OpenAddresses GitHub](https://github.com/openaddresses/openaddresses); [geocode.earth data sources](https://geocode.earth/docs/reference/data_sources/)
- ODbL definitions: a "Derivative Database" includes "Extracting or Re-utilising the whole or a Substantial part of the Contents in a new Database". A "Produced Work" is a work such as an image, text or sound that results from using the database. — [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/)
- OSMF guideline: "If the published result of your project is intended for the extraction of the original data, then it is a database and not a Produced Work." Database dumps are usually not Produced Works. — [OSMF Produced Work guideline](https://osmfoundation.org/wiki/Licence/Community_Guidelines/Produced_Work_-_Guideline)
- Natural Earth: "All versions of Natural Earth raster + vector map data … are in the public domain." No permission is needed and credit is unnecessary. Populated Places is a point dataset at 10m/50m/110m scales. — [Natural Earth Terms of Use](https://www.naturalearthdata.com/about/terms-of-use/)
- SimpleMaps Basic World Cities Database: CC BY 4.0, ~50.2k "prominent cities", free with attribution. Non-US data comes from NGA and US data from the Census Bureau/USGS. Paid tiers have their own licence. — [SimpleMaps World Cities](https://simplemaps.com/data/world-cities); [SimpleMaps License](https://simplemaps.com/data/license)

### Inferences
- **City frequency proportional to population:** use cities15000 (or cities5000 for denser coverage). Group by country_code, then weight = population / sum(population in country). Ship a pre-normalised `(country, admin1, city, ascii_name, weight)` table. A CC BY 4.0 adaptation may be redistributed under MIT for the code, but the data file needs a NOTICE/ATTRIBUTION entry ("Contains data from GeoNames, CC BY 4.0, www.geonames.org; modified: filtered, normalised"). CC BY has no share-alike, so this is compatible with an MIT package. The data file itself stays CC BY, so state that in the package metadata/NOTICE.
- **Size estimate:** cities15000 at roughly 33k rows × ~60 bytes is about 2 MB raw and well under 1 MB compressed. A top-N-per-country cut (say 200 cities × 250 countries) would be smaller still. Either fits a 5-20 MB wheel budget easily. allCountries (multi-GB) and full postal codes should be an optional fetch.
- **Postal codes:** ship only format patterns per country (regex/templates, which carry no copyright) plus perhaps a small sample. Offer the GeoNames postal file as an optional download.
- **OSM/Nominatim, OpenAddresses:** treat as optional, user-initiated fetches only. A bundled street-name frequency table extracted from OSM is very likely a Derivative Database under ODbL, because it is intended to allow extraction of the data. It would force ODbL on that file and attribution to "© OpenStreetMap contributors". Shipping an ODbL file inside an MIT wheel is legally possible if it is clearly separated and labelled, but it complicates downstream use. Avoid it.
- **US Census Gazetteer** (places with population) and **Eurostat/GISCO**: US federal works are generally public domain. Eurostat reuse is under the Commission reuse decision (see the ESCO section), which is attribution-only, but GISCO geodata carries extra copyright notices (unverified, prior knowledge).

### Gaps
- I could not fetch the GeoNames dump readme directly (egress blocked). Exact cities500/1000/5000 row counts and file sizes are not confirmed.
- Not verified this session: US Census Gazetteer files URL/terms, Eurostat GISCO licence specifics, and the exact current SimpleMaps attribution wording.
- No court or legal analysis was found on whether aggregated frequency tables (e.g. street-name counts) from ODbL data are "Substantial" extractions. The OSMF guideline is the best available interpretation.

## Names: SSA, US Census surnames, name-dataset, Wikidata, gender/culture distributions

### Takeaway
SSA baby names (CC0/US public domain) and the Census 2010 surname file (US government, aggregated) are safe to ship as derived frequency tables. philipperemy/name-dataset is a serious trap: it was extracted from the 2021 Facebook leak of 533M users, so it is leaked PII whatever "names aren't copyrightable" says. Do not ship or recommend it.

### Cited Findings
- SSA national baby names: name, year, sex and count from a 100% sample of SSA card applications, 1880 through 2025, updated annually. Download: ssa.gov/oact/babynames/names.zip (one yobYYYY.txt per year). Names with fewer than 5 occurrences are suppressed. The data.gov catalogue lists it as public domain (CC0). — [data.gov SSA national data](https://catalog.data.gov/dataset/baby-names-from-social-security-card-applications-national-data); [namesovertime SSA summary](https://namesovertime.com/us/en/data-sources/ssa-national/)
- Census 2010 surnames: every surname occurring 100 or more times, 162,253 names. Each row has frequency, rank and race/Hispanic-origin percentages, available as CSV/Excel. Aggregates only, no individual information. — [Census Frequently Occurring Surnames 2010](https://census.gov/topics/population/genealogy/data/2010_surnames.html); [Census surname API](https://www.census.gov/data/developers/data-sets/surnames.html)
- philipperemy/name-dataset: code is Apache-2.0. The data (730K first names, 983K last names, 491M records, 106 countries, 3.3 GB compressed) was "extracted from the massive Facebook dump (533M users)". The README says lists of names are "not copyrightable, generally speaking" but recommends consulting a lawyer. — [name-dataset GitHub](https://github.com/philipperemy/name-dataset)
- Faker (MIT) builds locale data from community pull requests and documents sources per provider (e.g. Italian words from napolux/paroleitaliane, es_ES company names "inspired by" Wikipedia rankings). — [Faker GitHub](https://github.com/joke2k/faker); [Faker it_IT docs](https://faker.readthedocs.io/en/master/locales/it_IT.html); [Faker es_ES docs](https://faker.readthedocs.io/en/master/locales/es_ES.html)

### Inferences
- **US first names:** ship a gender-split weight table for a recent window (e.g. birth years 1950-2005, weighted by age pyramid if age is generated). The top ~5k names per sex cover the vast majority of mass. That is about 100-200 KB. Ship it under CC0 with a courtesy credit.
- **US surnames:** ship the top 10-20k Census 2010 surnames with counts. The race/ethnicity columns allow culture-correlated name pairing (e.g. joint first/last plausibility), but note the ethical sensitivity of that.
- **Non-US names:** the cleanest route is Wikidata given-name/family-name items (Wikidata structured data is CC0, unverified, prior knowledge), plus national statistics offices that publish name frequency tables (e.g. INE Spain, ONS UK, Statistics Netherlands/Meertens). Each has its own terms, unverified this session. Faker/Mimesis locale lists are MIT and can be reused with attribution, but they mostly lack frequency weights.
- **name-dataset:** even if facts are not copyrightable in the US, EU GDPR and leaked-data provenance make it reputationally and legally risky. It also may carry sui generis database rights in the EU. Flag it as "do not use".

### Gaps
- Wikidata CC0 status and a SPARQL recipe for name frequency per country were not verified this session.
- No verified per-country official name-frequency sources were gathered, given the tool budget.

## Product text: Amazon Reviews, Open Food Facts, Icecat, Wikidata products

### Takeaway
Amazon Reviews 2023 has no licence (the lab says it cannot assign one, "primarily for research purposes"), so do not ship derived text. Use it at most as a user-run optional fetch. Open Food Facts is legally usable (ODbL + DbCL, images CC BY-SA) but is share-alike. Safer: ship hand-written or LLM-generated templates and seed vocab from CC0/public sources, and offer OFF as an optional fetch.

### Cited Findings
- McAuley Lab on Amazon-Reviews-2023: they are "not in a position to assign a license to this dataset or dictate the terms of its usage". It is made available "primarily for research purposes", and users must follow legal and ethical standards. Third-party mirrors claim "CC0" (Kaggle) or "academic, non-commercial research use only", which conflict. — [HF discussion: Dataset License?](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/discussions/1); [Kaggle mirror](https://www.kaggle.com/datasets/wajahat1064/amazon-reviews-data-2023)
- Open Food Facts: database under ODbL, individual contents under the Database Contents License (DbCL), product images CC BY-SA. Commercial use is allowed under attribution and share-alike. Combining OFF data with other databases requires the resulting database to be open too. Exports are at world.openfoodfacts.org/data, also on Hugging Face (openfoodfacts/product-database) and AWS. — [OFF data](https://world.openfoodfacts.org/data); [OFF terms](https://world.openfoodfacts.org/terms-of-use); [HF OFF README](https://huggingface.co/datasets/openfoodfacts/product-database/blob/main/README.md)

### Inferences
- **Amazon Reviews (2018/2023):** the review text was written by Amazon users and is © them/Amazon, under Amazon ToS. "No licence" means default all-rights-reserved. Shipping n-gram or phrase banks with distinctive phrases risks reproducing copyrighted expression. Only very high-frequency short n-grams (generic phrases like "works great") would plausibly be non-protectable, and even that rests on an unsettled fair-use argument. Recommendation: do not ship. Optional user fetch only, with a clear warning.
- **Open Food Facts:** good for product names, brands, categories and ingredients (food domain). A frequency table of category labels is plausibly a Derivative Database under ODbL, so ship it as a separate ODbL-licensed data file with attribution, or make it an optional fetch (preferred).
- **Icecat** open catalogue, **Best Buy** API, **Open Product Data (POD)**: not verified this session. Best Buy's developer API terms are generally restrictive about storage and redistribution (unverified, prior knowledge). Icecat "Open Icecat" has its own terms (unverified).
- **Wikidata products/brands:** CC0 (unverified this session) makes it the best ship-able source for brand names and product-category taxonomies. Note that brand names are trademarks. Using them in fake data is generally fine, but avoid implying endorsement.

### Gaps
- I could not open the amazon-reviews-2023.github.io page (egress blocked) to quote any terms it currently shows.
- Icecat, Best Buy, Open Product Data and GS1 licence details were not verified.

## Reviews and opinions: Yelp, IMDb, Amazon, TripAdvisor — redistribution of derived phrase banks

### Takeaway
None of the major review corpora allow redistributing derived phrase banks in a commercially usable MIT package. Yelp is academic-only (2023 terms), IMDb is personal/non-commercial with no republishing, and Amazon has no licence. Review text realism should come from original templates, CC0/CC-BY corpora, or small models trained only by end users locally.

### Cited Findings
- Yelp Dataset Terms of Use (last updated July 7, 2023) grant a "royalty-free, non-exclusive, revocable, non-sublicensable, non-transferable … license to use, access, and create derivative works of the Data … solely for academic use." Earlier 2020/2021 versions also allowed narrowly defined "non-commercial" use by nonprofits, government and educational bodies. — [Yelp Terms 2023 PDF](https://s3-media0.fl.yelpcdn.com/assets/srv0/engineering_pages/f64cb2d3efcc/assets/vendor/Dataset_User_Agreement.pdf); [Yelp Terms 2021 PDF](https://s3-media0.fl.yelpcdn.com/assets/srv0/engineering_pages/dc1cabe7cb95/assets/vendor/Dataset_User_Agreement.pdf); [Yelp Open Dataset page](https://business.yelp.com/data/resources/open-dataset/)
- IMDb non-commercial datasets are for "personal and non-commercial use". They "must not be altered/republished/resold/repurposed to create any kind of online/offline database", and require the attribution "Information courtesy of IMDb … Used with permission." They are refreshed daily at datasets.imdbws.com. — [IMDb developer: non-commercial datasets](https://developer.imdb.com/non-commercial-datasets); [IMDb Help: Can I use IMDb data](https://help.imdb.com/article/imdb/general-information/can-i-use-imdb-data-in-my-software/G5JTRESSHJBBHTGX)
- Amazon reviews: no licence assigned (see the Product text section). — [HF discussion](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/discussions/1)

### Inferences
- Yelp "solely for academic use" excludes shipping anything derived in an MIT package that commercial users install. Treat Yelp as forbidden even as an "optional fetch helper", because the helper would invite non-academic use.
- IMDb: no shipping and no fetch helper (non-commercial).
- TripAdvisor: no official open dataset was found. Scraped Kaggle copies violate TripAdvisor ToS (not verified this session). Avoid.
- The "IMDB movie reviews" sentiment dataset (Maas et al., Stanford) is a different thing from IMDb's datasets. Its licence status is unclear (unverified).
- **Safe pattern:** an original phrase bank written by the maintainers or generated by an LLM whose output terms allow it, organised by sentiment × aspect × domain, with slot-filling from ship-able vocab (product nouns from Wikidata/OFF categories). Optionally train tiny Markov/n-gram models at runtime on a corpus the user supplies.

### Gaps
- Licence status of the Stanford IMDB sentiment corpus, the Amazon polarity (Zhang et al.) corpus, and TripAdvisor research datasets was not verified.

## Customer support / tickets / chat: Bitext, Twitter support, ABCD, MultiWOZ, Taskmaster, IT incidents

### Takeaway
Permissive options exist. MultiWOZ and ABCD are MIT (repo), and Taskmaster is CC BY 4.0, so intents, slot values and short utterance templates derived from them can ship with attribution. Bitext is CDLA-Sharing 1.0 (share-alike for the data, compatible with commercial use). The Twitter Customer Support (Kaggle) set is CC BY-NC-SA 4.0 and contains real users' tweets, so it is a non-commercial + share-alike + PII trap.

### Cited Findings
- The Bitext customer-support LLM chatbot dataset is licensed **cdla-sharing-1.0**. Derivatives of the data must be shared under the same licence, with attribution. Sibling Bitext sets cover banking, hospitality, restaurants, insurance, mortgage, events ticketing and retail e-commerce. — [Bitext HF discussions](https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset/discussions); [Bitext retail banking HF](https://huggingface.co/datasets/bitext/Bitext-retail-banking-llm-chatbot-training-dataset)
- "Customer Support on Twitter" (thoughtvector, Kaggle): about 2.8M tweets and replies, CC BY-NC-SA 4.0. — [Kaggle](https://www.kaggle.com/datasets/thoughtvector/customer-support-on-twitter)
- ABCD (ASAPP Action-Based Conversations Dataset) is MIT licensed. — [asappresearch/abcd](https://github.com/asappresearch/abcd)
- MultiWOZ is released under the MIT licence (GitHub). The Cambridge repository deposit is labelled CC BY 4.0, so the two sources conflict. Both are permissive. — [budzianowski/multiwoz](https://github.com/budzianowski/multiwoz); [Cambridge repository](https://www.repository.cam.ac.uk/items/74e8d468-9442-424a-bb3b-1bb88dcb8673)
- Taskmaster-1: 13,215 task-based dialogs in 6 domains. Across TM-1/2/3 there are over 55,000 dialogs in a dozen+ domains, under CC BY 4.0. — [Taskmaster GitHub](https://github.com/google-research-datasets/Taskmaster); [GEM Taskmaster card](https://gem-benchmark.com/data_cards/Taskmaster); [Google AI blog](https://ai.googleblog.com/2019/09/announcing-two-new-natural-language.html)

### Inferences
- **Ship:** an intent taxonomy plus short paraphrase templates derived from ABCD/MultiWOZ (MIT) and Taskmaster (CC BY 4.0, attribution in NOTICE). A few hundred templates per domain is about 100s of KB.
- **Bitext:** CDLA-Sharing's share-alike applies to the data (and to "Enhanced Data"), not to software that uses the data. Shipping a Bitext-derived template file means that file must stay CDLA-Sharing-1.0 with attribution. That is acceptable if it is kept as a separately licensed data file, but cleaner as an optional fetch from HF. The 27-intent/11-category taxonomy itself (labels only) is low risk.
- **Twitter support:** do not ship anything. NC conflicts with an MIT library's commercial users, SA conflicts with MIT, and the tweets carry real handles/PII plus X/Twitter developer terms on redistributing tweet content.
- **IT incident data:** no openly licensed real ServiceNow/Microsoft incident corpus was found in this session. ServiceNow demo-instance data falls under ServiceNow terms (unverified). Recommend generating ITSM tickets from ITIL-style category/priority taxonomies plus templates, or Synthea-style simulation.

### Gaps
- The exact CDLA-Sharing-1.0 clause text was not fetched. The interpretation above comes from the licence's general summary.
- No verified open IT incident/ticket corpus was found. A UCI "Incident management process event log" dataset exists (unverified licence, likely CC BY 4.0, from prior knowledge).

## Job titles, companies, industries: O*NET, ESCO, SEC EDGAR, OpenCorporates

### Takeaway
O*NET (CC BY 4.0, current release 31.0) and ESCO (EU reuse decision 2011/833/EU, attribution only, commercial OK) are both ship-able sources for job titles, alternate titles and skills. SEC EDGAR company names are US government public data. OpenCorporates is ODbL share-alike with mandatory "from OpenCorporates" hyperlinks, so it is a trap for bundling.

### Cited Findings
- The O*NET Database (USDOL/ETA) is licensed CC BY 4.0. Verbatim use: "Used under the CC BY 4.0 license. O*NET® is a trademark of USDOL/ETA." Modified use: "includes information from the O*NET 31.0 Database by USDOL/ETA", and you must indicate the modifications. Current version is 31.0. — [O*NET Database Content License](https://www.onetcenter.org/license_db.html); [O*NET Database](https://www.onetcenter.org/database.html)
- ESCO: under Commission Decision 2011/833/EU, ESCO "can be downloaded, used, reproduced and reused for any purpose and by any interested party free of charge". Conditions are to acknowledge the source, not distort the meaning, and accept no Commission liability. — [ESCO FAQ](https://esco.ec.europa.eu/fr/about-esco/faq); [Decision 2011/833/EU](https://eur-lex.europa.eu/LexUriServ/LexUriServ.do?uri=OJ:L:2011:330:0039:0042:EN:PDF)
- SEC EDGAR: company_tickers.json (~780 KB, ~10k tickers) at https://www.sec.gov/files/company_tickers.json. A nightly bulk ZIP is published around 3:00 a.m. ET. Fair access is 10 requests/s per IP with a declared User-Agent (Company email). — [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces); [SEC company tickers](https://www.sec.gov/file/company-tickers)
- OpenCorporates bulk data is under ODbL share-alike. Use must carry a "from OpenCorporates" hyperlink. A non-share-alike licence can be bought. — [OpenCorporates terms](https://opencorporates.com/terms-of-use-2/); [OpenCorporates API](https://api.opencorporates.com/)

### Inferences
- **Ship:** O*NET occupation titles + Alternate Titles + Sample of Reported Titles (tens of thousands of titles, around 1-3 MB raw, unverified size), mapped to SOC major groups for industry correlation. Include the required attribution text in NOTICE and docs. ESCO occupations (~3k) and alternative labels in ~28 languages give multilingual job titles. Ship a single-language subset and fetch the others optionally.
- **Company names:** use EDGAR names only for statistics (suffix distribution such as Inc/LLC/Corp, token frequencies). Do not emit real company names as fake data, because that is confusing and has trademark implications. A generated "Word + Word + suffix" scheme calibrated on EDGAR token frequencies is safe. US federal works carry no copyright (17 U.S.C. §105; unverified this session but standard).
- **Industry codes:** NAICS/SIC (US government) and NACE (Eurostat) are ship-able taxonomies (unverified licence pages this session).
- **OpenCorporates:** optional fetch only, never bundled.

### Gaps
- The O*NET file sizes and title counts for the 31.0 release were not verified.
- The ESCO portal's own download terms page and current version (v1.2.x?) were not fetched.

## Medical, clinical notes and legal text: MIMIC, MTSamples, Synthea

### Takeaway
Synthea (Apache-2.0 code, synthetic output) is the only clean source for ship-able clinical structure (conditions, meds, encounters). MIMIC is credentialed-access with a data use agreement that forbids redistribution. MTSamples has no open licence, and the widely used Kaggle scrape is a copyright/ToS grey area. Do not ship.

### Cited Findings
- Synthea is licensed Apache License 2.0 (MITRE). It generates synthetic, realistic patient records "free from cost, privacy, and security restrictions". Sample downloads of 100 or 1,000 patients come in C-CDA, CSV and FHIR R4/STU3/DSTU2. An OMOP version is on the AWS Open Data registry. — [Synthea GitHub](https://github.com/synthetichealth/synthea); [Synthea downloads](https://synthea.mitre.org/downloads); [AWS Synthea OMOP](https://registry.opendata.aws/synthea-omop/)
- MTSamples: no licence statement was found via search. — (search returned nothing specific; see Gaps)

### Inferences
- **Ship:** condition/medication/procedure frequency tables (names + SNOMED/RxNorm codes) derived from Synthea sample output. Apache-2.0 allows this with NOTICE attribution, and the output is synthetic so there is no PII. Note that SNOMED CT code *descriptions* carry SNOMED International licensing in non-member countries (unverified, prior knowledge). RxNorm/ICD-10-CM (US government) are freer. Be careful with which terminology strings are bundled.
- **MIMIC-III/IV:** PhysioNet credentialed DUA, so no redistribution and no derived text (prior knowledge, unverified this session).
- **MTSamples:** treat as all-rights-reserved transcription samples. Do not ship. Write note templates (SOAP structure) from scratch instead.
- **Legal text:** US federal court opinions and statutes are public domain. CourtListener/Free Law Project bulk data and the Caselaw Access Project (now openly released) are candidate sources (unverified this session). EU legislation via EUR-Lex is reusable under 2011/833/EU.

### Gaps
- MTSamples terms, the MIMIC DUA wording, and CourtListener/CAP licences were not verified this session.

## Practical guidance: wheel budget, optional downloads, attribution, how Faker/Mimesis source data

### Takeaway
A 5-20 MB wheel easily fits pre-aggregated, compressed frequency tables for names, cities, job titles and support templates from permissive sources (CC0/public domain, CC BY 4.0, MIT, Apache-2.0, EU 2011/833). Anything ODbL, CDLA-Sharing, CC BY-SA, NC, "academic only" or unlicensed should be an opt-in fetch into a user cache, with the licence shown at fetch time. Faker and Mimesis are both MIT and keep data as in-repo Python/JSON with ad-hoc per-locale source notes. That is a weak provenance model Misata can improve on.

### Cited Findings
- Faker is MIT. Locale data is contributed via PRs, with sources noted inside provider code (e.g. Wikipedia, napolux/paroleitaliane). — [Faker GitHub](https://github.com/joke2k/faker); [Faker it_IT](https://faker.readthedocs.io/en/master/locales/it_IT.html)
- Mimesis is MIT and supports 46 locales. Its data lives as JSON files under data/<locale>, loaded via pull() with lru_cache. — [Mimesis docs PDF](https://mimesis.readthedocs.io/_/downloads/en/stable/pdf/); [libraries.io mimesis](https://libraries.io/pypi/mimesis)
- CC BY 4.0 sources (GeoNames, O*NET, Taskmaster, SimpleMaps Basic) require attribution and an indication of modifications. — [O*NET license](https://www.onetcenter.org/license_db.html); [GeoNames about](https://www.geonames.org/about.html)

### Inferences
- **Recommended tiers:**
  - *Tier A, bundled in the wheel (target ≤5 MB compressed total):*
    - SSA first names (CC0)
    - Census surnames (US government)
    - GeoNames cities15000 weights + admin1 names (CC BY 4.0)
    - Natural Earth countries/places (public domain)
    - O*NET titles (CC BY 4.0)
    - ESCO EN labels (EU reuse)
    - MultiWOZ/ABCD (MIT) and Taskmaster (CC BY) derived intent templates
    - Synthea-derived condition/medication frequencies (Apache-2.0)
    - original hand-written phrase banks
  - *Tier B, optional `misata data fetch <pack>`:*
    - GeoNames allCountries/postal codes (CC BY)
    - ESCO all languages
    - Open Food Facts product slices (ODbL)
    - Bitext (CDLA-Sharing)
    - OSM extracts via Geofabrik (ODbL)
    - OpenAddresses (per-source)
  - *Tier C, never (not even a helper):*
    - Yelp (academic only)
    - IMDb (non-commercial, no republishing)
    - Twitter customer support (NC-SA + PII)
    - name-dataset (Facebook leak PII)
    - MIMIC (DUA)
    - MTSamples (unlicensed)
    - Amazon reviews: no licence; at most a user-run loader that points at the upstream page, with a warning.
- **Provenance hygiene:** ship `misata/data/SOURCES.toml` (or similar) listing, per data file: source URL, licence SPDX ID (CC-BY-4.0, CC0-1.0, ODbL-1.0, CDLA-Sharing-1.0), retrieval date, transformation, and attribution string. Expose it at runtime (`misata.data.licenses()`). Put the combined attributions in a top-level NOTICE file included in the sdist/wheel, and declare it in pyproject (`license-files`).
- **Update cadence:**
  - GeoNames: daily dumps; refresh the bundled table yearly.
  - SSA: annual (spring).
  - O*NET: roughly annual or semiannual releases (31.0 is current).
  - EDGAR: nightly.
  - IMDb: daily (irrelevant).
  - Census surnames: decennial. 2020-census surnames had not been confirmed released in this session.
- **Tiny models:** training a small n-gram/Markov model on CC BY or MIT dialog data and shipping the weights is likely an adaptation that still requires attribution, but it is fine under permissive licences. Do not train shipped models on NC/ToS-restricted corpora.

### Gaps
- Mimesis per-locale data provenance was not inspected (GitHub API access to the repo was denied in this session).
- No authoritative legal analysis was found on whether n-gram frequency tables from copyrighted review text are non-infringing. This remains uncertain.
- Whether Census has released 2020 surname files was not verified.
