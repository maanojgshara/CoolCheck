# Languages: three drafts, back-translation check (24 Oct 2026, 20:38 SGT)

Written by `scripts/checks/language_check.py` (window B, 24 Oct 2026); report copied unchanged below this note. Read it with these facts:
- The three English drafts were made once by the agent loop and reused for both translators. The Malay one was made before the fix of 20:40 SGT: the model sent `calls_per_volunteer: 0` and the plan got 8 x 0 = 0 calls (now a 0 counts as not stated); its text is still a valid test of translation.
- This is the third run. Run 1 (Llama only) and run 2 used a prompt that quoted the line "Draft only: nothing has been sent.", which both models then left in English; this run asks for every sentence to be translated and allows a local name in brackets after the English name. In run 2, Qwen 3.5 needed `reasoning_effort: "none"`: with no setting it spent its 4,000 tokens thinking (`finish_reason: length`) and returned nothing.
- Back-translation is by `system.ai.gpt-oss-120b`, not Google Translate as Guide §14.2 planned (no Google key is set up). Some flags below come from the back-translation, not the translation: Malay "dihantar" back-translated as "submitted"; Tamil "வரைவு" (draft) back-translated as "Scope"; Chinese "1-2" back-translated in words.

- Translators: `system.ai.meta-llama-3-3-70b-instruct`, `system.ai.qwen35-122b-a10b`; back-translation: `system.ai.gpt-oss-120b`, through the Unity Gateway chat-completions route, temperature 0, profile `coolcheck`.
- Label: Machine-translated, checked by back-translation, not reviewed by a native speaker.

## Malay (Bahasa Melayu, as used in Singapore): "Only 8 volunteers tomorrow. Which blocks should we call first?" (2026-10-24)

Draft source: agent. Tool calls: [{"name": "get_priority_areas", "arguments": {"target_date": "2026-10-24", "call_capacity": 0, "region": null}, "llm_arguments": {"volunteers": 8, "calls_per_volunteer": 0}, "row_count": 41, "error": null, "elapsed_ms": 1234}]

English:

```
The whole island has 8 volunteers for heat outreach. TOA PAYOH and BISHAN have High heat, but are ranked High and Medium respectively for vulnerability. SOUTHERN ISLANDS and SUNGEI KADUT have High heat but no HDB blocks to rate. Prioritize TOA PAYOH, then BISHAN.
Note: High heat but Not rated (no confirmed HDB blocks, so no blocks or calls): Southern Islands and Sungei Kadut.
Draft only: nothing has been sent. A person approves; the Active Ageing Centre matches the blocks against its own client list (CoolCheck holds no personal data). Heat is forecast per planning area; blocks rank vulnerability, never heat. Distances are straight lines, not walking distances.
```

### `system.ai.meta-llama-3-3-70b-instruct`: DRIFT (6 s)

Translation:

```
Seluruh pulau ini mempunyai 8 orang sukarelawan untuk pencerapan haba. TOA PAYOH [Toa Payoh] dan BISHAN [Bishan] mempunyai haba tinggi, tetapi berkedudukan tinggi dan sederhana bagi kerentanan masing-masing. SOUTHERN ISLANDS [Pulau Selatan] dan SUNGEI KADUT [Sungei Kadut] mempunyai haba tinggi tetapi tiada blok HDB untuk dinilai. Utamakan TOA PAYOH [Toa Payoh], kemudian BISHAN [Bishan].
Nota: Haba tinggi tetapi Tidak dinilai (tiada blok HDB yang disahkan, jadi tiada blok atau panggilan): Southern Islands [Pulau Selatan] dan Sungei Kadut [Sungei Kadut].
Draf sahaja: tiada apa yang telah dihantar. Seseorang mengesahkan; Pusat Penuaan Aktif [Active Ageing Centre] mencocokkan blok dengan senarai klien sendiri (CoolCheck tidak memegang data peribadi). Haba diramalkan per kawasan perancangan; blok menilai kerentanan, bukan haba. Jarak adalah garis lurus, bukan jarak berjalan.
```

