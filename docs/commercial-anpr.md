<!-- Internal research, 26 Sep 2026: not a submission document. Built by four research passes and a synthesis, fact-checked (10 of 12 key claims verified in full, 2 partly, both corrected here). -->
# Commercial-grade ANPR and speed enforcement: how it works, what Indian buyers test, and how far Sentinel is from it

For the team lead · 26 Sep 2026 · Built from four research passes (toll, speed, models, Indian specs), plus my own checks against the primary sources and against the repo.

## The short answer

- **Commercial systems have the same software shape as Sentinel.** Toll and speed-camera ANPR detect the plate, read it, apply plate rules, vote across frames and match. What makes them commercial grade is mostly *not* the recognition model. It is five other things:
  1. **A camera built and placed for plates:** global shutter, pulsed infrared, a trigger, and a known number of pixels on each character.
  2. **A certified speed or time measurement** before any ticket is issued.
  3. **A signed evidence package.**
  4. **A person checking the read** before anything goes out.
  5. **Accuracy proven on the buyer's terms,** plus certificates.
- **Indian buyers already write all of this into their documents.**
  - IHMCL's March 2026 free-flow toll tender for five Gujarat plazas asks for 99% ANPR accuracy day and night "without any manual validation/audit" as a site acceptance test criterion (its ongoing SLA sets 99% daily only for vehicle count and classification). It requires global-shutter cameras of 3 MP or better, infrared, a LiDAR trigger, and video from 5 s before to 5 s after each event [20].
  - NHAI's highway spec has an operator check every machine-read plate against the image before an e-challan. Every correction is logged and 100% audited by a manager [25].
  - CMVR Rule 167A requires a state-signed accuracy certificate, renewed every year, for every enforcement device. That includes ANPR and CCTV [3].
- **The model matters less than it looks.**
  - Plate *detection* is close to solved: YOLOv4 kept an average recall above 99.5% even on datasets it never saw [77].
  - In the 2026 ICPR low-resolution plate competition, the top 10 of 99 valid entries were within 3.13 points of each other, with no dominant architecture [81].
  - What moves results by tens of points is pixels on the plate, new sites and plate layouts. OpenALPR read 94.3% of car plates but 45.7% of two-row motorcycle plates on the same toll dataset [77]. On our own stock footage, the close camera captured 91.2% of plates and the wide one 21.7% [110].
