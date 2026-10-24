# CoolCheck: a next-day heat briefing for community care teams

*A HeatGuard solution for DAISI Round 2, problem B1. Team AIsenal.*

## Summary

CoolCheck is a next-day heat briefing for Active Ageing Centre teams and care coordinators. Each night it forecasts the coming day's heat stress for 41 planning areas, crosses it with the area's vulnerability (seniors aged 75+, rental flats, distance to cooling refuges) into a Low, Medium or High tier, and lists the HDB blocks to check first. On held-out weeks scored once, the pre-declared test passed: area-day PR-AUC 0.489 against 0.360 for "same as today". At the cut-off it caught 61 of 77 High area-days, about one alert in three correct; at equal alert load, 35 against 32. Without S142, S137 and S135 the edge is small; no difference is claimed from these weeks alone (`checks/final_check.md`). Still to build: the agent, its four-language advisories and its evaluations; the briefing dashboard is in progress.

> **Draft of the Devpost project description, 24 Oct 2026.** Every number names the repository file it comes from; paths are relative to `docs/` unless they start with another folder. `[TBD: …]` marks what is not built yet. Weak results are reported as they are.

## The problem, who uses CoolCheck and the decision it informs

2025 was Singapore's hottest year on record (DAISI problem statement B1). Heat stress falls hardest on older residents: in June 2026, 806,080 residents were aged 65 or over and 310,310 were aged 75 or over (`checks/area_exposure.md`).

NEA measures heat stress at its weather stations as the Wet Bulb Globe Temperature (WBGT), in its own categories Low, Moderate and High, and publishes a 24-hour weather forecast. What we did not find in open data is a view of the coming day that puts the heat forecast together with where vulnerable seniors live and how far they are from a place to cool down.

CoolCheck is for the people who check on seniors: Active Ageing Centre (AAC) teams and care coordinators. It informs one decision, made each morning: where to put a limited number of calls and visits. Overnight, CoolCheck gives each of the 41 planning areas with residents aged 65+ the coming day's heat level, gives the 32 of them with HDB blocks a risk tier, and lists within each the HDB blocks to check first (`design/risk_score.md`). A scheduled job at 00:45 SGT does this; its first scheduled night was 24 Oct (`checks/heat_forecast_first_night.md`). The AAC matches the block list against its own client list, so CoolCheck holds no personal data.