Back-translation:

```
The whole island has 8 volunteers for heat mapping. TOA PAYOH [Toa Payoh] and BISHAN [Bishan] have high heat, but they rank high and medium respectively for their vulnerability. SOUTHERN ISLANDS [Pulau Selatan] and SUNGEI KADUT [Sungei Kadut] have high heat but no HDB blocks to assess. Prioritize TOA PAYOH [Toa Payoh], then BISHAN [Bishan].
Note: High heat but Not assessed (no verified HDB blocks, so no blocks or calls): Southern Islands [Pulau Selatan] and Sungei Kadut [Sungei Kadut].
Draft only: nothing has been submitted. Someone confirmed; the Active Ageing Centre [Active Ageing Centre] matches blocks with its own client list (CoolCheck does not hold personal data). Heat is predicted per planning area; blocks assess vulnerability, not heat. Distance is straight‑line, not walking distance.
```

Checks: {"untranslated_sentences": [], "numbers_missing_in_translation": [], "numbers_missing_in_back_translation": [], "ungrounded_numbers_in_translation": [], "blocks_missing_in_translation": [], "blocks_missing_in_back_translation": [], "names_missing_in_translation": [], "names_missing_in_back_translation": [], "nothing_sent_kept": false, "draft_word_kept": true, "passed": false}

### `system.ai.qwen35-122b-a10b`: DRIFT (4 s)

Translation:

```
Seluruh pulau mempunyai 8 sukarelawan untuk penyampaian maklumat mengenai haba. TOA PAYOH dan BISHAN mempunyai haba tinggi, tetapi masing-masing dikehadkan sebagai Tinggi dan Sederhana dari segi kerentanan. SOUTHERN ISLANDS dan SUNGEI KADUT mempunyai haba tinggi tetapi tiada blok HDB untuk dinilai. Utamakan TOA PAYOH, kemudian BISHAN.
Nota: Haba tinggi tetapi tidak dinilai (tiada blok HDB yang disahkan, maka tiada blok atau panggilan): Southern Islands dan Sungei Kadut.
Draf sahaja: tiada apa-apa yang telah dihantar. Seorang individu meluluskan; Pusat Penuaan Aktif memadankan blok tersebut dengan senarai pelanggannya sendiri (CoolCheck tidak menyimpan data peribadi). Haba diramalkan mengikut kawasan perancangan; blok mengkehadkan kerentanan, bukan haba. Jarak adalah garis lurus, bukan jarak berjalan kaki.
```

Back-translation:

```
All islands have 8 volunteers for the delivery of information about heat. TOA PAYOH and BISHAN have high heat, but each is limited as High and Medium in terms of vulnerability. SOUTHERN ISLANDS and SUNGEI KADUT have high heat but no HDB block to be assessed. Prioritize TOA PAYOH, then BISHAN.  
Note: High heat but not assessed (no verified HDB block, therefore no block or call): Southern Islands and Sungei Kadut.  
Draft only: nothing has been submitted. One individual approves; the Active Aging Centre matches that block with its own customer list (CoolCheck does not store personal data). Heat is predicted according to planning area; blocks limit vulnerability, not heat. Distance is straight‑line, not walking distance.
```

Checks: {"untranslated_sentences": [], "numbers_missing_in_translation": [], "numbers_missing_in_back_translation": [], "ungrounded_numbers_in_translation": [], "blocks_missing_in_translation": [], "blocks_missing_in_back_translation": [], "names_missing_in_translation": [], "names_missing_in_back_translation": [], "nothing_sent_kept": false, "draft_word_kept": true, "passed": false}

## Tamil (as used in Singapore): "We have 500 calls for tomorrow." (2026-10-23)

Draft source: agent. Tool calls: [{"name": "get_priority_areas", "arguments": {"target_date": "2026-10-23", "call_capacity": 500, "region": null}, "llm_arguments": {"call_capacity": 500, "region": "ALL"}, "row_count": 41, "error": null, "elapsed_ms": 4859}]

