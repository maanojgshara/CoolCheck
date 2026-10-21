# Check 6: Meteorological Service Singapore historical daily records, terms of use

Script: `scripts/checks/check6_mss_terms.py`; run 2026-10-21 12:52 SGT. Two unauthenticated GET requests: `https://www.weather.gov.sg/terms-of-use/` (HTTP 200, 73,739 bytes) and `https://www.weather.gov.sg/climate-historical-daily/` (HTTP 200, 151,750 bytes). **Unverified until read; I am not a lawyer and this is not legal advice.**

## What was tested

Whether the site's terms of use allow using the historical daily records (daily maximum air temperature for the M9/M10 test, daily rainfall) in this project, and whether the data can be fetched by a program.

## Result

The terms page was readable. Clauses found (checked by phrase search on the page text, paraphrased here):

| clause | found on page | paraphrase |
|---|---|---|
| 2.2 | yes | Site contents are copyright and owned by or licensed to NEA. |
| 4.1 | yes | Contents may not be reproduced, republished, uploaded, posted or distributed without MSS's prior written permission. |
| 4.2 | yes | To use parts of the contents, ask in writing by email, stating contents, intent, manner, time frame and identity; NEA may refuse. |
| 4.3 | yes | Subject to 4.2, contents may be used, copied and distributed solely for personal, internal, non-commercial or informational purposes; one copy may be downloaded for personal non-commercial use with notices kept; no commercial use without written consent. |
| 5.4 | yes | Real-time data has only basic quality checks; gaps may occur; MSS is not liable for missing data. |
| 6.2 | yes | Users must not use a robot, spider or other automatic device, or a manual process, to monitor or copy pages or contents without NEA's prior written permission, nor impose an unreasonably large load on the servers. |

Reading of those clauses (mine, not a legal opinion):

- **Allowed without asking (4.3):** personal, internal, non-commercial or informational use, including copying and distributing the contents for those purposes. A hackathon test of whether air temperature adds skill is plausibly within 'internal' and 'informational' use, but whether a public repository, dashboard or write-up that republishes the data counts as 'distribution' under 4.1 versus 4.3 is **not clear to me**.
- **Needs written permission:** reproducing or republishing the contents (4.1), commercial use (4.3), and any robot, spider or other automatic device to copy pages (6.2). So a script that pulls many station-days from this site is, on the wording, an automatic device and would need permission from NEA_MSS_Engage@nea.gov.sg.
- **No open-data licence is stated** on the page (no Singapore Open Data Licence wording), unlike the data.gov.sg datasets.

## Download mechanism

- The historical page lets a visitor pick a station, a weather parameter and a period; it lists 5 named Meteorological Stations (Changi Meteorological Station, Paya Lebar Meteorological Station, Seletar Meteorological Station, Sembawang Meteorological Station, Tengah Meteorological Station) among many named rain gauge sites. No CSV file link or download URL appears in the page source, so the download is probably built by page scripts; the file format and URL were **not determined**.
- Page note on coverage: Manual observations were gradually replaced by automated meteorological instruments from 2009.
- Records are said on the page to be updated by the 10th of each month (page text, not tested).

## Fallback (agreed 19 Oct): if the terms do not allow it
Skip the air-temperature test (M9, M10). **Alternatives found on data.gov.sg under the Singapore Open Data Licence (catalogue crawl 21 Oct; the datasets were not opened):** NEA 'Historical Air Temperature across Singapore' yearly CSVs for 2016 to 2024 (`d_2b359912668f5f55fde28254e9c9092d` for 2016 up to `d_910c81fce47f38574015b3882ac59254` for 2024), and the NEA live air-temperature API with `date=` history (check 12: 1-minute readings, back to at least 2016-12-02), from which a daily maximum could be computed. The 2025 to 2026 yearly CSV was not seen in the catalogue; the API would cover it. Rainfall history already comes from the data.gov.sg rainfall feed (backfilled).

## Could not confirm

- Whether MSS grants permission by email and how long it takes (not asked).
- The download URL or format of the historical records, and whether the daily maximum temperature is among the parameters for the stations needed.
- Whether the data.gov.sg alternatives cover the same stations and have a daily maximum or only raw readings.
- The terms page's date of last revision (not found in the text).