- **Sentinel today.** 90 of 120 stored vehicle plates (75.0%) were exactly right, 107 (89.2%) within one character, on the organisers' sandbox cameras where plates are readable (all but one on CAM06 and CAM07; the other on CAM12) [118].
  - A team member checked them blind on the plate review page on 26 Sep (crop only; the server grades the typed reading). One reviewer so far.
  - At Sentinel's confidence 0.9 or above: 69 of 81 exact (85.2%), 79 within one character. Between 0.5 and 0.7: 8 of 18. That supports confidence routing: pass the high band, send the rest to a person.
  - An earlier check by the AI assistant, with the stored read in view (not blind), gave 92 of 107 (86.0%). It was optimistic.
  - Why the 30 misses missed, by the AI assistant's review of the crops (not a person, so it corrects nothing): 13 are Sentinel's (a character dropped near the plate's end 5, look-alike letters 3, digits 3, the vote 1, a short plate box 1), 13 the reviewer's typing, 1 both, 3 unclear. The figure stays 90 of 120 until a second blind reviewer reads them [121].
  - 25 changes to how a crop is read, tried without training with the gain rule fixed first, did not beat the shipped model on real plates [122]. The Indian-format fine-tune, behind gates, is the lever; nothing changes before the submission [112][123].
  - A per-camera plate-reading quality report now grades every capture and tiers each camera with advice (CAM06 and CAM07 marginal, the rest counts-only). Its grade does not predict a right read on real plates; the reader's confidence does [120].
  - The capture rate is unknown.
  - That is a promising figure for investigative analytics on existing CCTV. It is not enforcement grade, and there is no path to toll-grade 99% on surveillance CCTV.
- **Recommendation: three products.**
  - (A) ANPR and event analytics on existing city CCTV, sold with honest per-camera measurement.
  - (B) A purpose-built ANPR lane kit: partner OEM camera, IR, trigger, edge box, our software.
  - (C) A review-and-evidence back office: human verification, signed evidence, eChallan integration. It can also sit on other vendors' cameras.
  - For speed enforcement, integrate certified speed sensors; don't build metrology.
  - Don't bid for free-flow tolling directly. IHMCL requires the OEM to have been in business for at least 3 years and the product to have run in an MLFF system for at least 1 year [20].

How to read this report:
- **[n]** is a source in the numbered list at the end.
- **Vendor claim** means a datasheet or marketing figure that nobody independently measured.
- **Derived** means my own arithmetic from cited inputs, not a published figure.
- **Unknown** means it was searched for and not found.

---

## 1. How commercial toll-lane and free-flow ANPR works

### 1.1 Step by step (IHMCL's multi-lane free-flow spec for Gujarat, with other practice alongside)

| Step | What happens | Numbers that matter |
|---|---|---|
| **1. Detect the vehicle (trigger)** | An overhead LiDAR sees the vehicle enter the capture zone and triggers the cameras. A radar tracks every vehicle across the lanes [20]. Older lanes use inductive loops [45]. Some ANPR cameras trigger themselves from the plate, a built-in laser or a radar (vendor docs [57][58][59]). | LiDAR: 865–905 nm, 10–220 km/h, at least 2 lanes per unit. Radar: 76–81 GHz, up to 256 objects over 4 lanes, speed accuracy better than ±1%, certified by a government-authorised agency [20]. |
| **2. Capture** | ANPR cameras at the front and the rear (the RFP does not say how many per lane), plus left- and right-hand "audit" cameras that record the whole scene [20]. | Progressive-scan **global-shutter** CMOS, **3 MP or better**, 50/60 fps. Shutter from 1 s to 1/100,000 s, about 40 m range, 150 km/h or more. **Video from t−5 s to t+5 s** around each event. Must read retroreflective and non-retroreflective plates, day and night. **No HiSilicon chipset.** Audit cameras 2048×1536 [20]. |
| **3. Light the plate** | Pulsed IR fires in step with the shutter, so the plate is bright while headlights and sun are suppressed. Adaptive Recognition alternates flash strength on odd and even frames, so reflective and non-reflective plates both come out readable (vendor claim) [58]. Neology runs separate IR and colour OCR channels (vendor claim) [57]. | IHMCL: invisible IR, at least 50 m, up to 75 Hz, one illuminator per lane [20]. 850 nm gives the best light output and sensor sensitivity but glows faintly. 940 nm is almost covert but needs much more light. 740 nm sees through windscreens [60]. |
| **4. Read on the edge** | The engine returns the plate text, a confidence per character, alternative readings for each character, and the plate type or country [55]. | Carmen's plate confidence is the product (or mean) of a text factor, a plate-type factor and a position factor [55]. |
| **5. Route by confidence** | Confident reads bill automatically; the rest go to people. | IHMCL toll plazas (ETC) grade confidence as Good (100%), Average (95–99.99%) or Poor (<95%). The plate text replaces a failed tag read only above 95% [24]. The free-flow tender says the lane software decides "based on the confidence" of RFID and ANPR but gives no threshold. A bidder asked and was told "As per RFP" [20][21]. |
| **6. Fuse** | FASTag (RFID) is primary and ANPR is the fallback. Front and rear reads are correlated, and vehicle counts are cross-checked across ANPR, RFID, LiDAR and lane counters [20]. | A vehicle that ANPR missed through frame loss, latency or overload counts against ANPR accuracy [20]. The Illinois Tollway lane runs: detect → front plate → transponder → axle count → track → rear plate → transaction [46]. |
| **7. Exceptions and human review** | A separate control-centre team validates low-confidence cases. That team sees only pending items, an auditor authorises e-notices, and every rejection needs a written reason. If RFID and ANPR both fail, staff identify the vehicle from audit footage within 24 h [20]. | — |
| **8. Back office** | Owner lookup (VAHAN), the e-notice, payment. | E-notice within 48 h for closed, blacklisted or unregistered tags. The bank is paid for an e-notice only with clear front and rear photographs [20]. Penalties: ₹1,00,000 per incorrect manual plate-based transaction, ₹10,000 per wrong e-notice, ₹10,000 per vehicle with no images or video. Uptime 99.9% (44 min a month) [20]. These penalties push every design towards precision, with people handling the doubtful reads. |

### 1.2 The numbers that decide whether a plate can be read

**Pixels on the plate (published guidance)**

| Source | Guidance |
|---|---|
| Axis white paper | 100–150 px across the plate for most LPR software, and at least 75 px for full-contrast characters. Keep the total angle under 30°. Switch WDR off [51]. |
| Adaptive Recognition (Carmen) | Characters at least 10 px tall (Latin script), best at 20–60 px; accuracy falls again at about 70–80 px. Strokes at least 2 px wide [54]. |
| Genetec, from Bosch's supplier appendix | Characters 30–60 px tall [53] |
| Plate Recognizer | Design for about 100 px of plate width. Its own stress test failed at about 30 px [61]. |
| Axis License Plate Verifier (on-camera app) | Plate width at least 130 px for one-row plates, 70 px for two-row [52] |

**Motion blur and frames**
- Axis gives the longest usable exposure at 130 km/h by camera angle to the direction of travel: 4.5 ms at 5°, 2.2 ms at 10°, 1.5 ms at 15° and 0.8 ms at 30° [51].
- Bosch recommends 1/500 s for stop-start traffic and 1/1750–1/2500 s at 120 km/h. Some engines want up to 7 consecutive frames: at 144 km/h and 25 fps the plate must stay sharp over about 13 m, and at 60 fps over about 6.5 m [53].

**Indian plates, what the arithmetic says (derived)**

The inputs: Rule 51 makes car characters 65 mm tall with a 10 mm stroke; motorcycle rear letters are 35 mm and numerals 40 mm [14]. Rule 50 makes plates two-line by default, with car plates 340×200 mm or 500×120 mm [13].
- **Density needed:** 20 px characters need about 0.31 px/mm (about 310 px/m) at the plate.
- **Lane coverage:** 1920 px across one 3.5 m lane gives about 550 px/m, so characters about 36 px tall. Across two lanes they are about 18 px. Across a 20 m junction they are about 6 px, which is below every vendor minimum.
- **A small plate image:** a 500 mm single-line plate imaged 60 px wide has characters about 8 px tall.
- **Motorcycles:** 20 px on a 35 mm letter needs about 570 px/m.
- **Blur:** at 60 km/h a car moves about 33 cm during a 1/50 s exposure (five character heights) and about 8 mm at 1/2000 s. The exposure settings of the sandbox cameras are unknown.

**What Sentinel sees**
- On the sandbox cameras where the detector found any plates, the median plate-box width was 40–89 px in stream pixels [109].
- On our stock footage, the close camera (median read box 106 px) captured 91.2% of the plates on screen for at least 1 s. The wide camera (55 px) captured 21.7% [110].
- That is exactly what the vendor guidance predicts.

**An Indian risk for any night ANPR**
- The HSRP standard AIS-159 specifies plate reflectivity only under visible light (white at least 45 cd/lx/m²). It sets no infrared requirement and no typeface [15].
- Toll bidders told IHMCL that many Indian plates do not reflect IR, and IHMCL answered "As per RFP" [21].
- So infrared performance on Indian plates is not guaranteed by the plate standard.

### 1.3 How read rates are defined: the denominator decides the number

- **IHMCL site acceptance test (free-flow tolling):**
  - 99% accuracy, day and night, with no manual validation.
  - A read of **either the front or the rear plate** counts.
  - Only "humanly not readable" plates (damage, mud, stickers, tampering) are excluded. Low light, skew, fog, rain and glare are **not** excused if IR, multi-angle capture, HDR or enhancement could fix them.
  - Accuracy is reported separately for each scenario, and a vehicle lost to frame loss counts as a miss [20].
  - A bidder asked for 95% and was refused [21]. The 2025 Dwarka Expressway tender kept 99.5% on standard plates visible to the human eye, even during a 6-month stabilisation period [23].
- **UK NASPLE v3.5 (July 2026):**
  - Capture rate = plates logged ÷ plates visible to the human eye. Read rate = correct reads ÷ plates captured.
  - Fixed ANPR cameras must capture 98% and read 95%. **CCTV working in ANPR mode must capture 85% and read 95%.**
  - Tested on at least **250 consecutive vehicles** (or 2 hours) per lane, day and night, with the read rate reviewed at least yearly [34].
  - Read-to-alarm within 4 s for fixed cameras [34].
- **US DHS 2025 market survey:** vendor capture and read figures of 90–99.5%, stated as "not independently verified". Examples: Jenoptik 99.5% capture / 98% read, Genetec 98.6/97.8, Rekor 99/98, Plate Recognizer >99/>99 [45].
- **Other vendor claims:**
  - Hikvision: >99% capture and >98% read "under recommended installation and lighting" [59].
  - Tattile: 99.9% detection and 99.5% accuracy [116].
  - Vitronic: >99% on human-readable plates [115].
- **Independent check:** across eight public datasets, the commercial engines Sighthound and OpenALPR averaged 9.1 and 6.2 points below the research system's 96.9% (IET ITS 2021) [76].

**What this means for us.** Sentinel's 75.0% (blind) measures something different from all of these:
- It is the precision of stored reads.
- It is one person's reading of the stored crops.
- It has no capture denominator.

It cannot be compared with any of the figures above until we measure the way NASPLE or IHMCL do.

### 1.4 How much goes to people in practice

- **Florida:** up to about 140 million toll-by-plate transactions a year, about 42%, need manual review. This is Florida DOT as quoted in a patent, so it is second-hand [48].
- **Maryland:** video tolls are billed only after manual review [47].
- **India's free-flow plazas, May–Jul 2026 (news):** 1.1 crore transactions and about 10.5 lakh e-notices [106]. This mixes tag failures with vehicles that have no tag, so it is **not** an ANPR review rate.
- **Choryasi, near Surat** (live since May 2026 [105]): measured ANPR accuracy and the manual-review share are unknown.

---

## 2. Speed cameras that issue tickets automatically

### 2.1 Three ways to measure speed

- **Spot speed by radar.**
  - A UK Gatso fixed camera uses 24.110 GHz radar with a 5° beam at 20° to the kerb. It takes two photos 0.5–0.7 s apart, and road markings at known spacing give a second distance-over-time speed, which must agree within 10% [43].
  - Tracking radars follow many vehicles. Sensys Gatso's RT4 measures range, speed and angle 32 times a second, tracks from 0 to 150 m, triggers at 10–80 m and enforces up to 6 lanes (vendor manual) [63]. Jenoptik VECTOR SR claims ±1 mph over 12.5–186 mph, across 3 lanes (vendor claim) [64].
- **Spot speed by lidar.** Vitronic PoliScan claims up to 4 lanes, 2 directions and 320 km/h (vendor claim) [65].
- **Fixed-distance sensors** (loops, piezo strips, light barriers). OIML cites two pressure strips as *insufficient* redundancy: a motorcycle's front wheel can jump the first strip, so the time measured is far too short [37].
- **Section (average) speed.** ANPR at the entry and exit points; speed = distance ÷ time.
  - OIML R 91-1:2025 requires:
    - each detection field no longer than 0.5% of the shortest section;
    - an image and a timestamp at every point;
    - a continuous time-sync check, with enforcement stopped the moment it fails;
    - a time MPE of 0.3%.
  - GNSS-only time sync counts as insufficient redundancy [37].
  - The UK requires:
    - only one possible route between entry and exit;
    - the distance measured three times, agreeing within 1%, with the shortest used;
    - records under the threshold deleted within an hour;
    - an operator's check of each violation before it is exported [38].
- **Video-based speed** is a new category in OIML R 91-1:2025. The device must mark the vehicle positions in the evidence and must refuse to measure when image quality cannot guarantee the permitted error [37].
- **Effect on crashes** (Høye 2014 meta-analysis, via the EU Road Safety DSS):
  - section control: −30% total crashes, −56% fatal and serious;
  - fixed cameras: about −20% total crashes [44].
- **India:**
  - NHAI's 2021 ATMS spec makes the speed-enforcement system (VSDS) **ANPR-camera based**, one camera per lane, covering spot and section speed. Radar only drives the speed display shown to drivers [25].
  - NHAI's 2023 policy places enforcement gantries (VIDES) about every 10 km, detecting spot and sectional speeding for e-challans. The radar speed displays carry no ANPR and issue no challans [26].

### 2.2 Tying the speed to the right plate

- **OIML §6.6:** a speed must never be given to the wrong vehicle, including when one overtakes another. If the vehicle was outside the zone where identification is certain, the device cancels the measurement and produces **no evidence file** [37].
- **Germany (PTB-A 12.01):** each value is assigned to one vehicle unambiguously (e.g. by lane), and occlusion errors in multi-lane traffic must be excluded [39].
- **How vendors do it:**
  - project the tracking radar or lidar position into the image and draw a frame around the offending plate [65];
  - print the lane in the data bar [63];
  - use one ANPR camera per lane (NHAI) [25].

### 2.3 The evidence package

- **OIML §7.3–7.4.** The evidence file holds:
  - date and time, location and a unique ID;
  - speed, direction and the speed limit;
  - device type and serial number;
  - photos or video;
  - the lane or a marker;
  - the device configuration.

  It must be secured for integrity and authenticity, with the private signing key unreadable outside the device. Viewing software checks authenticity automatically, and files are stored securely for about 3 months at the device [37].
- **Germany.** Image and measurement data sit inseparably in one case file with an asymmetric signature, and lossy compression must not change plate characters [39]. Two court decisions set the practice:
  - The Saarland Constitutional Court (2019) threw out TraffiStar S350 readings because the device kept no raw data [41].
  - The Federal Constitutional Court (2020) gave defendants access to the logbook, the calibration certificate and the raw data [42].

  **The design lesson: keep the raw data.**
- **UK:** AES-128-CBC with a 16-byte MAC computed over the whole image [38].
- **Vendor example (Sensys Gatso):** the data bar shows date, time, event number, lane, speed, direction, vehicle type, image interval, limits, location, serial number and approval number. The camera is 5120×3840, with an 850 nm IR flash of 10–1000 µs [63].
- **India:**
  - **Rule 167A** requires a photo showing the offence and the plate, plus the device's measurement [6]. The challan also carries date, time, place, the provision violated, and a certificate under s.65B of the Evidence Act [7].
  - **Since 1 Jul 2024 that certificate falls under BSA s.63:** signed by the person in charge of the device and by an expert, with a hash value (MD5/SHA-256) in the Schedule format. This comes from a secondary source [8].
  - **NHAI:** ANPR video kept 60 days, speeding clips for at least 5 years [25].
  - **IHMCL:** video from t−5 s to t+5 s [20].
  - **Guwahati:** images digitally fingerprinted and encrypted, with a data bar [32].

### 2.4 Calibration and type approval

- **OIML R 91-1:2025** permits a stationary error of ±3 km/h up to 100 km/h and ±3% above [37].
- **UK:** at most +2 mph (+3% above 66 mph); an independent second speed check; annual calibration; Home Office type approval, with Dstl as its technical partner [38].
- **Germany:** recalibration every year (MessEV Annex 7) [40].
- **India:**
  - **Legal Metrology:** from 1 Jul 2025, radar speed equipment must be verified and stamped by the Legal Metrology authorities, under rules drafted from OIML R 91 [12]. **Unknown:** whether this covers ANPR/video-based speed or section speed, which is how NHAI's spec does it.
  - **NHAI 2021:** cameras and software calibrated monthly with a certified test report, plus third-party test and calibration certificates [25].
  - **Gujarat's SASGUJ tender (2017):** speed accurate to ±10 km/h, "tested & certified by the competent certifying body for the acceptance as an evidence in the court of law" at the factory acceptance test and every year after [28].
  - **Rule 167A:** an annual state certificate for each device [3].
  - **Visakhapatnam (GVMC) tender:** the analytics OEM must hold ARAI certificates for speed detection and ANPR [31].
  - **Unknown:** ARAI's test procedure for ANPR or speed. My search found none published.
  - **Mumbai–Pune:** the expressway system went live without prior device approval and was approved later without technical verification (PTI) [103].

### 2.5 Back office and human verification

- **Abroad:**
  - UK: an operator verifies each record before export [38].
  - New York work zones: a certified technician reviews each violation before the notice is mailed [117].
  - Washington State: an officer certifies each infraction after inspecting the images, and the cameras may image only the vehicle and plate, never faces [50].
- **NHAI 2021 spec:**
  - The operator matches the system's plate read with the image and may edit it.
  - Every correction is logged and 100% audited by the manager.
  - Unread plates become incidents for manual entry.
  - Only then does the software generate the e-challan and SMS, using VAHAN and the NPCI FASTag mapper [25].
- **Indian practice (news):**
  - **Kerala** (726 cameras): the control room verifies, the Motor Vehicles Department (MVD) re-examines and approves, and the challan follows within about 6 h [101].
  - **Mumbai–Pune** (40 gantries): operators verify and the RTO approves. 27.76 lakh e-challans worth ₹470 cr, of which ₹51 cr was recovered [102]. The operator is paid ₹555 + GST per challan [103].
  - **Bengaluru:** false seatbelt tickets, and rivets read as zeros, led to manual validation. Police claim 99.9% after validation [104].
- **Error rates are rarely published.**
  - NYC's 2024 audit found errors in about 12% of sampled events, mostly events *wrongly rejected* (lost enforcement). Missing or obscured plates cost at least $108M [49].
  - No Indian false-challan rate was found.

### 2.6 What Indian law requires

- **MV Act s.136A (2019).** The State Government must ensure electronic monitoring and enforcement on national highways, state highways and urban roads, and the Centre makes the rules [1]. The Supreme Court (2 Sep 2024, S. Rajaseekaran) directed every State to implement s.136A and Rule 167A [2].
- **CMVR Rule 167A (G.S.R. 575(E), Aug 2021):**
  - **Devices:** speed camera, CCTV, speed gun, body camera, dashcam, ANPR and weigh-in-motion. Each needs a certificate "signed by a designated authority of the State Government certifying that the device is accurate and operating properly", **renewed yearly** [3].
  - **Placement:** high-risk NH/SH corridors and critical junctions in cities over 1 million, plus 132 listed cities. Gujarat's are Surat, Ahmedabad, Vadodara and Rajkot [4].
  - **Footage:** must carry an electronic stamp of location, date and time, and may support challans for 12 offence categories, speeding first. Warning signs are required before monitored stretches [5].
  - **The challan:** clear photos of the offence and the plate, plus the device's measurement. The notice goes out **within 15 days**, and records are kept until the challan is disposed of, or until any proceedings and appeals end [6].
- **The Rule 167 rewrite** (draft G.S.R. 723(E), 29 Sep 2025 [9]; final Third Amendment Rules 2026 as reported by a secondary source [10]):
  - auto-generated challans are allowed;
  - delivery within 3 days electronically or 15 days by post;
  - 45 days to pay or contest, then the challan is deemed accepted;
  - the authority must decide within 30 days;
  - a 50% deposit is needed to go to court;
  - unpaid challans flag the vehicle "Not to be Transacted".

  Whether the final text matches the draft is **uncertain**; only secondary summaries were read.
- **Courts:** on 5 May 2026 a Srinagar magistrate quashed challans issued from officers' personal phones, because Rule 167A needs approved, certified devices [11].
- **What this means for a product:**
  - Each device (camera plus software) needs the annual state certificate.
  - Radar speed also needs Legal Metrology stamping.
  - Evidence must carry location, date and time, and come with a BSA s.63 certificate.
  - The Rule 167A text I read does not itself mandate a person checking each challan. The NHAI spec does [25], and every Indian deployment in this research uses one.

### 2.7 Gujarat today

- **eChallan (NIC Gujarat, Apr 2025):**
  - live in all 38 police districts since 2023;
  - fed by CCTV, ANPR, speed guns, red-light (RLVD) and stop-line (SLVD) detection;
  - vehicle details from VAHAN and licences from SARATHI;
  - geo-tagged, time-stamped photos, sent by SMS, e-mail or post;
  - unpaid after 90 days, sent to the Virtual Court;
  - 66.79 lakh challans and ₹497 cr recovered, as of 20 Mar 2025 [98].
- **VISWAS:** Phase I has 7,000+ cameras across 41 locations, with 34 NETRAM district centres and TRINETRA in Gandhinagar; Phase II adds 10,500+ cameras (news) [99].
- **Delhi–Mumbai Expressway, Vadodara–Navsari stretch (news, May 2026):** ANPR speed detection every 10 km; limits 120 km/h for cars, 100 for buses and trucks, 80 for vehicles with more than 4 axles; ₹1,500 e-challan [100].
- **Unknown:** whether a person checks each Gujarat camera challan before it is issued.

---

## 3. What models they use, and why the model is rarely the differentiator

### 3.1 The model stack

1. **Vehicle detector:** YOLOv5m in Hailo's reference app; TrafficCamNet in NVIDIA's (vendor docs [69][66]).
2. **Plate detector:** Tiny-YOLOv4 (Hailo; NVIDIA LPDNet) [69][68]. Corner-regressing models such as IWPOD-NET (MIT licence) also unwarp oblique plates [87].
3. **Layout or plate-type classifier:** Carmen's plate "types" encode syntax, layout and font [55].
4. **OCR:**
   - segmentation-free CNN + CTC (LPRNet: 3 ms per plate on a GTX 1080) [82];
   - transformers (PARSeq [83]). On Indian truck plates, YOLOv7 + PARSeq scored 95.82% on the authors' own data [84];
   - character-detection OCR, which handles two-row plates natively [76].
5. **Syntax engine:** position rules (letter vs digit per slot) [76].
6. **Tracker, quality gate and multi-frame fusion.** Hailo uses a Kalman tracker plus an edge-variance filter that skips blurred plates [69].
7. **Confidence and rejection.** MC-dropout reached AUC 0.995 at flagging misreads on CCPD [90]; a legibility classifier (4 classes) decides what to enhance or reject [91].
8. **Human review.**

Commercial vendors (Jenoptik, Vitronic, Sensys Gatso, IDEMIA, Indian ITMS integrators) **publish no architectures: unknown.**

Sentinel already has steps 2, 4, 5 and 6: a YOLOv11n detector plus a classical text-line finder, CCT-XS OCR, Indian rules, and a per-character vote. It also has a COCO vehicle detector and stores confidences. It has no corner rectification, no layout classifier and no confidence-based routing.

### 3.2 What actually moves accuracy

| Lever | Measured effect | Source |
|---|---|---|
| Choice of plate detector | YOLOv4 recall stays above 99.5% on average, even on unseen datasets: detection is not the bottleneck | [77] |
| Voting across a vehicle's frames | 85.45% → 93.53% (SSIG); 64.89% → 78.33% (UFPR-ALPR) | [75] |
| Fusing several OCR models | 92.4% → 97.6% within a dataset; 87.6% → above 90% across datasets | [79] |
| Layout classification plus position rules | +2.1 points on average, +3.6 on fixed-position layouts | [76] |
| **Indian plate rules in Sentinel** | Real sandbox crops: raw exact 60.7% → **89.3%** after normalisation (28 crops, 15 vehicles, one camera) | [111] |
| 4-point vs 2-point plate boxes (Indian data) | LPRNet 75.6% vs 66.3% | [86] |
| Super-resolution plus multi-frame on tiny plates | 1.7% → 31.1% → 44.7% | [80] |
| **A new site or dataset** | 82.4% → 74.5% average; AOLP 90.8% → 62.7% | [77] |
| Near-duplicates between training and test | AOLP error more than doubles once the splits are fair | [78] |
| **Two-row plates** | OpenALPR: 94.3% of cars vs 45.7% of motorcycles | [77] |
| **Pixels on the plate** (Sentinel, synthetic plates) | 106 px → 91.2% capture; 55 px → 21.7% | [110] |

### 3.3 Data

- **Vendor training sets (vendor docs):**
  - NVIDIA LPRNet: 310,000 proprietary US plates. LPDNet: 45,000 US images plus 172,000 CCPD images [67][68].
  - Hailo's LPRNet: 4 M synthetic plates [69].
- **Engines are per region and updated often.** Carmen's IND engine is updated quarterly [55]; Plate Recognizer updates every 3–6 weeks (vendor claim) [62].
- **Synthetic data helps:** it improved results across 16 OCR models and 12 datasets [88], and diffusion-generated plates added +3% [89].
- **Public Indian data is scarce:**
  - ILPD (16,192 images) cannot be released, for legal reasons [85][86].
  - UFPR-ALPR and RodoSol are academic, non-commercial only [96].
  - CCPD is MIT-licensed but Chinese [97].
  - The fast-plate-ocr docs do not say whether Indian plates are in its training data [95].
  - **No commercially licensed Indian plate dataset was found.**
- **What follows:** labelled crops from our own cameras are the asset.

### 3.4 Edge hardware

- **NVIDIA DeepStream LPR reference app** (1080p streams): "Jetson Orin" 5 streams at 341.65 FPS aggregate; Xavier NX 3 at 80.31; Nano 1 at 9.2; T4 14 at 447.15 [66]. Which Orin module is meant is unstated.
- **Hailo-8 with an i.MX8 host:** the full 3-network pipeline at 60 FPS on 1080p (vendor claim) [69].
- **On the camera:** Axis License Plate Verifier runs on ARTPEC-8, one licence per camera, with results in under 1 s, up to 105 km/h [52].
- **Sentinel:** one GTX 1650 Ti laptop, about 4 streams at about 4.5 analysed fps [114][113].

### 3.5 Why the model is rarely the differentiator

1. **Detection is solved** and recognition architectures are close together:
   - the ICPR 2026 top 10 were within 3.13 points, with no dominant architecture;
   - the one constant among the top entries was using all frames of the track [81];
   - no single OCR model wins everywhere [79].
2. **Input quality moves tens of points** (pixels, blur, IR contrast, two-row layout), and the camera and its placement set it. See the table above: 94.3% vs 45.7%, 91.2% vs 21.7%, 1.7% vs 44.7%.
3. **Domain shift moves 8–28 points** (82.4 → 74.5; AOLP 90.8 → 62.7) [77]. It is fixed with data from the target cameras, not with a new architecture.
4. **Buyers specify capture and process, not models.**
   - IHMCL specifies the global shutter, the IR, the LiDAR trigger, the audit cameras, a manual validation team and penalties [20].
   - NHAI specifies an operator audit [25].
   - No tender read names a detector or OCR model.
5. **Rules and fusion are cheap and large.** In our own data, Indian normalisation alone took raw exact reads from 60.7% to 89.3% [111].
6. **The legal value of a ticket comes from certified physics and signed evidence, not from AI.** The speed is certified metrology [37][12]; ANPR only identifies the vehicle.

---

## 4. What Indian government buyers specify and test

| Buyer / document | ANPR accuracy asked | How it is measured | Capture / camera | Certification, evidence, retention | Source |
|---|---|---|---|---|---|
| **Gujarat Home Dept SASGUJ RFP** (GIL, 2017; predecessor of VISWAS) | >90% standard English font and HSRP; 75% non-standard fonts; day and night; up to 120 km/h. RLVD ≥90% | Random checks at the city control centre; any shortfall counts against the SLA | 2 MP 50/60 fps for ANPR and speed; 8 MP for RLVD; 6–50 mm lens; external IR ≥50 m; IP66; ONVIF S | Speed ±10 km/h, certified for court evidence at the factory test and yearly. Video 30 days; ANPR, RLVD and speed outputs 3 months | [28] |
| SASGUJ pre-bid replies | Vendors called 90% at night "near to impossible" and asked for 70% day / 60% night. GIL: "No Change" | — | — | — | [29] |
| SASGUJ camera plan | 9,167 cameras planned, 2,833 of them ANPR | — | — | — | [30] |
| **NHAI ATMS spec** (Feb 2021) | ≥90% **at night at 180 km/h**, standard plates, within a 40 m zone | — | 2 MP 60 fps; shutter to 1/100,000 s; IR 100 m; WDR 120 dB; 1 camera per lane | **Operator checks each read, edits logged, 100% manager audit.** Monthly calibration; third-party certificates. ANPR video 60 days, speeding clips ≥5 years | [25] |
| **NHAI ATMS 2023 SLA** (IHMCL training deck) | ≥95% = 10 points, 90–95% = 5, <90% = 0 | Integrator's own reports of wrong or missed plates, plus **random NHAI audits of recorded footage** | Enforcement gantries (VIDES) about every 10 km | Evidence uploaded to eChallan within 24 h; command-centre software STQC certified | [26] |
| **IHMCL toll plazas (ETC)** (Jan 2025) | >98% on HSRP, >90% on non-HSRP; count 99.5%; classification >95% | — | 2 MP per lane, global shutter | Confidence tiers; plate text used only above 95% confidence | [24] |
| **IHMCL free-flow tolling (MLFF)**, Gujarat GJ-02 and Delhi DL-01 (Mar 2026) | **≥99% day and night without manual validation**; front or rear counts | Site acceptance test per scenario; counts checked against RFID, LiDAR and lane counters; frame loss = miss | ≥3 MP global shutter, 50/60 fps, IR ≥50 m, no HiSilicon, video t±5 s | STQC within 6 months of acceptance; CERT-In yearly; ANPR images 180 days, video 30 days; ₹ penalties per error | [20][22] |
| IHMCL Dwarka Expressway MLFF (2025) | 99.5% on standard plates visible to the eye; not relaxed during stabilisation | Non-standard plates go to audit and manual validation | — | — | [23] |
| **GVMC Visakhapatnam ITMS** (Dec 2025) | 80–85% in months 0–3, 90–95% in months 3–6, then ≥95% day and night. RLVD 95% day, 90% night | Random time-sample audits from month 3 | 1 ANPR camera per lane | **ARAI certificates for speed and ANPR**; STQC Safe-to-Host; CERT-In audit before go-live and yearly VAPT; 99.5% uptime | [31] |
| **Guwahati Smart City** | ≥80% day / ≥60% night (another clause says 70/60), standard plates | — | Speed: 4D radar 24/77 GHz, 4 lanes; ±3 km/h below 100, ±3% above; 9 MP 1" global shutter; white flash | Images fingerprinted and encrypted with a data bar; hosting in India on a MeitY-empanelled cloud | [32] |
| NHIT ATMS tender (2025) | Speed detection 98% up to 180 km/h, day and night | — | 2/4 MP; 180 days of recording | — | [27] |

**Requirements that apply across tenders**
- **Cameras:**
  - BIS registration under IS 13252.
  - Since 9 Apr 2025, MeitY's essential security requirements for CCTV, tested by third-party labs [17].
  - For government buyers, an STQC security test report, valid 3 years [18].
- **Operations** (CERT-In):
  - clocks synced to NIC/NPL NTP servers;
  - logs kept 180 days in India;
  - incidents reported within 6 h [19].
- **Devices:** the annual state certificate under Rule 167A [3]; Legal Metrology stamping for radar [12].
- **Gaps in the documents:**
  - No codified national standard for ANPR accuracy exists; the highway operators' association says so for free-flow tolling [33].
  - None of the Indian tenders read specifies pixels per character or an IR wavelength.
  - No published ARAI test procedure was found.

**The pattern**
- City tenders (60–90%) are well below highway and toll tenders (90–99%).
- Accuracy is audited on live or recorded traffic, not in a lab.
- Human validation is written in wherever tickets are issued.

---

## 5. Sentinel against commercial grade

**Where we stand.** The pipeline has the same shape: detector, OCR, Indian rules, vote across frames, tracker, watchlist.

What we lack:
- ANPR cameras (we have surveillance CCTV);
- a trigger;
- control of the IR;
- calibration or type approval;
- more than one laptop's compute;
- evidence signing;
- certified accuracy.

The measured status comes from `sandbox_review.md` (the blind check), `review_truth.md` (the check against known plates), `sandbox_eye.md` (the earlier AI check), `sandbox_daynight.md` (the two sandbox runs), `ocr_baseline.md`, `anpr_eval_current.md`, `capture_quality.md` (the per-camera report), `blind_errors.md` (the misses), `ocr_fix_trials.md`, `bench/pipeline_gates.md` and the HLD [118][119][107][108][111][110][120][121][122][123][113].

| Area | Commercial practice | Sentinel today | Gap severity | What closes it |
|---|---|---|---|---|
| **Camera** | Dedicated ANPR cameras (NHAI and GVMC specify one per lane): global shutter, ≥2–3 MP, 50/60 fps, shutter to 1/100,000 s [20][25] | Whatever CCTV exists, over RTSP; lens, exposure and angle are not ours. The sandbox cameras are mostly overview and red-light views [109] | **Critical** for enforcement and tolling; acceptable for investigative analytics on plate-viable views | Lane kit with an OEM ANPR camera; for CCTV, the per-camera plate-reading quality report (built 26 Sep [120]) and tiering |
| **Pixel budget** | Designed in: 100–150 px across the plate, characters 20–60 px [51][54] | Measured after the fact: sandbox median box widths 40–89 px on the cameras that found plates [109]; stored plates on CAM06 and CAM07 have medians of 104 and 106 px, with 39% and 36% of captures under size [120]; our wide stock camera at 55 px captured 21.7% [110] | **High** | The per-camera report grades size, blur and light and advises zooming in or moving closer [120]; lens choice on the lane kit; no plate path on cameras below the threshold |
| **Trigger** | LiDAR, loop, radar or laser trigger; counts cross-checked between sensors [20][45] | None. Video detector and tracker only, so we cannot know how many vehicles passed | **High** (capture can be neither guaranteed nor measured) | Use the COCO vehicle counts as a rough denominator now; a trigger sensor on the lane kit |
| **Night and IR** | Pulsed IR in step with the shutter, 850 nm, multi-exposure, WDR off [20][51][58] | No control over any of it, and nothing measured: the sandbox replays fixed clips, each camera's from one time of day, so our 25 Sep evening and 26 Sep morning runs (54/75 and 36/45 blind) replayed the same footage and are not night against day. The cameras whose clips were recorded at night mostly read nothing [108][109] | **High** | IR on the lane kit; ask departments for shutter and IR settings on plate-viable cameras |
| **Plate detector** | Large proprietary training sets; own or permissive models [68] | YOLOv11n at 640 px plus a classical text-line finder. **AGPL-3.0**, and its model card warns its metrics are inflated by train/test contamination [93][92] | **High** for a closed commercial product (licence); Medium technically | Retrain a permissive detector (RT-DETR or YOLOX, Apache-2.0 [94]) on our own labelled crops, or choose AGPL openly as the business model |
| **OCR** | Per-region engines with Indian plate types, updated quarterly [55] | CCT-XS global model with 10 character slots (no 11-character plates); single-digit Delhi RTO codes fail. Real-crop test sets: 28 AI-labelled crops [111] and 120 blind-read plates; 25 reading changes without training, including 9 other models, did not beat it [122] | **Medium** | The gated fine-tune, training now [112][123]; 11 slots; real labelled data from the review page |
| **Rules and fusion** | Syntax and type engines, per-character vote, multi-model fusion [55][75][79] | Indian rules plus BH series; confidence-weighted per-character vote; raw 60.7% → 89.3% after normalisation on real crops [111] | **Low** (same shape) | Keep; add an OCR ensemble later |
| **Non-plate rejection** | Plate-type and legibility classifiers [55][91] | Since 26 Sep the not-a-plate rule stops all 23 real non-plate crops at the worker gate (0 of 23 pass) and lost no real plate, but it rests on one hoarding and stops numbers, not lettered signs [122][113]; the fixed-text rule catches a repeated hoarding [113] | **Medium** | A plate / not-a-plate classifier trained on the review page's rejects |
| **Confidence and routing** | Confidence tiers; above 95% goes straight through, the rest to a manual team [24][20] | Stores the weakest character's confidence. On 120 blind-read real plates, ≥0.9 was 85.2% exact and 0.5–0.7 8 of 18 [118]; confidence is the strongest sign of Sentinel's misreads (AUC 0.84) [121]. A "check the crop" mark below 0.9 is a finale candidate behind a gate [123]; no routing queue yet | **High** | Calibrate on reviewed real crops; three bands (auto / review / reject) |
| **Human verification** | Operator checks every read against the image; edits logged; 100% manager audit; separate roles; written reasons [25][20] | 5 roles, an audit log, crops behind a token [114]; a plate review page (blind check and quick verify), built 26 Sep for measurement, not for enforcement [118] | **Medium** (the seed exists) | A verification workflow to the NHAI 2021 pattern |
| **Speed** | Certified radar or lidar, or OIML time-over-distance; ±3 km/h [37] | None. The journey view shows a straight-line average over a leg and says it is not a measured speed [113] | **Critical** for speed enforcement | Integrate a stamped radar; do not build metrology |
| **Time** | Certified or redundant time sources with continuous sync checks [37][39]; NTP from NIC/NPL [19] | Edge clock plus NTP (design); clock-offset monitoring designed, not built [113] | **High** for enforcement | Clock monitoring; GNSS and NTP cross-checked on the lane kit |
| **Evidence** | Signed case file, data bar, stills plus t±5 s video, raw data kept, BSA s.63 certificate [37][39][20][8] | The best-read JPEG crop and a database row per sighting. No video clip, no signature, no hash certificate | **Critical** for enforcement | Evidence package v1 (Horizon 2) |
| **Proof of accuracy** | NASPLE: 250 consecutive vehicles, capture and read, day and night [34]; IHMCL: per-scenario acceptance test [20] | Precision only: 120 plates, all but one on 2 cameras, checked blind by one team member (75.0% exact; 85.2% at confidence 0.9 or above); capture unmeasured [118] | **High** | A second blind reviewer; a NASPLE-format audit on our own test lane |
| **Certification** | Rule 167A annual certificate [3]; Legal Metrology for radar [12]; ARAI [31]; STQC and CERT-In [20][31]; certified cameras [17] | None | **Critical** to sell to government | The certification path in section 6 |
| **Integrations** | VAHAN, NIC eChallan/ITMS, NPCI FASTag mapper [25] | VAHAN and eGujCop are mock adapters [114] | **High** (access, not code) | Through a pilot buyer |
| **Compute and uptime** | Edge compute per lane or camera (e.g. DeepStream on Orin [66]); 99.5–99.9% uptime SLAs [20][31] | One GTX 1650 Ti laptop, about 4 streams at about 4.5 fps; store-and-forward tested once (21/21 replayed) [114] | **High**, but well understood | GPU edge nodes per the Plan for Scale; uptime monitoring |
| **Eligibility to bid** | OEM ≥3 years in business, product ≥1 year in MLFF operation, preferred OEM lists [20] | A new team | **Critical** for tolling; not an issue for city analytics | Sell through system integrators; toll later, if ever |

---

## 6. Roadmap: from hackathon proof of concept to a sellable product

### 6.1 The product line

| Product | What it is | Who buys | Promise it can keep |
|---|---|---|---|
| **A. Sentinel CCTV Analytics** (today's Model 2 platform) | ANPR, counts and events on cameras that already exist; watchlists, journeys, per-camera accuracy reports | Police districts, smart cities, VISWAS-type programmes, through their integrators | Investigation and alerts on plate-viable views; honest "this camera can / cannot read plates" |
| **B. Sentinel Lane** | A purpose-built ANPR kit: partner OEM camera + IR + trigger + edge box + our software | Checkposts, city entry points, campuses, then enforcement points | A read rate measured the NASPLE way on each lane |
| **C. Sentinel Review & Evidence** | Human verification queue, signed evidence packages, BSA s.63 certificate, eChallan integration, accuracy audits; also works on other vendors' cameras | The same buyers, plus integrators who need an audit trail | "Nothing goes out unchecked"; an audit a buyer can re-run |

### 6.2 Horizon 1: next 3 months (Oct–Dec 2026)

1. **Finale first** (12–13 Oct). The blind plate check on the review page was done on 26 Sep (90 of 120 exact [118]); a second, different blind reviewer would settle the 12 plates where it and the earlier AI check disagree, and the 13 misses the AI assistant's review puts on the reviewer [121]. The finale's pipeline changes are gated and decided by 9 Oct [123].
2. **Numbers updated everywhere** (done 26 Sep): the documents quote the blind check [118], and the AI check's 92/107 only as the earlier, optimistic figure [107].
3. **Measure the way buyers do.**
   - Turn the review page into a NASPLE-style audit: at least 250 consecutive vehicles per camera, day and night, reporting capture *and* read, per camera and per scenario [34][20].
   - The sandbox forbids recording, so do this on our own test site.
4. **Build one test lane.**
   - Buy one global-shutter ANPR camera with pulsed 850 nm IR and a lens chosen for characters of at least 20 px [54][60], plus a Jetson Orin-class edge box.
   - Install it at a friendly site (a campus gate) with signage and consent.
   - Choose the camera from OEMs that pass MeitY's CCTV security testing [17][18]. IHMCL's preferred list names Pelco/Avigilon, Axis, Vivotek, FETCI, Tattile and Bosch [20].
   - Prices are **unknown**: no public unit prices were found.
5. **Clean up the licences.** Replace the AGPL plate detector with a permissive one retrained on our crops, or choose AGPL deliberately [92][93][94]. Also review react-leaflet's Hippocratic licence [113].
6. **Route by confidence.**
   - Calibrate the stored confidence on reviewed real crops.
   - Set three bands: auto, review, reject.
   - Treat the synthetic-plate curve [110] as a hypothesis until real crops confirm it; the first real figures [118][121] point the same way.
   - The marking step is G3 of the finale gates [123].
7. **Fix the known OCR gaps:**
   - 11-character plates;
   - single-digit RTO codes;
   - a learned plate / not-a-plate classifier (the rule added on 26 Sep stops the known hoarding's numbers, not lettered signs [122]);
   - a two-row test set.
8. **Camera suitability report: built 26 Sep** as the plate-reading quality report [120]: size, blur, light and contrast per capture, a tier and advice per camera, plates per 1,000 frames. Its grade describes the camera, not a read. Next, as [120] proposes: weigh plate yield (capture) in the tier, and ask for 20 captures before calling a camera counts-only.

### 6.3 Horizon 2: 6–12 months (with months 3–6 as the bridge; to about Sep 2027)

1. **A pilot with one district or smart city,** through an integrator that holds the contract:
   - 10–30 plate-viable existing CCTV cameras;
   - 2–4 lanes of our own kit at checkposts or city entry points.
2. **Human verification to the NHAI 2021 pattern:**
   - the operator checks each read against the image;
   - edits are logged;
   - the manager audits 100% of corrections;
   - separate roles and written reasons, as in IHMCL's spec [25][20].
3. **Evidence package v1:**
   - stills plus a t−5 s to t+5 s clip;
   - a data bar with location, date and time;
   - a hash and an asymmetric signature, with the key held on the device;
   - raw data kept;
   - BSA s.63 certificate generation;
   - retention until the challan is disposed of [37][39][6][8].
4. **Integrations with the pilot buyer's access:** NIC eChallan/ITMS, VAHAN, eGujCop; NTP from NIC/NPL [19].
5. **Security certifications:** STQC Safe-to-Host, a CERT-In-empanelled audit and yearly VAPT (as GVMC requires) [31]; CERT-In logging [19].
6. **Accuracy reports** per camera class in NASPLE format, witnessed by the buyer.

### 6.4 Horizon 3: 12–24 months (to about Sep 2028)

1. **Enforcement certification:**
   - the Rule 167A annual certificate for our lane kit and software, with the state authority [3];
   - ARAI test reports, since tenders like GVMC ask for them [31].
   - How ARAI tests ANPR is **unknown**; find out early.
2. **Speed:**
   - Integrate a Legal Metrology-stamped radar from a partner OEM into the lane kit for spot speed [12].
   - Attempt section speed only once the time chain meets OIML §6.13 (0.3% time error, redundant sources, a continuous check) [37], and once it is clear whether Legal Metrology covers non-radar speed (**unknown**).
3. **Highway enforcement:** supply software and the back office to an integrator for NHAI ATMS/VIDES work, where the ANPR SLA is ≥95% [26].
4. **Tolling:** only through a partner. The OEM gates mean a team starting now cannot bid as OEM before about 2029 (derived from the 3-year rule [20]). The review back office is the realistic entry point.
5. **Scale-out** per the Plan for Scale.

### 6.5 Data strategy

1. **Label with the review page.** Every stored sighting is shown with its crop. The reviewer types the plate blind, or confirms it, and marks "not a plate" or "unreadable". That one action is both the precision audit and the training label.
2. **Keep the splits honest.**
   - Split by vehicle and by camera, and freeze test sets per camera class; never train on them. Near-duplicates [78] and cross-site drops [77] are the two traps.
   - The frozen sets and pre-registered gates already exist [112]: keep that discipline for every retrain.
3. **Pre-train on synthetic Indian plates,** including HSRP, BH series [16], two-line and non-standard fonts. The literature supports it [88][89], and Hailo trained on 4 M synthetic plates [69]. Fine-tune on real crops.
4. **Retrain on a steady cadence,** e.g. quarterly, as Carmen does for its IND engine [55]. Adopt a candidate only through the gates.
5. **Handle the data lawfully.** Labels are real registrations, which is personal data under the DPDP Act. Keep them local, with retention limits, as the sandbox labels already are [107]. Record the camera owner's permission to keep crops for measurement; STATUS lists asking the organisers this as open [114].

### 6.6 Hardware choices

- **Lane kit:**
  - camera: global shutter, 2–5 MP, 50/60 fps, 850 nm pulsed IR with multi-exposure if available, WDR off [51][58][59];
  - trigger: a laser or radar trigger, or the camera's own plate trigger;
  - edge: a Jetson Orin-class box running DeepStream-style INT8/FP16 models [66];
  - an Axis-style on-camera app is the alternative at small sites [52].
- **City nodes:** GPU nodes with NVDEC for many CCTV streams (Plan for Scale). Laptop numbers do not transfer [113].
- **Avoid hardware that tenders exclude:** the HiSilicon ban [20] and the MeitY security requirements [17].

### 6.7 Certifications, in order

1. CERT-In practices (NTP, logs) and a VAPT: needed for any government pilot [19][31].
2. STQC Safe-to-Host for the web application [31].
3. Cameras that already hold BIS/MeitY security certificates, bought rather than certified ourselves [17][18].
4. ARAI test reports for ANPR, and for speed if it is offered [31].
5. The Rule 167A state certificate for each enforcement deployment, renewed yearly [3].
6. Legal Metrology stamping, through the radar partner [12].

### 6.8 Partnerships

- **Integrators** that hold state and city CCTV/ITMS contracts: the route to market for Products A and C.
- **Camera OEMs** on IHMCL's preferred list [20], for the lane kit and later for toll work.
- **A radar OEM** with Legal Metrology approval, for speed.
- **An academic partner** for independent measurement: it answers the DHS point that vendor figures go unverified [45].

### 6.9 Realistic accuracy targets per camera class

These are proposals, not measurements.

| Camera class | Promise | Target | Basis | Today |
|---|---|---|---|---|
| Wide overview, red-light and night CCTV | No plate reads promised; counts and events only | — | Most sandbox cameras gave no valid plate at all [109] | Matches |
| Plate-viable existing CCTV (tier A) | Investigative reads with human review | Read (precision) ≥95% in the auto band; capture ≥85% of human-readable plates (NASPLE's CCTV class) | [34] | 75.0% precision, blind, all but one plate on CAM06/07 (85.2% in the 0.9-or-above band); capture unmeasured [118] |
| Purpose-built lane, HSRP plates | Enforcement-ready reads | ≥95% day and night in year 1 (full NHAI SLA points; GVMC after month 6); ≥98% as the stretch (IHMCL ETC) | [26][31][24] | Not built |
| Purpose-built lane, non-HSRP plates | — | ≥90% (IHMCL ETC); 75% for non-standard fonts (SASGUJ) | [24][28] | — |
| Free-flow toll, 99% front or rear without manual validation | **Do not promise** | — | Bidders said no system achieves 99% at free-flow speed in India [21] | — |
| Challans after human verification | No known wrong challans; track appeals | Error rate measured on appeals | Bengaluru claims 99.9% after validation (police claim) [104] | No challans |

---

## 7. Where Sentinel can genuinely differentiate, and what not to attempt

### Where we can win

1. **Making existing city CCTV useful.**
   - Gujarat has already bought thousands of cameras: 7,000+ in VISWAS Phase I and 10,500+ in Phase II [99]. SASGUJ planned 2,833 ANPR cameras [30].
   - Buyers audit these at random against 60–90% targets [28][32].
   - A platform that tells a department, per camera, "reads plates at X% precision and Y% capture" or "use for counts only", and sets up the analytics to match, fills a real gap.
2. **Honest, per-camera measurement as a product feature.**
   - Vendor figures are "not independently verified" [45].
   - Commercial engines scored 6–9 points below their claims on independent data [76].
   - India has no codified national ANPR accuracy standard [33].
   - A NASPLE-format audit tool that runs against any vendor's output is sellable and hard to fake.
3. **Human-in-the-loop review done properly.**
   - NHAI requires it [25]; Kerala, Mumbai–Pune and Bengaluru do it by hand [101][102][104].
   - A good review queue with confidence routing, logged edits, manager audit and signed evidence also produces our training data.
4. **Privacy by design.** No facial recognition, vehicle and plate only. Washington State writes this into law [50], and it fits the DPDP Act's purpose limitation.
5. **Open standards and no lock-in.**
   - RTSP and ONVIF in; open APIs out. IHMCL asks for open, vendor-neutral APIs [20].
   - Our integration layer works across camera makes.
6. **Indian plate specifics.** Two-line plates, the BH series, non-HSRP plates and 11-character series are where global engines are weakest (e.g. two-row plates at 45.7% [77]). Our rules already add about 29 points on real crops [111]. How commercial engines do on Indian plates is **unknown**: no independent benchmark was found.

### What not to attempt

- **Building our own speed-measurement physics** (radar, lidar, certified time). Integrate certified sensors [37][12].
- **Bidding for free-flow or toll plazas directly.** The OEM gates, the 99%-without-validation requirement and the ₹1 lakh per wrong manual transaction penalty are wrong for a new team [20].
- **Promising 99% or even 95% on surveillance CCTV.** Even the UK accepts 85% capture for CCTV used in ANPR mode [34].
- **Issuing tickets from CCTV journey speeds.** A straight-line average between cameras is not a measured speed [113].
- **Auto-issuing anything without a person checking it,** or without the Rule 167A certificate [3][11].
- **Facial recognition.**
- **Building our own camera hardware.** Partner instead.

---

## 8. What is still unknown

- **Toll confidence threshold:** IHMCL/NHAI publish none for automatic vs manual processing. The ">95% confidence" figure appears only in IHMCL's ETC tender [24] and an e-con Systems blog [74], not in the free-flow RFP [21].
- **Indian free-flow plazas:** measured ANPR accuracy and manual-review share are not published, and the Choryasi OEM and OCR engine are unconfirmed.
- **ARAI:** the test procedure for ANPR and speed certification.
- **Rule 167A certificates:** who issues the annual certificate in Gujarat, and how the device is tested.
- **Legal Metrology:** whether the 2025 rules cover ANPR/video-based or section speed; the notification text was not opened.
- **Rule 167 rewrite:** the final gazette text of the 2026 amendment was not read (secondary summaries only).
- **Gujarat challans:** whether a person checks each camera challan before issue.
- **Commercial engines:** their architectures, and their accuracy on Indian plates (HSRP, two-line, BH).
- **Prices:** unit prices for ANPR cameras, radars or enforcement gantries.
- **Indian data:** any commercially licensed Indian plate dataset.
- **HSRP under IR:** retroreflectivity in the infrared band.

## 9. Notes for the repo, found while reading (read-only; nothing changed)

- **Stale accuracy figure** (resolved 26 Sep: the documents now quote the blind check, `bench/results/sandbox_review.md`). `bench/results/sandbox_eye.md` (26 Sep 07:31) now pools the 25 Sep evening and 26 Sep morning runs: 92/107 = 86.0% exact on vehicle plates (55/66 and 37/41 in `sandbox_daynight.md`). `docs/hld.md` v1.5 (§7.5, §13, §13a.2) and `STATUS.md` still say 55/66. Under the CLAUDE.md "change the story everywhere" rule, the deck, video captions, form answers and README-for-reviewers need checking too.
- **Not day and night** (corrected 26 Sep evening). The sandbox replays fixed clips recorded in June 2026, each camera's from one time of day, looping; our two runs replayed the same footage. Every "day/night" comparison in the pack was removed; `sandbox_daynight.md` keeps its file name only.
- **Plate widths are stream pixels.** In `bench/sandbox_plates.py` the widths come from Ultralytics `xyxy` boxes, which are in the original frame's coordinates, so the table's "Median width 640 (px)" is stream pixels at the 640 px inference size. The header could say so.
- **The accuracy claim will be challenged.** Every Indian buyer and standard read here measures on live or recorded traffic by a person. The blind check by a team member is the one figure a judge or a buyer will accept.

## Verification note

- **Re-opened by me against the primary text:**
  - IHMCL GJ-02 RFP [20]: the SAT accuracy clause, the camera spec, the HiSilicon ban, t±5 s.
  - An IHMCL ETC RFP extract with the >98% / >90% / >95%-confidence clauses [24].
  - NASPLE v3.5 [34]: the 98/95, 85% CCTV and 250-vehicle clauses.
  - NHAI ATMS 2021 [25]: operator audit, 100% manager audit, 90% at night at 180 km/h, monthly calibration, 60-day / 5-year retention, ANPR-based VSDS.
  - The NHAI 2023 SLA deck [26]; SASGUJ [28]; OIML R 91-1:2025 [37]; CMVR 167A [3][6]; the Legal Metrology report [12].
  - Axis [51] and Bosch [53]; Laroca 2018 and 2022 [75][77]; the Ultralytics licence [92]; the morsetechlab model card [93].
- **Taken from the researchers' reading, which says they opened each source:** all other sources.
- **Failed for me:** the NIC eChallan page [98] (a certificate error).

## Sources

1. MV Act s.136A (2019 amendment) — https://www.aaptaxlaw.com/motor-vehicles-act-2019/section-136a-137-138-145-146-of-motor-vehicles-amendment-act-2019.html
2. LiveLaw, Supreme Court directs States to implement s.136A (2 Sep 2024) — https://www.livelaw.in/top-stories/supreme-court-directs-state-governments-to-implement-s-136a-motor-vehicles-act-for-electronic-monitoring-of-road-safety-268384
3. CMVR Rule 167A, devices and annual certificate — https://ebook.commerciallawpublishers.com/fa/cmvr/files/basic-html/page452.html
4. CMVR Rule 167A, city list — https://ebook.commerciallawpublishers.com/fa/cmvr/files/basic-html/page453.html
5. CMVR Rule 167A, footage stamp, offences, warning signs — https://ebook.commerciallawpublishers.com/fa/cmvr/files/basic-html/page457.html
6. CMVR Rule 167A, challan contents, 15 days, retention — https://ebook.commerciallawpublishers.com/fa/cmvr/files/basic-html/page458.html
7. MoRTH notification summary (s.65B certificate) — https://www.indianbureaucracy.com/morth-notification-for-electronic-monitoring-enforcement-of-road-safety/
8. BSA 2023 s.63 (secondary) — https://www.rkdewan.com/articles/electronic-records-now-governed-by-section-63-of-the-bhartiya-sakshya-adhiniyam-2023/
9. MoRTH draft G.S.R. 723(E), 29 Sep 2025 — https://morth.gov.in/backend/old_files/circulars_document/draft%20notification%20G.S.R.%20723(E)%20DT.%2029.09.2025.pdf
10. CMVR (Third Amendment) Rules 2026 summary — https://www.teamleaseregtech.com/updates/article/52088/central-motor-vehicles-third-amendment-rules-2026/
11. Srinagar court quashes phone-issued e-challans (5 May 2026) — https://www.asvlawoffices.com/news-insights/rule-167-a-compliance-mandatory-srinagar-court-quashes-e-challans-issued-through-personal-phones/
12. Tribune, Legal Metrology rules for radar speed equipment — https://www.tribuneindia.com/news/consumer-affairs/centre-notifies-rules-to-strengthen-road-safety-and-fairness-in-traffic-enforcements
13. CMVR Rule 50 — https://indiankanoon.org/doc/94226366/
14. CMVR Rule 51 — https://www.aptransport.org/html/registration-registrationdisplay.html
15. AIS-159 (HSRP), Aug 2019 — https://www.shimnit.com/wp-content/uploads/2024/08/August-2019-AIS-159.pdf
16. BH series details — https://transport.maharashtra.gov.in/site/upload/pdf/bhseriesdetails.pdf
17. BIS CCTV implementation guidelines (MeitY ER) — https://www.crsbis.in/BIS/app_srv/tdc/gl/docs/CCTV_Implementation_guidelines.pdf
18. STQC testing under PPP-MII for CCTV (2026) — https://www.staffnews.in/2026/03/testing-requirements-under-public-procurement-order-for-cctv-cameras.html
19. CERT-In Directions, 28 Apr 2022 — https://www.cert-in.org.in/PDF/CERT-In_Directions_70B_28.04.2022.pdf
20. IHMCL RFP, FASTag-ANPR MLFF, Gujarat Bundle GJ-02, 20 Mar 2026 — https://ihmcl.co.in/wp-content/uploads/2026/03/FinalRFPMLFFGJ02-20032026.pdf
21. IHMCL Gharaunda MLFF pre-bid responses, 20 Jun 2025 — https://ihmcl.co.in/wp-content/uploads/2025/06/Gharaunda-Responsetoprebid-20062025.pdf
22. IHMCL MLFF RFP Delhi-NCR DL-01, Mar 2026 — https://ihmcl.co.in/wp-content/uploads/2026/03/FinalRFPDL01-10032026.pdf
23. IHMCL Dwarka Expressway MLFF pre-bid responses, 25 Jul 2025 — https://ihmcl.co.in/wp-content/uploads/2025/07/Response-to-prebid_25072025-1.pdf
24. IHMCL ETC toll-plaza RFP, Jan 2025 — https://ihmcl.co.in/wp-content/uploads/2025/01/FinalRFP10plazas21012025.pdf
25. NHAI ATMS Functional and Technical Specification, Feb 2021 — https://www.cosai.in/resources/1.%20ATMS-%20Function%20and%20Technical%20specification_NHAI-CO-ATMS-02-2021_Feb%202021.pdf
26. IHMCL ATMS training deck (NHAI ATMS policy, 10 Oct 2023) — https://ihmcl.co.in/wp-content/uploads/2024/04/ATMS_Training_PDF.pdf
27. NHIT/NWPPL ATMS corrigendum and pre-bid, 2025 — https://nhit.co.in/procurment/2025-2026/Corrigendum%20-%20I%20&%20Prebid%20Queries%20NWPPL%20ATMS%202024%2001.pdf
28. Gujarat Home Dept SASGUJ RFP (GIL, 2017) — https://gil.gujarat.gov.in/tendercms/TenderDocs/2017621174659599.pdf
29. SASGUJ pre-bid replies (GIL) — https://gil.gujarat.gov.in/tendercms/TenderDocs/2017621174644238.pdf
30. SASGUJ camera distribution (GIL) — https://gil.gujarat.gov.in/tendercms/TenderDocs/201771015579162.pdf
31. GVMC Visakhapatnam ITMS RFP, Dec 2025 (TCIL) — https://www.tcil.net.in/tender/pdf/25f2850_1.pdf
32. Guwahati Smart City RFP, vol. 2 — https://gscl.assam.gov.in/sites/default/files/swf_utility_folder/departments/smartcity_webcomindia_org_oid_7/latest/volume2.pdf
33. HOAI / Vertis, MLFF tolling in India, Apr 2026 — https://hoai.in/wp-content/uploads/2026/04/Multi-Lane-Free-Flow-MLFF-Tolling-in-India.pdf
34. UK National ANPR Standards for Policing and Law Enforcement (NASPLE) v3.5, Jul 2026 — https://assets.publishing.service.gov.uk/media/69c25599d588c92c483e4c1f/NASPLE.v3.4.pdf
35. UK National ANPR Service technical specifications — https://gov.uk/government/publications/national-anpr-standards/national-anpr-service-technical-specifications-accessible-version
36. UK Home Office ANPR evaluation guidance v2.0 — https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/909024/ANPR_-_Evaluation_Approved_Version_2.0.pdf
37. OIML R 91-1:2025, Traffic speed meters — https://www.oiml.org/en/files/pdf_r/r091-1-e25.pdf
38. UK Home Office speedmeter, traffic light and lane enforcement camera handbook v2.0 — https://www.gov.uk/government/publications/speedmeter-traffic-light-and-lane-enforcement-camera-handbook/speedmeter-traffic-light-and-prohibited-lane-enforcement-camera-handbook-accessible
39. PTB-A 12.01 (Oct 2015) — https://oar.ptb.de/files/download/681c517953218de84f08e697
40. MessEV Annex 7 (recalibration periods) — https://www.gesetze-im-internet.de/messev/anlage_7.html
41. Saarland Constitutional Court, Lv 7/17 (5 Jul 2019) — https://www.burhoff.de/asp_weitere_beschluesse/inhalte/5126.htm
42. Federal Constitutional Court, 2 BvR 1616/18 (12 Nov 2020) — https://www.bundesverfassungsgericht.de/SharedDocs/Pressemitteilungen/DE/2020/bvg20-105.html
43. PRSP, Gatso fixed safety cameras — https://www.prsp.org.uk/gatso-fixed-safety-cameras/
44. EU Road Safety DSS, section control synopsis (Høye 2014) — https://www.roadsafety-dss.eu/assets/data/pdf/synopses/Installation_of_section_control_speed_cameras_23102017.pdf
45. DHS S&T ALPR Market Survey Report, Jun 2025 — https://www.dhs.gov/sites/default/files/2025-06/25_0606_st_lprmsr.pdf
46. Illinois Tollway, Tolling Back-Office Overview, Mar 2023 — https://agency.illinoistollway.com/documents/20184/1308568/20230330_TechOps%20Back_Office.pdf/5c0b57dd-c69d-e644-f18b-830592d19542?version=1.0&t=1680191014410
47. Maryland Transportation Authority audit, Sep 2021 — https://dls.maryland.gov/pubs/prod/NoPblTabPDF/MDTA21.pdf
48. Geotoll patent US11544942 — https://patents.google.com/patent/US11544942
49. NYC Comptroller, speed camera audit, Jan 2024 — https://comptroller.nyc.gov/wp-content/uploads/2024/01/Audit_Glance_DOT-Speed-Cameras.pdf
50. Washington RCW 46.63.200 — https://app.leg.wa.gov/RCW/default.aspx?cite=46.63.200
51. Axis white paper, License plate capture — https://whitepapers.axis.com/en-us/license-plate-capture
52. AXIS License Plate Verifier datasheet — https://www.axis.com/dam/public/e9/56/67/datasheet-axis-license-plate-verifier-en-US-509394.pdf
53. Bosch white paper, Automatic license plate recognition — https://media.boschsecurity.com/fs/media/pb/media/industry_2/white_paper_automatic_license_plate_recognition_.pdf
54. Adaptive Recognition, Carmen brief guide for input images — https://adaptiverecognition.com/app/uploads/DOC/Software/Carmen/brief_guide_for_input_images.pdf
55. Carmen ANPR Reference Manual — https://adaptiverecognition.com/app/uploads/DOC/Software/Carmen/ANPR/carmen_anpr_reference_manual.pdf
56. Genetec AutoVu SharpV specifications — https://techdocs.genetec.com/r/en-US/AutoVuTM-SharpV-Administrator-Guide-14.4/Specifications-for-the-SharpV
57. Neology IRIS datasheet — https://symbiotesolutions.com/wp-content/uploads/Iris-Data-Sheet.pdf
58. Adaptive Recognition Vidar datasheet — https://adaptiverecognition.com/app/uploads/DOC/Cameras/Vidar_ANPR_Cameras_for_Any_Type_of_Traffic_Monitoring/Vidar_ANPR_Consolidation/camera-vidar-datasheet.pdf
59. Hikvision AI-TCV900 datasheet — https://www.hikvision.com/content/dam/hikvision/en/support/regional-materials/turkey/AI-TCV900_Datasheet_20240123.pdf
60. Gardasoft, wavelengths for ANPR illumination — https://www.gardasoft.com/Glossary-of-Terms/LED-Illumination-for-ITS-traffic/Wavelengths-for-ANPR-illumination-applications.aspx
61. Plate Recognizer, camera setup for best ANPR — https://platerecognizer.com/camera-setup-for-best-anpr/
62. Plate Recognizer, real-world results — https://platerecognizer.com/alpr-results/
63. Sensys Gatso T-Series technology summary — https://cms8.revize.com/revize/cedarrapids/T-Series%20Technology%20Summary.pdf
64. Jenoptik VECTOR SR (vendor document) — https://www.myvendorlink.com/external/vfile?d=vrf&s=193823&v=102855&sv=0&i=330&ft=b
65. Vitronic automated speed enforcement — https://www.vitronic.com/en-us/automated-speed-enforcement
66. NVIDIA DeepStream LPR app — https://github.com/NVIDIA-AI-IOT/deepstream_lpr_app
67. NVIDIA TAO LPRNet model card — https://catalog.ngc.nvidia.com/orgs/nvidia/tao/models/lprnet/-?_lr=1
68. NVIDIA TAO LPDNet model card — https://catalog.ngc.nvidia.com/orgs/nvidia/tao/models/lpdnet/-
69. Hailo, ALPR with Hailo processors — https://hailo.ai/blog/automatic-license-plate-recognition-with-hailo-processors/
70. Stellarview, highways and expressways (vendor claim) — https://stellarview.ai/solutions/highways-expressways/
71. Vaaan, speed violation detection system (vendor claim) — https://vaaaninfra.com/hardware/speed-violation-detection-system
72. Vehant VIDES (vendor claim) — https://www.vehant.com/solutions/vides/video-incident-detection-enforcement-system/
73. Kapsch, multi-lane free flow — https://www.kapsch.net/en/tolling/multi-lane-free-flow
74. e-con Systems blog, camera design for ORT/MLFF — https://www.e-consystems.com/blog/camera/applications/why-camera-design-matters-in-open-road-tolling-ort-and-multi-lane-free-flow-mlff/
75. Laroca et al. 2018, robust real-time ALPR (temporal redundancy) — https://arxiv.org/pdf/1802.09567
76. Laroca et al., layout-independent ALPR (IET ITS 2021) — https://arxiv.org/abs/1909.01754
77. Laroca et al. 2022, cross-dataset LPR study — https://arxiv.org/pdf/2201.00267
78. Near-duplicates in LPR datasets — https://arxiv.org/pdf/2304.04653
79. Fusing OCR models for LPR — https://arxiv.org/html/2309.04331
80. UFPR-SR-Plates (super-resolution) — https://arxiv.org/abs/2505.06393
81. ICPR 2026 low-resolution LPR competition — https://arxiv.org/pdf/2604.22506
82. LPRNet — https://arxiv.org/abs/1806.10447
83. PARSeq — https://arxiv.org/abs/2207.06966
84. Indian commercial truck plates (YOLOv7 + PARSeq) — https://arxiv.org/abs/2211.13194
85. Indian licence plate dataset in the wild (ILPD) — https://arxiv.org/abs/2111.06054
86. ILPD repository — https://github.com/sanchit2843/Indian_LPR
87. IWPOD-NET — https://github.com/claudiojung/iwpod-net
88. Synthetic data for multinational LPR — https://arxiv.org/abs/2601.07671
89. Diffusion-generated synthetic plates — https://arxiv.org/abs/2501.03374
90. Probabilistic deep learning for LPR (MC-dropout) — https://arxiv.org/html/2302.01427
91. LPLC legibility dataset — https://arxiv.org/abs/2508.18425
92. Ultralytics licence — https://www.ultralytics.com/license
93. morsetechlab YOLOv11 plate detector model card — https://huggingface.co/morsetechlab/yolov11-license-plate-detection
94. RT-DETR (Apache-2.0) — https://github.com/lyuwenyu/RT-DETR
95. fast-plate-ocr model zoo — https://ankandrew.github.io/fast-plate-ocr/latest/inference/model_zoo/
96. UFPR-ALPR dataset licence — https://github.com/raysonlaroca/ufpr-alpr-dataset
97. CCPD — https://github.com/detectRecog/CCPD
98. NIC, Gujarat eChallan (Apr 2025) — https://informatics.nic.in/files/websites/april-2025/echallan.php
99. DeshGujarat, VISWAS 10,500 cameras (Dec 2023) — https://deshgujarat.com/2023/12/15/10500-cctv-cameras-being-installed-across-gujarat-under-viswas-project/
100. DeshGujarat, Delhi–Mumbai Expressway Vadodara–Navsari speeding (May 2026) — https://deshgujarat.com/2026/05/18/delhi-mumbai-expressway-overspeeding-on-vadodara-navsari-stretch-to-invite-penalty/
101. Onmanorama, Safe Kerala AI cameras (May 2023) — https://www.onmanorama.com/news/kerala/2023/05/02/safe-kerala-project-no-fine-only-challan-traffic-violations-ai-camera-may-19.html
102. Angel One, Mumbai–Pune Expressway e-challans — https://www.angelone.in/news/economy/ai-cameras-on-mumbai-pune-expressway-issued-470-crore-in-e-challans
103. PTI via TaxTMI, Mumbai–Pune ITMS (Jun 2025) — https://www.taxtmi.com/tmi_blog_details?id=829207
104. OneIndia, Bengaluru AI camera errors and manual review (Aug 2024) — https://www.oneindia.com/bengaluru/ai-traffic-camera-errors-in-bengaluru-fixed-through-manual-review-by-cops-how-to-dispute-fines-3903061.html
105. DeshGujarat, Choryasi barrier-less toll live (1 May 2026) — https://deshgujarat.com/2026/05/01/indias-first-barrierless-toll-system-goes-live-at-surats-choryasi-plaza/
106. Autocar Pro, 6 MLFF plazas process 1.1 crore vehicles — https://www.autocarpro.in/news/barrier-free-tolling-gathers-pace-6-plazas-process-11-cr-vehicles-in-first-3-months-134152
107. Sentinel repo: D:\GitHub\GP\bench\results\sandbox_eye.md (26 Sep 2026 07:31)
108. Sentinel repo: D:\GitHub\GP\bench\results\sandbox_daynight.md (regenerated 26 Sep 2026 evening: the 25 Sep evening and 26 Sep morning runs, the same looping footage; `sandbox_loop.md` shows the repeats)
109. Sentinel repo: D:\GitHub\GP\bench\results\sandbox_plates.md, sandbox_plates_day.md, and D:\GitHub\GP\bench\sandbox_plates.py
110. Sentinel repo: D:\GitHub\GP\bench\results\anpr_eval_current.md (24 Sep 2026)
111. Sentinel repo: D:\GitHub\GP\bench\results\ocr_baseline.md (25 Sep 2026)
112. Sentinel repo: D:\GitHub\GP\bench\ocr_gates.md
113. Sentinel repo: D:\GitHub\GP\docs\hld.md (v1.5, §7.1, §7.2, §7.5, §13, §13a, §14)
114. Sentinel repo: D:\GitHub\GP\STATUS.md (24 Sep 2026)
115. Vitronic, AI-based toll enforcement in Poland (vendor claim) — https://www.vitronic.com/en-us/case-study/ai-based-toll-enforcement-in-poland
116. Tattile, free-flow (vendor claim) — https://www.tattile.com/applications/free-flow/
117. New York automated work-zone speed enforcement — https://www.ny.gov/work-zone-safety-awareness/automated-work-zone-speed-enforcement-program
118. Sentinel repo: D:\GitHub\GP\bench\results\sandbox_review.md (26 Sep 2026 13:19; blind check by a team member)
119. Sentinel repo: D:\GitHub\GP\bench\results\review_truth.md (26 Sep 2026 12:27)
120. Sentinel repo: D:\GitHub\GP\bench\results\capture_quality.md and quality_thresholds.md (26 Sep 2026; plate-reading quality by camera and its check against the blind reviews)
121. Sentinel repo: D:\GitHub\GP\bench\results\blind_errors.md (26 Sep 2026; why the 30 blind misses missed, by the AI assistant's adjudication)
122. Sentinel repo: D:\GitHub\GP\bench\results\ocr_fix_trials.md (26 Sep 2026; 25 reading changes without training)
123. Sentinel repo: D:\GitHub\GP\bench\pipeline_gates.md (26 Sep 2026; no change before the submission, finale gates G0–G6)