English:

```
The whole island has no High-tier areas, but SOUTHERN ISLANDS is Not rated with High heat. The plan allocates 500 calls to TOA PAYOH, a Medium-tier area: 312 calls to Blk 208A and 188 calls to Blk 170.
Note: No rated area is High on 23 Oct. Southern Islands has High heat but is Not rated (no confirmed HDB blocks), so CoolCheck has no blocks or calls there; check with the local team.
Draft only: nothing has been sent. A person approves; the Active Ageing Centre matches the blocks against its own client list (CoolCheck holds no personal data). Heat is forecast per planning area; blocks rank vulnerability, never heat. Distances are straight lines, not walking distances.
```

### `system.ai.meta-llama-3-3-70b-instruct`: DRIFT (14 s)

Translation:

```
முழு தீவும் உயர் தரமான பகுதிகளைக் கொண்டிருக்கவில்லை, ஆனால் SOUTHERN ISLANDS [தெற்குத் தீவுகள்] உயர் வெப்பத்துடன் மதிப்பிடப்படவில்லை. திட்டம் 500 அழைப்புகளை TOA PAYOH [தோ பாயோ] என்ற மத்திய தரமான பகுதிக்கு ஒதுக்குகிறது: 312 அழைப்புகள் Blk 208A க்கும், 188 அழைப்புகள் Blk 170 க்கும்.
குறிப்பு: மதிப்பிடப்பட்ட எந்த பகுதியும் 23 அக்டோபர் அன்று உயர் தரமானது அல்ல. Southern Islands [தெற்குத் தீவுகள்] உயர் வெப்பத்தைக் கொண்டுள்ளது, ஆனால் மதிப்பிடப்படவில்லை (உறுதிப்படுத்தப்பட்ட HDB குடியிருப்புகள் இல்லை), எனவே CoolCheck அங்கு எந்த குடியிருப்புகளையும் அழைப்புகளையும் கொண்டிருக்கவில்லை; உள்ளூர் அணியைத் தொடர்பு கொள்ளுங்கள்.
வரைவு மட்டுமே: எதுவும் அனுப்பப்படவில்லை. ஒரு நபர் ஒப்புதல் அளிக்கிறார்; Active Ageing Centre [செயல்படு வயதானவர் மையம்] தனது சொந்த வாடிக்கையாளர் பட்டியலுடன் குடியிருப்புகளை ஒப்பிடுகிறது (CoolCheck எந்த தனிப்பட்ட தரவையும் வைத்திருக்கவில்லை). வெப்பநிலை திட்டமிடல் பகுதி அடிப்படையில் முன்கூட்டியே மதிப்பிடப்படுகிறது; குடியிருப்புகள் வளமையை மதிப்பிடுகின்றன, வெப்பத்தை அல்ல. தூரங்கள் நேர்கோடுகளாகும், நடக்கும் தூரங்கள் அல்ல.
```

Back-translation:

```
The whole island does not have high‑quality areas, but SOUTHERN ISLANDS [Southern Islands] is not rated as high temperature. The plan allocates 500 calls to the medium‑quality area TOA PAYOH [Toa Payoh]: 312 calls to Blk 208A and 188 calls to Blk 170.  
Note: No area rated on 23 October is high‑quality. Southern Islands [Southern Islands] has high temperature, but is not rated (no confirmed HDB residences), therefore CoolCheck has no residences or calls there; contact the local team.  
Scope only: nothing has been sent. One person gives consent; Active Ageing Centre [Active Ageing Centre] compares residences with its own customer list (CoolCheck holds no personal data). Temperature planning is pre‑rated based on area; residences are rated for wealth, not temperature. Distances are straight lines, not walking distances.
```

Checks: {"untranslated_sentences": [], "numbers_missing_in_translation": [], "numbers_missing_in_back_translation": [], "ungrounded_numbers_in_translation": [], "blocks_missing_in_translation": [], "blocks_missing_in_back_translation": [], "names_missing_in_translation": [], "names_missing_in_back_translation": [], "nothing_sent_kept": true, "draft_word_kept": false, "passed": false}