[TBD: a practitioner's confirmation of the need, the tiers and the actions; none has been obtained yet.]

## Approach and architecture

```
data.gov.sg: WBGT, rainfall, 24-hour forecast, air temperature
  |  collector on GitHub Actions, every 15 minutes (started by cron-job.org)
  v
Unity Catalog Volume: raw JSON
  |  Lakeflow pipeline (serverless, triggered)
  v
Bronze (Auto Loader) -> Silver (parsed, rule flags, deduplicated) -> daily station labels
  |                                       |
  | hourly job                            | features known by 00:15 SGT
  v                                       v
gold.latest_readings -> live page      LightGBM in MLflow: 14-month back-test, final check;
                                       live model refit to 22 Oct, registered as champion
                                          |  nightly job, 00:45 SGT (refresh, then score)
                                          v
                                       gold.heat_forecast: 41 areas
                                          |
static open data -> Silver layers -> Gold vulnerability views
                                          |  (heat level x vulnerability third)
                                          v
                                       gold.area_heat_risk: the tier view
                                          |
                    [TBD: briefing dashboard, approval App and agent]
```

The diagram's numbers are cited in the steps below.

1. **Live feeds, collected outside Databricks.** Databricks serverless, on our trial workspace and on Free Edition alike, could not resolve any `.gov.sg` host (`build-log.md`, 19 and 20 Oct). A collector on GitHub Actions therefore fetches four NEA feeds from data.gov.sg and uploads the raw responses to a Unity Catalog Volume. cron-job.org starts it every 15 minutes, GitHub's own schedule is kept as a second start, and one repository variable stops both (`README.md`). It runs every 15 minutes from 22 Oct, 15:00 SGT (`datasets.md`, row 1).
2. **One Lakeflow pipeline from Bronze to Silver.** Auto Loader loads each raw page into Bronze. Silver parses every copy, flags each quality rule rather than dropping rows, deduplicates and quarantines what does not parse. A daily label per station takes NEA's own category, the highest of the day. When Silver was first built, it held exactly the raw files' totals: 1,036,005 WBGT readings and 11,893,198 rainfall readings (`checks/silver_check.md`).
3. **Static layers.** SingStat's June 2026 residents by age for the 55 Master Plan 2025 planning areas (`checks/area_exposure.md`); HDB Property Information for rental flats; the 10,817 residential HDB blocks, geocoded once with OneMap, 10,807 of them confirmed (`checks/geocode_hdb.md`); cooling refuges from the People's Association's community clubs and the 93 Active Ageing Centres named in MOH's Dementia Friendly Go-To-Points (`checks/refuge_park_access.md`); parks from NParks; household electricity from EMA. They are fetched on a laptop, again because of the network block, and loaded to Unity Catalog; the refuge and park tables carry column comments and source and licence tags (`scripts/static/load_refuge_park_access.py`).
4. **Heat mapped to planning areas.** Heat is measured at stations, so each day every planning area takes its nearest reporting WBGT station, measured from the mean position of its HDB blocks (or the area's centre where it has none), and island stations serve only their own island. Before that rule, Sentosa's beach station stood in for Bukit Merah and for Outram on 136 days each (`checks/h10_v2.md`). The network grew from 8 stations on 16 Jan 2025 (`checks/wbgt_high_days.md`) to 30 reporting on 22 Oct 2026 (`checks/live_completeness.md`), so one model is pooled across stations without the station ID.
5. **A forecast of NEA's own category.** A LightGBM model gives, for each station and day, the probability of Low, Moderate and High heat stress, from 11 features known by 00:15 SGT that day: yesterday's peak WBGT and its 7-day mean, a 30-day station character, yesterday's High readings, the peak and High count of a fixed panel of the original stations, NEA's forecast maximum temperature and text, yesterday's rainfall, the month and the season (`checks/final_check.md`, settings).
6. **Tested month by month, then once on held-out weeks.** A rolling monthly back-test over 14 months, July 2025 to August 2026, predicts each month with a model trained only on the months before it, against three baselines: "same as today", "same month last year" and a rule on NEA's forecast maximum temperature (`checks/backtest.md`). The alert cut-off was chosen on the back-test. A final check on 1 Sep to 19 Oct 2026 was specified in writing before any of its data was read, then scored once behind a lock (`design/backtest.md`, §15; `checks/final_check.md`). Every run is logged in MLflow.
7. **From heat to a tier.** A vulnerability index ranks the 32 planning areas that have HDB blocks on seven components (`design/risk_score.md`, §3):
   - senior exposure: residents aged 75+, as a count and as a share;
   - can't cool down: 1–2 room rental flats, and a weak electricity term;
   - the cooling-access gap: flats beyond 400 m of a refuge, refuges per 1,000 residents aged 65+, and flats beyond 400 m of a park.

   Each component becomes a percentile among the 32 areas, and the weighted sum splits the areas into thirds. The coming day's heat level is High when the model's probability of High reaches the cut-off, 0.110 (`checks/backtest_review.md`), and otherwise the more likely of Moderate and Low. A 3×3 rule crosses the heat level with the vulnerability third to give the area's risk tier: Low, Medium or High (`design/risk_score.md`, §6). Within an area, blocks are ordered by 1–2 room rental flats, then by distance to the nearest refuge: blocks rank vulnerability, never heat. The vulnerability views and the weight and action tables are in Unity Catalog. A scheduled job at 00:45 SGT refreshes the pipeline, scores the coming day with the live model and writes `gold.heat_forecast`; the view `gold.area_heat_risk` crosses that with the thirds to give the day's tiers, with no probability or score column (`checks/heat_forecast_first_night.md`). Its first scheduled night was 24 Oct: one night, not a track record.
8. **What people see.** A live heat-stress page, an AI/BI dashboard, shows the newest WBGT by station on a map in NEA's categories, rain in the last hour and air temperature, from a table an hourly job refreshes. When the table is more than 90 minutes old, every station shows "no recent reading" (`README.md`).
   - [TBD: the briefing dashboard: the planning-area map by tier, the areas with plain reasons, and the block list.]
   - The agent's three tools exist as Unity Catalog SQL functions, `get_priority_areas`, `find_refuges` and `what_if_add_refuge`. The first fills the AAC's call capacity in code, in tier order, and none returns a probability or a score. 35 local tests and 16 through Databricks Connect passed (`design/agent_tools.md`).
   - [TBD: the agent. It drafts the day's outreach plan from the tiers and the block list. Allocation to the AAC's call capacity is done in code, a person approves, and nothing is sent automatically.]
   - [TBD: advisories in four languages.]
   - [TBD: the agent's evaluation scenarios.]

**Built with:** Unity Catalog (catalog, Volume, tables, views, SQL functions, a model registry, comments, tags), Lakeflow Spark Declarative Pipelines (Auto Loader, expectations, Auto CDC), Lakeflow Jobs on serverless, MLflow, AI/BI dashboards, Declarative Automation Bundles, and Databricks Connect for the tests; GitHub Actions and cron-job.org for collection.

## The datasets

CoolCheck uses 15 open datasets from 9 agencies, all under the Singapore Open Data Licence v1.0 (`attribution.md`):

| dataset | agency | use |
|---|---|---|
| WBGT heat stress (real-time) | National Environment Agency | the model's label and main input; the live page |
| Rainfall across Singapore | National Environment Agency | model input; the live page |
| 24-hour Weather Forecast | National Environment Agency | model input |
| Air Temperature across Singapore | National Environment Agency | the live page only, not a model input |
| Singapore Residents by Planning Area/Subzone, Age Group, Sex and Floor Area of Residence, June 2026 | Singapore Department of Statistics | residents aged 65+ and 75+ per area |
| Senior Activity Centres and Active Ageing Centres, Annual | Singapore Department of Statistics | the count behind "93 of about 223" (`checks/refuge_park_access.md`) |
| HDB Property Information | Housing & Development Board | blocks, dwellings and rental flats |
| Dementia Friendly Go-To-Points | Ministry of Health | the 93 Active Ageing Centres, a partial refuge layer (`checks/refuge_park_access.md`) |
| Eldercare Services (2016) | Ministry of Health | a sensitivity run only |
| Community Club / PAssion WaVe Outlet | People's Association | community clubs, the complete refuge layer |
| NParks Parks and Nature Reserves | National Parks Board | parks within 400 m of flats |
| Master Plan 2025 Planning Area Boundary | Urban Redevelopment Authority | the 55 planning areas (`checks/area_exposure.md`) |
| Master Plan 2025 SDCP Park layer | Urban Redevelopment Authority | a sensitivity run only |
| Singapore Energy Statistics 2025, Chapter 3 | Energy Market Authority | the electricity term |
| OneMap Search API | Singapore Land Authority | geocoding the HDB blocks once |

The dataset register lists 23 datasets or feeds from 10 agencies, counting those held for comparison, planned or cited once (`datasets.md`). Considered and not used: PM2.5, which has no clear role in a next-day heat model, and HDB Elderly, which covers 25 towns in four survey years from 2003 to 2018 (`checks/hdb_elderly.md`).

Real data was messy, and each problem has a stated rule:
- 521 forecast records carry a 48-hour validity window and 6 end before they start (`checks/forecast_validity.md`). Validity is taken as the start plus 24 hours, and old issues are not used.
- Four back-test days had no usable forecast and were filled from training data by a fixed rule: 2025-07-21, 2026-04-29, 2026-05-18 and 2026-07-07 (`checks/backtest.md`). None was filled in the final check (`checks/final_check.md`).
- 53 geocoded blocks had candidates at different places and were resolved by a postal-code rule (`checks/geocode_hdb.md`).
- The station network grew from 8 to 30 stations, so results are also reported for the original 8, and without S142, S137 and S135, three hot stations that joined late (`checks/error_analysis.md`).

## Results

**The back-test, July 2025 to August 2026.** It covers 17,438 area-days, each one planning area on one day, over the 41 areas with residents aged 65+; 710 of them were High (`checks/backtest.md`). PR-AUC measures how well a score ranks High days above the rest; a score with no skill gets the High rate, 0.041 here.

| method | PR-AUC (95% interval) |
|---|---|
| CoolCheck's model | 0.295 (0.233 to 0.365) |
| "same as today" | 0.235 (0.171 to 0.306) |
| NEA forecast rule | 0.058 (0.040 to 0.081) |

Source of the table: `checks/backtest.md`.

- The model ranks risk better than "same as today": the difference is 0.061, with a 95% interval of 0.009 to 0.115 (`checks/backtest.md`).
- At the same number of alerts as "same as today", 700, both catch 245 of the 710 High area-days (`checks/backtest.md`). The gain is fewer alerts for the same catch: to catch half, 355 of 710, the model needs 1,180 alerts and "same as today" 1,541 (`checks/backtest_review.md`).
- "Same month last year" exists only from February 2026; over February to August 2026 it scores 0.095 against the model's 0.337 (`checks/backtest.md`).
- The station-character feature was kept by a rule fixed before the run: 0.340 with it and 0.296 without, on station-days (`checks/backtest.md`).
- Without stations S142 (Sentosa), S137 (Jurong Island) and S135 (Bird Paradise), the edge over "same as today" is not clear: 0.179 against 0.160, a difference of 0.019 with an interval from −0.021 to 0.069, on station-days (`checks/backtest.md`).

**The final check, 1 Sep to 19 Oct 2026, scored once** (`checks/final_check.md`).
- The pre-declared test passed: area-day PR-AUC 0.489 against 0.360 for "same as today".
- At the cut-off, 61 of 77 High area-days were caught, with about one alert in three correct: 176 alerts, precision 0.347.
- At the same alert load, the model caught 35 against 32.
- Without S142, S137 and S135 the edge is small: on station-days, PR-AUC 0.279 against 0.244, and 11 of 31 each at the same load.
- No difference between the model and a baseline is claimed from the final check alone: its 49 days are too few for the block bootstrap.

The final check scores the model fitted to 31 Aug 2026, on 9,308 station-days with 465 High (`checks/final_check.md`). The live model is the same configuration refit on target dates to 22 Oct 2026, on 10,861 station-days with 538 High. It is a different fitted model, and no result is reported for it yet (`checks/live_model.md`).

**The tiers in the back-test months** (`checks/risk_score.md`).
- The High tier fired on 566 area-days: about 1.3 areas a day on average, on 168 of 427 days, and at most 14 in one day.
- The Medium tier fired on 4,773 area-days, about 11 areas a day on average. Medium is not an alert: heightened care where heat is Moderate in an upper- or middle-third area, or High in a lower-third one.
- Low covered 8,263 area-days (`checks/risk_score.md`). The 9 areas without HDB blocks show only their heat level (`design/risk_score.md`).
- The weights are a stated judgement, tested by sensitivity runs and not yet reviewed by a practitioner. Equal weights keep the ranking close (Spearman's rho 0.900, 10 areas change third); refuges from the clubs only give 0.888; the URA park layer gives 0.915 and changes no tier; dropping the electricity term gives 0.990 and changes nothing.

**The pipeline in use.**
- The live page's hourly job ran 21 times in a row without a failure, in 61 to 84 s each (`checks/latest_readings_cost.md`).
- The 264 tests that run locally passed on 23 Oct (`build-log.md`).
- A scan of every commit in the repository found no credential (`checks/secret_scan.md`).

## Impact: reach, lead time and recall

- **Reach.** In the back-test months the High tier covered, on average, 16,524 residents aged 75+ a day (`checks/risk_score.md`). Count each such resident once per day as a senior-day. On observed High days in the rated areas there were 4,571,620 senior-days, and 1,806,220 of them (39.5%) fell in areas the tier had flagged High in advance: 143 of 471 High area-days (`checks/risk_score.md`).
- **Lead time.** The forecast for a day uses only data up to 00:15 SGT that day (`design/backtest.md`). On High days the first High reading came at 12:45 at the median and never before 09:45, over 465 High station-days (`checks/eda.md`). On its first scheduled night, 24 Oct 2026, the nightly job had the day's forecast for all 41 areas written at 00:49:49 SGT, 35 minutes after the cut-off and about 5 hours before 06:00 (`checks/heat_forecast_first_night.md`). That is one night, not a track record.
- **Recall.** In the back-test, the cut-off caught half of the High area-days, 355 of 710 (`checks/backtest_review.md`). In the final check it caught 61 of 77 (`checks/final_check.md`).
- **No harm figure.** There is no open data on heat illness by area and day, so we claim no lives saved, no admissions avoided and no harm prevented.

## Limitations

- **The final check is small:** 77 High area-days over 49 days, so no difference is claimed from it alone (`checks/final_check.md`).
- **The edge rests on three hot stations.** Without S142, S137 and S135 the edge over "same as today" is not clear in the back-test (0.179 against 0.160, `checks/backtest.md`) and small in the final check (`checks/final_check.md`).
- **The model is late into hot spells.** It missed 315 of 465 first days of a hot spell, against 40 of 245 later days, and all 22 High area-days of March 2026, the start of a hot season (`checks/error_analysis.md`). In April 2026 its probabilities of High summed to about 82 against 184 observed High area-days (`checks/backtest_review.md`).
- **The probability is not shown.** Over its alerts it is about right on average, 0.275 against 0.301 observed, but too spread out: its highest fifth predicts 0.478 against 0.420 observed (`checks/error_analysis.md`). The briefing shows tiers, never the probability.
- **The alert load varies.** At the cut-off the final check gave 3.59 alerts a day against the back-test's 2.76, and in October only 13 of 76 alerts were High days (`checks/final_check.md`).
- **The label is fragile.** 260 of 465 High station-days rest on one or two 15-minute readings (`checks/eda.md`). Where two stations are almost equally near an area, their daily categories differed on about 22% of days in the two areas checked (`checks/backtest.md`).
- **The history is short.** WBGT history starts on 16 Jan 2025 (`checks/wbgt_high_days.md`), so there are 14 test months and at most one earlier year for "same month last year".
- **The refuge layer is partial.** Open data names 93 of about 223 Active Ageing Centres, so distances overstate the gap where centres are missing; distances are straight lines, not walking routes (`checks/refuge_park_access.md`).
- **The park source matters.** NParks and URA's park layers rank the areas almost oppositely on parks within 400 m (rho 0.082), so parks carry only 0.10 of the weight (`checks/refuge_park_access.md`, `design/risk_score.md`).
- **The electricity term is weak.** The April-to-June over November-to-February ratio of 1–2 room electricity use averages 1.0995 over 280 area-years, 2015 to 2024, about a 10% rise. A smaller rise only "may indicate" less air-con use, and 4 of the 32 rated areas have no value (`checks/ema_electricity.md`).
- **Air temperature is not tested as a model input.** WBGT is used because NEA's categories are defined on it; we make no claim that it predicts better than air temperature.
- **Some areas are not rated.** 9 of the 41 areas with residents aged 65+ have no HDB blocks and show their heat level only; they hold 4,730 residents aged 65+ (`design/risk_score.md`).
- **One night so far.** The nightly job has one scheduled night behind it, 24 Oct, and the live model has no held-out result (`checks/heat_forecast_first_night.md`, `checks/live_model.md`).
- **Not built yet:** the briefing dashboard, the agent, the four languages and the evaluations, all marked [TBD] above.

## What's next

- **Who would run it.** A trial over one heat season with one AAC cluster: its staff read the briefing each morning and decide the calls, and the team runs the pipeline. [TBD: a named partner, and a practitioner's review of the tiers, the weights and the actions.] After a trial, an organisation that coordinates AACs could own it. On Databricks Free Edition, a service principal's login and the collector's upload were tested and worked (`build-log.md`, 22 Oct). [TBD: the full redeploy to Free Edition, since the trial workspace ends on 30 Oct (`build-log.md`, 19 Oct).]
- **The measured cost.** All figures are at list price.
  - The live page's hourly refresh costs US$0.142 a run, US$3.40 a day (`checks/latest_readings_cost.md`). Every 15 minutes would cost about US$13.59 a day, an estimate, so it stays hourly.
  - The trial workspace used US$12.95 from 19 to 21 Oct, the days the pipeline was built and the history loaded (`checks/cost_since_19_oct.md`).
  - Each collector run on GitHub Actions is billed as one minute (`build-log.md`).
  - The nightly job, a pipeline refresh and then scoring, cost US$0.358 on its first scheduled night, 24 Oct, and US$0.447 for the manual run of 23 Oct. Two runs, so no daily or monthly total is claimed (`checks/heat_forecast_first_night.md`). Not counted yet: the App, which bills while it runs, and the SQL warehouse behind the dashboard and the App. [TBD: the App's cost, read from billing after it has run a day.]
- **No personal data.** CoolCheck holds aggregates and public places only: residents by age per planning area, flats per block, refuges and parks. Names, addresses and health data stay with the AAC, which matches the block list against its own clients.
- **How it fits AACs' welfare calls.** The tier table proposes actions, each marked "proposal, not yet reviewed by a practitioner" (`design/risk_score.md`, §7):
  - High: phone checks before noon on flagged seniors in the priority blocks; AACs and community clubs extend hours as cooling spaces; the town council is told.
  - Medium: the AAC broadcasts a hydration and heat advisory in four languages; volunteers flag seniors living alone in the priority blocks.
  - Low: routine.

  In the back-test months that meant about 1.3 High areas and about 11 Medium areas a day (`checks/risk_score.md`). Whether about 11 Medium areas a day is useful is a question for the practitioner review. [TBD: the agent drafts the day's call plan within the AAC's stated capacity, and a person approves it.]
- **Then:**
  - a practitioner's review of the tiers, weights and actions;
  - the full list of Active Ageing Centres from MOH or AIC;
  - air temperature as a model input, if a permitted source of its history exists;
  - recalibrating the probability before it is ever shown;
  - refitting the live model as days complete; it was fitted once, to 22 Oct.

## Data sources and attribution

Each dataset in use carries the notice below, copied from the dataset register (`datasets.md`); `attribution.md` gives where each must appear. SingStat and EMA are named without links to their sites. CoolCheck is not official advice, and no agency endorses it.

1. "Contains information from Heat stress (WBGT) real-time readings accessed on 20 October 2026 from National Environment Agency via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
2. "Contains information from Rainfall real-time readings accessed on 20 October 2026 from National Environment Agency via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
3. "Contains information from 24-hour Weather Forecast accessed on 20 October 2026 from National Environment Agency via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
4. "Contains information from Air temperature real-time readings accessed on 22 October 2026 from National Environment Agency via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
7. "Contains information from Singapore Residents by Planning Area/Subzone, Age Group, Sex and Floor Area of Residence, June 2026 accessed on 21 October 2026 from Singapore Department of Statistics which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
8. "Contains information from Senior Activity Centres and Active Ageing Centres, Annual accessed on 21 October 2026 from Singapore Department of Statistics via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
9. "Contains information from HDB Property Information accessed on 21 October 2026 from Housing & Development Board via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
11. "Contains information from Eldercare Services accessed on 21 October 2026 from Ministry of Health via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
12. "Contains information from Dementia Friendly Go-To-Points (GTPs) accessed on 21 October 2026 from Ministry of Health via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
14. "Contains information from Community Club / PAssion WaVe Outlet accessed on 21 October 2026 from People's Association via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
16. "Contains information from NParks Parks and Nature Reserves accessed on 21 October 2026 from National Parks Board via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
19. "Contains information from Master Plan 2025 Planning Area Boundary (No Sea) accessed on 21 October 2026 from Urban Redevelopment Authority via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
20. "Contains information from Master Plan 2025 SDCP Park layer accessed on 21 October 2026 from Urban Redevelopment Authority via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
22. "Contains information from Singapore Energy Statistics 2025, Chapter 3: Energy Consumption accessed on 21 October 2026 from Energy Market Authority which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
23. "Contains information from OneMap Search API accessed on 21 October 2026 from Singapore Land Authority (OneMap) which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."

[TBD: notices 1, 2 and 4 use descriptive names. Replace them with the data.gov.sg titles once the register is updated (`attribution.md`, flags 3 and 4).]
