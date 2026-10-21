# Check 1: does Eldercare Services include Active Ageing Centres?

Dataset `d_f0fd1b3643ed8bd34bd403dedd7c1533` (MOH, GeoJSON, source last updated 2024-06-06). Script: `scripts/checks/check1_refuges.py`; file downloaded 2026-10-21 by `download_static.py` (no key). **Unverified until read.**

## What was tested

Every feature's `NAME` (parsed from the HTML `Description` attribute table) was classified by keyword, and the file was compared with SingStat's published yearly counts of Senior Activity Centres and Active Ageing Centres (dataset `d_0f70d7095a527be4ea443a7e30597896`).

## Result

- Features: **133**, all `Point` geometry. Valid coordinates inside a Singapore bounding box: 133 of 133. Distinct names: 116; distinct coordinate pairs: 120.
- Attribute keys in the Description table: `ADDRESSBLOCKHOUSENUMBER`, `ADDRESSBUILDINGNAME`, `ADDRESSFLOORNUMBER`, `ADDRESSPOSTALCODE`, `ADDRESSSTREETNAME`, `ADDRESSTYPE`, `ADDRESSUNITNUMBER`, `DESCRIPTION`, `FMEL_UPD_D`, `HYPERLINK`, `INC_CRC`, `LANDXADDRESSPOINT`, `LANDYADDRESSPOINT`, `NAME`, `PHOTOURL`.
- The `FMEL_UPD_D` stamp (record update date) by year: {'2016': 133}.

Classification by name (keyword rules in the script; a heuristic, not an official category):

| kind (by name) | features |
|---|---|
| Senior Activity Centre (name or 'SAC') | 60 |
| Home / care service (by name) | 30 |
| Operator or programme name (by name) | 23 |
| Cluster Support (by name) | 8 |
| Silver ACE (not AAC by name) | 6 |
| Other / unclassified | 6 |

Examples per kind (first 4):

- Senior Activity Centre (name or 'SAC'): Yuhua Senior Activity Centre; THK SAC @ Kaki Bukit; THK SAC @ Boon Lay; PEACE-Connect Senior Activity Centre@5
- Silver ACE (not AAC by name): Silver ACE @ Bukit Merah; Silver Ace @ Taman Jurong; Silver Ace@Lengkok Bahru; Silver Ace@Redhill
- Home / care service (by name): Abdullah Shooker Jewish Welfare Home; Adventist Home For The Elders; AWWA Community Home for Senior Citizens; Bo Tien Home For The Aged
- Cluster Support (by name): NTUC Health Cluster Support @ Taman Jurong; NTUC Health Cluster Support @ Bt Merah; THK Cluster Support @ Bedok; Peace-Connect Cluster Operator
- Other / unclassified: Carecorner Cluster Suppport; Care Corner SGH @ WL569A; Care Corner SGH @ WL180C; Unicare Services Pte Ltd
- Operator or programme name (by name): Econ Health and Wellness Centre; Thye Hua Kwan Moral Charities Limited; Econ Health and Wellness Centre; Econ Health and Wellness Centre

SingStat counts (from the CSV):

| series | 2024 | 2023 | 2022 | 2021 | 2020 |
|---|---|---|---|---|---|
| Number Of Senior Activity Centres | na | 3 | 17 | 42 | 83 |
| Number Of Seniors Having Access To Senior Activity Centres | na | 1445 | 7287 | 19959 | 39749 |
| Number Of Active Ageing Centres | 223 | 157 | 119 | 60 | na |
| Number Of Seniors Having Access To Active Ageing Centres | 500435 | 335565 | 257529 | 139542 | na |

## Reading

- **Verdict: no feature is named an Active Ageing Centre, so by name the answer is NO and the agreed fallback applies.** 6 features are named 'Silver ACE'; whether those are Active Ageing Centres under another name is **not confirmed** (not stated in the file).
- **Active Ageing Centres by name in the file: 0.** Senior Activity Centres by name: 60. SingStat reports 223 Active Ageing Centres for 2024 and 3 Senior Activity Centres for 2023 (Senior Activity Centres peaked at 82 in 2019). The file has 133 points in total.
- The file's records are stamped 2016 and the address-point coordinate fields are 0, so the file looks like an old extract of Senior Activity Centres and similar services (inference from the names and stamps, not stated by MOH).

## Fallback (agreed 19 Oct): if the file does not include Active Ageing Centres
Use the MSF Senior Activity Centre data or the Agency for Integrated Care (AIC) listing of Active Ageing Centres (https://www.aic.sg/Care-Services/Active-Ageing-Centres). Community Clubs (check on `community_clubs`) and Parks remain as refuges.

## Could not confirm

- Whether the AIC listing can be downloaded or only browsed, and its terms of use (not opened).
- Whether the keyword classification matches MOH's own service categories.
- Whether any point in this file is a closed or moved centre.