### `system.ai.qwen35-122b-a10b`: DRIFT (4 s)

Translation:

```
முழு தீவிலும் உயர் தரப்பகுதிகள் எதுவும் இல்லை, ஆனால் SOUTHERN ISLANDS (தெற்குத் தீவுகள்) உயர் வெப்பத்திற்கு மதிப்பிடப்படவில்லை. இந்தத் திட்டம் TOA PAYOH (தோ பாயோ) என்ற நடுத்தர தரப்பகுதிக்கு 500 அழைப்புகளை ஒதுக்குகிறது: Blk 208A-க்கு 312 அழைப்புகள் மற்றும் Blk 170-க்கு 188 அழைப்புகள்.
குறிப்பு: 23 Oct அன்று எந்த மதிப்பிடப்பட்ட பகுதியும் உயர் வெப்பம் அல்ல. Southern Islands-க்கு உயர் வெப்பம் உள்ளது, ஆனால் அது மதிப்பிடப்படவில்லை (உறுதிப்படுத்தப்பட்ட HDB கட்டிடங்கள் இல்லை), எனவே CoolCheck-க்கு அங்கு எந்தக் கட்டிடங்களோ அழைப்புகளோ இல்லை; உள்ளூர் குழுவைச் சரிபார்க்கவும்.
வரைவு மட்டுமே: எதுவும் அனுப்பப்படவில்லை. ஒருவர் ஒப்புதல் அளிக்கிறார்; Active Ageing Centre (செயல்பாட்டு வயது முதிர்வு மையம்) தனது சொந்த வாடிக்கையாளர் பட்டியலுடன் கட்டிடங்களைப் பொருத்துகிறது (CoolCheck-க்கு தனிநபர் தரவுகள் எதுவும் இல்லை). வெப்பம் திட்டமிடல் பகுதிக்குத் திட்டமிடப்படுகிறது; கட்டிடங்கள் வெப்பத்தை அல்ல, ஆபத்தை வரிசைப்படுத்துகின்றன. தூரங்கள் நேர்கோட்டுத் தூரங்கள், நடந்து செல்லும் தூரங்கள் அல்ல.
```

Back-translation:

```
There are no high‑risk areas on the entire island, but SOUTHERN ISLANDS (Southern Islands) is not rated for high temperature. This project allocates 500 calls to the medium‑risk area TOA PAYOH (To Payoh): 312 calls to Blk 208A and 188 calls to Blk 170.  
Note: On 23 Oct no rated area is high temperature. Southern Islands has high temperature, but it is not rated (no confirmed HDB buildings), therefore there are no buildings or calls for CoolCheck there; check with the local team.  
Scope only: nothing has been sent. One person gives approval; the Active Ageing Centre matches buildings with its own customer list (CoolCheck has no individual data). Temperature is planned for the planning area; buildings rank risk, not temperature. Distances are straight‑line distances, not walking distances.
```

Checks: {"untranslated_sentences": [], "numbers_missing_in_translation": [], "numbers_missing_in_back_translation": [], "ungrounded_numbers_in_translation": [], "blocks_missing_in_translation": [], "blocks_missing_in_back_translation": [], "names_missing_in_translation": [], "names_missing_in_back_translation": [], "nothing_sent_kept": true, "draft_word_kept": false, "passed": false}

## Simplified Chinese (as used in Singapore): "Only 8 volunteers tomorrow, North-East only." (2026-10-24)

Draft source: agent. Tool calls: [{"name": "get_priority_areas", "arguments": {"target_date": "2026-10-24", "call_capacity": 200, "region": "NORTH-EAST"}, "llm_arguments": {"volunteers": 8, "region": "NORTH-EAST"}, "row_count": 6, "error": null, "elapsed_ms": 1359}]

English:

```
For the North-East region, the Active Ageing Centre should focus on Sengkang, with 1687 rental 1-2 room flats, and Moderate heat forecast. The priority block is 182 Rivervale Cres, with 438 rental 1-2 room flats, and a refuge within 0 m. All 200 calls are allocated to this block.
Draft only: nothing has been sent. A person approves; the Active Ageing Centre matches the blocks against its own client list (CoolCheck holds no personal data). Heat is forecast per planning area; blocks rank vulnerability, never heat. Distances are straight lines, not walking distances.
```

### `system.ai.meta-llama-3-3-70b-instruct`: DRIFT (3 s)

Translation:

```
对于东北地区，活跃老龄中心应该关注盛港 [Sengkang]，那里有1687套1-2房租赁公寓，中等热度预报。优先考虑的楼块是182 Rivervale Cres [里弗谷弯]，那里有438套1-2房租赁公寓，距离0 m就有一个避难所。所有200个电话都分配到这个楼块。
草稿：尚未发送任何内容。一个人批准；活跃老龄中心将楼块与其自己的客户名单进行匹配（CoolCheck不持有任何个人数据）。热度预报按规划区域进行；楼块排名按脆弱性排序，而不是热度。距离是直线距离，而不是步行距离。
```

Back-translation:

```
For the Northeast region, the active senior center should focus on Sengkang, where there are 1,687 one- to two-bedroom rental apartments, with a medium heat forecast. The priority building block is 182 Rivervale Cres, where there are 438 one- to two-bedroom rental apartments, and a shelter is located 0 m away. All 200 phone numbers are assigned to this building block.
Draft: No content has been sent yet. One person approved; the active senior center matches the building block with its own client list (CoolCheck holds no personal data). Heat forecasts are made by planning area; building block rankings are ordered by vulnerability, not by heat. Distance is straight-line distance, not walking distance.
```

Checks: {"untranslated_sentences": [], "numbers_missing_in_translation": [], "numbers_missing_in_back_translation": [1.0, 2.0, 1.0, 2.0], "ungrounded_numbers_in_translation": [], "blocks_missing_in_translation": [], "blocks_missing_in_back_translation": [], "names_missing_in_translation": [], "names_missing_in_back_translation": [], "nothing_sent_kept": true, "draft_word_kept": true, "passed": false}

### `system.ai.qwen35-122b-a10b`: DRIFT (3 s)

Translation:

```
针对东北区，活跃老化中心应聚焦盛港（Sengkang），该区有 1687 个 1-2 房组屋出租单位，并预报有中度高温。优先组屋大厦为 182 Rivervale Cres（182 河滨径），有 438 个 1-2 房组屋出租单位，且 0 米内设有庇护所。全部 200 通电话均分配至该大厦。  
仅属草案：尚未发出任何文件。需经一人批准；活跃老化中心将组屋大厦与其自身客户名单进行核对（CoolCheck 不持有任何个人资料）。高温预报按规划区发布；组屋大厦按脆弱性排序，而非按高温排序。距离为直线距离，非步行距离。
```

Back-translation:

```
Targeting the Northeast region, the active aging center should focus on Sengkang; this area has 1,687 one- to two-bedroom HDB rental units and a forecast of moderate high temperature. The priority HDB building is 182 Rivervale Cres, which has 438 one- to two-bedroom HDB rental units and a shelter located within 0 meters. All 200 phone calls are allocated to this building.  
Draft only: no documents have been issued. Approval by one person is required; the active aging center will cross‑check the HDB building with its own client list (CoolCheck holds no personal data). The high‑temperature forecast is released by planning zone; HDB buildings are ordered by vulnerability, not by high temperature. Distance is straight‑line distance, not walking distance.
```

Checks: {"untranslated_sentences": [], "numbers_missing_in_translation": [], "numbers_missing_in_back_translation": [1.0, 2.0, 1.0, 2.0], "ungrounded_numbers_in_translation": [], "blocks_missing_in_translation": [], "blocks_missing_in_back_translation": [], "names_missing_in_translation": [], "names_missing_in_back_translation": [], "nothing_sent_kept": false, "draft_word_kept": true, "passed": false}
