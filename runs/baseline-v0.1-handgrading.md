# regulated-rag v0.1 — hand-grading template (run 1)

Side-by-side view of each in-corpus query's claims and the cited chunk text. Mark grades in `runs/baseline-v0.1-handgrading.json`. This file is the reading view; the JSON is the gradesheet.

**For each claim:** does the claim follow from the cited chunk's text (faithfulness)? does it address the question (answer relevance)?

**For each 'extra' citation** (cited but not in expected): hierarchical, contextual, or off-topic?

---

## fdcpa-001
**Query:** Can a debt collector call me before 8am or after 9pm?

**Expected:** `§ 805(a)(1)`  **Cited:** `§ 805(a)(1), § 805(a)(1), § 805(a), § 805(a)(1)`  **Recall:** 1.00  **Precision:** 0.50

**Retrieved top-5:**

| rank | chunk_id | section_ref | rerank |
|---:|---:|:---|---:|
| 1 | 282 | `§ 805(a)(1)` | 0.829 |
| 2 | 277 | `§ 804(3)` | 0.235 |
| 3 | 280 | `§ 804(6)` | 0.202 |
| 4 | 281 | `§ 805(a)` | 0.178 |
| 5 | 285 | `§ 805(b)` | 0.173 |

### Claims
#### Claim 1
_Cites:_ `§ 805(a)(1)` (chunk_id 282)

**Claim text:**
> A debt collector may not communicate with a consumer at any unusual time or place, or a time known (or which should be known) to be inconvenient to the consumer.

**Cited chunk text:**
_§ 805(a)(1)_ (chunk_id 282):
> at any unusual time or place or a time or place known or which should be known to be inconvenient to the consumer . In the absence of knowledge of circumstances to the contrary, a debt collector shall assume that the convenient time for communicating with a consumer is after 8 o’clock antemeridian and before 9 o’clock postmeridian, local time at the consumer ’s location;

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 2
_Cites:_ `§ 805(a)(1)` (chunk_id 282)

**Claim text:**
> In the absence of knowledge of circumstances to the contrary, a debt collector must assume that the convenient time for communicating with a consumer is after 8 o'clock AM and before 9 o'clock PM, local time at the consumer's location — meaning calls before 8 AM or after 9 PM are generally not allowed.

**Cited chunk text:**
_§ 805(a)(1)_ (chunk_id 282):
> at any unusual time or place or a time or place known or which should be known to be inconvenient to the consumer . In the absence of knowledge of circumstances to the contrary, a debt collector shall assume that the convenient time for communicating with a consumer is after 8 o’clock antemeridian and before 9 o’clock postmeridian, local time at the consumer ’s location;

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 3
_Cites:_ `§ 805(a)` (chunk_id 281), `§ 805(a)(1)` (chunk_id 282)

**Claim text:**
> Without the prior consent of the consumer given directly to the debt collector, or the express permission of a court of competent jurisdiction, a debt collector may not communicate with a consumer in connection with the collection of any debt outside of these permitted hours.

**Cited chunk text:**
_§ 805(a)_ (chunk_id 281):
> Communication with the consumer generally. Without the prior consent of the consumer given directly to the debt collector or the express permission of a court of competent jurisdiction, a debt collector may not communicate with a consumer in connection with the collection of any debt—

_§ 805(a)(1)_ (chunk_id 282):
> at any unusual time or place or a time or place known or which should be known to be inconvenient to the consumer . In the absence of knowledge of circumstances to the contrary, a debt collector shall assume that the convenient time for communicating with a consumer is after 8 o’clock antemeridian and before 9 o’clock postmeridian, local time at the consumer ’s location;

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

### Extra citations (cited but not in expected)
Classify each below in the JSON's `extra_citations` array.

- **`§ 805(a)`** (chunk_id(s): [281]):
> Communication with the consumer generally. Without the prior consent of the consumer given directly to the debt collector or the express permission of a court of competent jurisdiction, a debt collector may not communicate with a consumer in connection with the collection of any debt—
  → _classify in JSON: `hierarchical` | `contextual` | `off_topic`_

---

## fdcpa-002
**Query:** What conduct does the FDCPA prohibit as harassment by debt collectors?

**Expected:** `§ 806, § 806(1), § 806(2), § 806(3), § 806(5), § 806(6)`  **Cited:** `§ 806, § 806, § 802(a)`  **Recall:** 0.17  **Precision:** 0.50

**Retrieved top-5:**

| rank | chunk_id | section_ref | rerank |
|---:|---:|:---|---:|
| 1 | 292 | `§ 806` | 0.832 |
| 2 | 299 | `§ 807` | 0.688 |
| 3 | 316 | `§ 808` | 0.677 |
| 4 | 260 | `§ 802(a)` | 0.475 |
| 5 | 324 | `§ 808(8)` | 0.420 |

### Claims
#### Claim 1
_Cites:_ `§ 806` (chunk_id 292)

**Claim text:**
> Under the FDCPA, a debt collector may not engage in any conduct the natural consequence of which is to harass, oppress, or abuse any person in connection with the collection of a debt.

**Cited chunk text:**
_§ 806_ (chunk_id 292):
> A debt collector may not engage in any conduct the natural consequence of which is to harass, oppress, or abuse any person in connection with the collection of a debt . Without limiting the general application of the foregoing, the following conduct is a violation of this section:

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 2
_Cites:_ `§ 806` (chunk_id 292)

**Claim text:**
> The prohibition on harassment is broadly applied and is not limited only to the specific examples listed in § 806 — the listed conduct is provided without limiting the general application of the harassment prohibition.

**Cited chunk text:**
_§ 806_ (chunk_id 292):
> A debt collector may not engage in any conduct the natural consequence of which is to harass, oppress, or abuse any person in connection with the collection of a debt . Without limiting the general application of the foregoing, the following conduct is a violation of this section:

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 3
_Cites:_ `§ 802(a)` (chunk_id 260)

**Claim text:**
> The FDCPA's harassment provisions exist in part because abusive debt collection practices contribute to personal bankruptcies, marital instability, loss of jobs, and invasions of individual privacy.

**Cited chunk text:**
_§ 802(a)_ (chunk_id 260):
> Abusive practices. There is abundant evidence of the use of abusive, deceptive, and unfair debt collection practices by many debt collectors. Abusive debt collection practices contribute to the number of personal bankruptcies, to marital instability, to the loss of jobs, and to invasions of individual privacy.

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

### Extra citations (cited but not in expected)
Classify each below in the JSON's `extra_citations` array.

- **`§ 802(a)`** (chunk_id(s): [260]):
> Abusive practices. There is abundant evidence of the use of abusive, deceptive, and unfair debt collection practices by many debt collectors. Abusive debt collection practices contribute to the number of personal bankruptcies, to marital instability, to the loss of jobs, and to invasions of individual privacy.
  → _classify in JSON: `hierarchical` | `contextual` | `off_topic`_

---

## fdcpa-003
**Query:** What information must a debt collector send me to validate a debt?

**Expected:** `§ 809(a)`  **Cited:** `§ 809(a), § 809(a)(3), § 809(a)(4), § 809(a)(5), § 809(b)`  **Recall:** 1.00  **Precision:** 0.20

**Retrieved top-5:**

| rank | chunk_id | section_ref | rerank |
|---:|---:|:---|---:|
| 1 | 325 | `§ 809(a)` | 0.647 |
| 2 | 329 | `§ 809(a)(4)` | 0.621 |
| 3 | 328 | `§ 809(a)(3)` | 0.565 |
| 4 | 331 | `§ 809(b)` | 0.515 |
| 5 | 330 | `§ 809(a)(5)` | 0.511 |

### Claims
#### Claim 1
_Cites:_ `§ 809(a)` (chunk_id 325)

**Claim text:**
> Within five days after the initial communication with a consumer, a debt collector must send a written notice containing specific information about the debt, unless that information was already included in the initial communication or the consumer has paid the debt.

**Cited chunk text:**
_§ 809(a)_ (chunk_id 325):
> Notice of debt; contents. Within five days after the initial communication with a consumer in connection with the collection of any debt, a debt collector shall, unless the following information is contained in the initial communication or the consumer has paid the debt, send the consumer a written notice containing—

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 2
_Cites:_ `§ 809(a)(3)` (chunk_id 328)

**Claim text:**
> The notice must include a statement that unless the consumer disputes the validity of the debt (or any portion thereof) within thirty days after receipt of the notice, the debt will be assumed to be valid by the debt collector.

**Cited chunk text:**
_§ 809(a)(3)_ (chunk_id 328):
> a statement that unless the consumer , within thirty days after receipt of the notice, disputes the validity of the debt, or any portion thereof, the debt will be assumed to be valid by the debt collector;

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 3
_Cites:_ `§ 809(a)(4)` (chunk_id 329)

**Claim text:**
> The notice must include a statement that if the consumer notifies the debt collector **in writing** within the thirty-day period that the debt (or any portion) is disputed, the debt collector will obtain verification of the debt or a copy of a judgment, and a copy of such verification or judgment will be mailed to the consumer.

**Cited chunk text:**
_§ 809(a)(4)_ (chunk_id 329):
> a statement that if the consumer notifies the debt collector in writing within the thirty-day period that the debt, or any portion thereof, is disputed, the debt collector will obtain verification of the debt or a copy of a judgment against the consumer and a copy of such verification or judgment will be mailed to the consumer by the debt collector; and

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 4
_Cites:_ `§ 809(a)(5)` (chunk_id 330)

**Claim text:**
> The notice must also include a statement that, upon the consumer's written request within the thirty-day period, the debt collector will provide the name and address of the original creditor, if different from the current creditor.

**Cited chunk text:**
_§ 809(a)(5)_ (chunk_id 330):
> a statement that, upon the consumer ’s written request within the thirty-day period, the debt collector will provide the consumer with the name and address of the original creditor , if different from the current creditor .

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 5
_Cites:_ `§ 809(b)` (chunk_id 331)

**Claim text:**
> If the consumer notifies the debt collector in writing within the thirty-day period that the debt is disputed, or requests the name and address of the original creditor, the debt collector must cease collection of the debt (or the disputed portion) until it obtains verification of the debt, a copy of a judgment, or the name and address of the original creditor, and mails that information to the consumer.

**Cited chunk text:**
_§ 809(b)_ (chunk_id 331):
> Disputed debts. If the consumer notifies the debt collector in writing within the thirty-day period described in subsection (a) that the debt, or any portion thereof, is disputed, or that the consumer requests the name and address of the original creditor , the debt collector shall cease collection of the debt, or any disputed portion thereof, until the debt collector obtains verification of the debt or a copy of a judgment, or the name and address of the original creditor , and a copy of such verification or judgment, or name and address of the original creditor , is mailed to the consumer by the debt collector. Collection activities and communications that do not otherwise violate this subchapter may continue during the 30-day period referred to in subsection (a) unless the consumer has notified the debt collector in writing that the debt, or any portion of the debt, is disputed or that the consumer requests the name and address of the original creditor. Any collection activities and communication during the 30-day period may not overshadow or be inconsistent with the disclosure of the consumer’ s right to dispute the debt or request the name and address of the original creditor.

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

### Extra citations (cited but not in expected)
Classify each below in the JSON's `extra_citations` array.

- **`§ 809(a)(3)`** (chunk_id(s): [328]):
> a statement that unless the consumer , within thirty days after receipt of the notice, disputes the validity of the debt, or any portion thereof, the debt will be assumed to be valid by the debt collector;
  → _classify in JSON: `hierarchical` | `contextual` | `off_topic`_

- **`§ 809(a)(4)`** (chunk_id(s): [329]):
> a statement that if the consumer notifies the debt collector in writing within the thirty-day period that the debt, or any portion thereof, is disputed, the debt collector will obtain verification of the debt or a copy of a judgment against the consumer and a copy of such verification or judgment will be mailed to the consumer by the debt collector; and
  → _classify in JSON: `hierarchical` | `contextual` | `off_topic`_

- **`§ 809(a)(5)`** (chunk_id(s): [330]):
> a statement that, upon the consumer ’s written request within the thirty-day period, the debt collector will provide the consumer with the name and address of the original creditor , if different from the current creditor .
  → _classify in JSON: `hierarchical` | `contextual` | `off_topic`_

- **`§ 809(b)`** (chunk_id(s): [331]):
> Disputed debts. If the consumer notifies the debt collector in writing within the thirty-day period described in subsection (a) that the debt, or any portion thereof, is disputed, or that the consumer requests the name and address of the original creditor , the debt collector shall cease collection of the debt, or any disputed portion thereof, until the debt collector obtains verification of the debt or a copy of a judgment, or the name and address of the original creditor , and a copy of such verification or judgment, or name and address of the original creditor , is mailed to the consumer by the debt collector. Collection activities and communications that do not otherwise violate this subchapter may continue during the 30-day period referred to in subsection (a) unless the consumer has notified the debt collector in writing that the debt, or any portion of the debt, is disputed or that the consumer requests the name and address of the original creditor. Any collection activities and communication during the 30-day period may not overshadow or be inconsistent with the disclosure of the consumer’ s right to dispute the debt or request the name and address of the original creditor.
  → _classify in JSON: `hierarchical` | `contextual` | `off_topic`_

---

## fdcpa-004
**Query:** Can a debt collector contact me at my workplace?

**Expected:** `§ 805(a)(3)`  **Cited:** `§ 805(a), § 805(a)(3), § 805(b)`  **Recall:** 1.00  **Precision:** 0.33

**Retrieved top-5:**

| rank | chunk_id | section_ref | rerank |
|---:|---:|:---|---:|
| 1 | 284 | `§ 805(a)(3)` | 0.699 |
| 2 | 277 | `§ 804(3)` | 0.340 |
| 3 | 285 | `§ 805(b)` | 0.330 |
| 4 | 274 | `§ 804` | 0.330 |
| 5 | 281 | `§ 805(a)` | 0.290 |

### Claims
#### Claim 1
_Cites:_ `§ 805(a)` (chunk_id 281)

**Claim text:**
> Generally, a debt collector may not communicate with a consumer in connection with the collection of any debt without the prior consent of the consumer given directly to the debt collector or the express permission of a court of competent jurisdiction.

**Cited chunk text:**
_§ 805(a)_ (chunk_id 281):
> Communication with the consumer generally. Without the prior consent of the consumer given directly to the debt collector or the express permission of a court of competent jurisdiction, a debt collector may not communicate with a consumer in connection with the collection of any debt—

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 2
_Cites:_ `§ 805(a)(3)` (chunk_id 284)

**Claim text:**
> Specifically, a debt collector is prohibited from contacting you at your place of employment if the debt collector knows or has reason to know that your employer prohibits you from receiving such communications.

**Cited chunk text:**
_§ 805(a)(3)_ (chunk_id 284):
> at the consumer ’s place of employment if the debt collector knows or has reason to know that the consumer ’s employer prohibits the consumer from receiving such communication.

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 3
_Cites:_ `§ 805(b)` (chunk_id 285)

**Claim text:**
> Additionally, without prior consumer consent, a court's express permission, or as reasonably necessary to effectuate a post-judgment judicial remedy, a debt collector may not communicate with any person other than the consumer, their attorney, a consumer reporting agency, the creditor, or the attorneys of the creditor or debt collector.

**Cited chunk text:**
_§ 805(b)_ (chunk_id 285):
> Communication with third parties. Except as provided in section 1692b of this title , without the prior consent of the consumer given directly to the debt collector, or the express permission of a court of competent jurisdiction, or as reasonably necessary to effectuate a postjudgment judicial remedy, a debt collector may not communicate, in connection with the collection of any debt, with any person other than the consumer, his attorney, a consumer reporting agency if otherwise permitted by law, the creditor, the attorney of the creditor, or the attorney of the debt collector.

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

### Extra citations (cited but not in expected)
Classify each below in the JSON's `extra_citations` array.

- **`§ 805(a)`** (chunk_id(s): [281]):
> Communication with the consumer generally. Without the prior consent of the consumer given directly to the debt collector or the express permission of a court of competent jurisdiction, a debt collector may not communicate with a consumer in connection with the collection of any debt—
  → _classify in JSON: `hierarchical` | `contextual` | `off_topic`_

- **`§ 805(b)`** (chunk_id(s): [285]):
> Communication with third parties. Except as provided in section 1692b of this title , without the prior consent of the consumer given directly to the debt collector, or the express permission of a court of competent jurisdiction, or as reasonably necessary to effectuate a postjudgment judicial remedy, a debt collector may not communicate, in connection with the collection of any debt, with any person other than the consumer, his attorney, a consumer reporting agency if otherwise permitted by law, the creditor, the attorney of the creditor, or the attorney of the debt collector.
  → _classify in JSON: `hierarchical` | `contextual` | `off_topic`_

---

## fdcpa-005
**Query:** What happens if I tell a debt collector that I have an attorney?

**Expected:** `§ 805(a)(2)`  **Cited:** `§ 805(a)(2), § 805(a)(2), § 805(b), § 804(6)`  **Recall:** 1.00  **Precision:** 0.33

**Retrieved top-5:**

| rank | chunk_id | section_ref | rerank |
|---:|---:|:---|---:|
| 1 | 280 | `§ 804(6)` | 0.773 |
| 2 | 283 | `§ 805(a)(2)` | 0.759 |
| 3 | 285 | `§ 805(b)` | 0.615 |
| 4 | 302 | `§ 807(3)` | 0.602 |
| 5 | 277 | `§ 804(3)` | 0.216 |

### Claims
#### Claim 1
_Cites:_ `§ 805(a)(2)` (chunk_id 283)

**Claim text:**
> Once a debt collector knows you are represented by an attorney with respect to the debt and has knowledge of (or can readily ascertain) your attorney's name and address, the debt collector must stop communicating directly with you and instead communicate only with your attorney.

**Cited chunk text:**
_§ 805(a)(2)_ (chunk_id 283):
> if the debt collector knows the consumer is represented by an attorney with respect to such debt and has knowledge of, or can readily ascertain, such attorney’s name and address, unless the attorney fails to respond within a reasonable period of time to a communication from the debt collector or unless the attorney consents to direct communication with the consumer ; or

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 2
_Cites:_ `§ 805(a)(2)` (chunk_id 283)

**Claim text:**
> The debt collector may still contact you directly if your attorney fails to respond within a reasonable period of time to a communication from the debt collector, or if your attorney consents to direct communication with you.

**Cited chunk text:**
_§ 805(a)(2)_ (chunk_id 283):
> if the debt collector knows the consumer is represented by an attorney with respect to such debt and has knowledge of, or can readily ascertain, such attorney’s name and address, unless the attorney fails to respond within a reasonable period of time to a communication from the debt collector or unless the attorney consents to direct communication with the consumer ; or

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 3
_Cites:_ `§ 805(b)` (chunk_id 285)

**Claim text:**
> More broadly, when it comes to third parties, a debt collector may not communicate with anyone other than you, your attorney, a consumer reporting agency (if permitted by law), the creditor, the creditor's attorney, or the debt collector's own attorney — unless you give prior consent, a court grants permission, or it is reasonably necessary to carry out a post-judgment judicial remedy.

**Cited chunk text:**
_§ 805(b)_ (chunk_id 285):
> Communication with third parties. Except as provided in section 1692b of this title , without the prior consent of the consumer given directly to the debt collector, or the express permission of a court of competent jurisdiction, or as reasonably necessary to effectuate a postjudgment judicial remedy, a debt collector may not communicate, in connection with the collection of any debt, with any person other than the consumer, his attorney, a consumer reporting agency if otherwise permitted by law, the creditor, the attorney of the creditor, or the attorney of the debt collector.

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 4
_Cites:_ `§ 804(6)` (chunk_id 280)

**Claim text:**
> Additionally, once the debt collector knows you are represented by an attorney regarding the subject debt and can ascertain that attorney's contact information, the debt collector must not communicate with any other person (such as third parties seeking your location) except through that attorney, unless the attorney fails to respond within a reasonable time.

**Cited chunk text:**
_§ 804(6)_ (chunk_id 280):
> after the debt collector knows the consumer is represented by an attorney with regard to the subject debt and has knowledge of, or can readily ascertain, such attorney’s name and address, not communicate with any person other than that attorney, unless the attorney fails to respond within a reasonable period of time to communication from the debt collector.

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

### Extra citations (cited but not in expected)
Classify each below in the JSON's `extra_citations` array.

- **`§ 804(6)`** (chunk_id(s): [280]):
> after the debt collector knows the consumer is represented by an attorney with regard to the subject debt and has knowledge of, or can readily ascertain, such attorney’s name and address, not communicate with any person other than that attorney, unless the attorney fails to respond within a reasonable period of time to communication from the debt collector.
  → _classify in JSON: `hierarchical` | `contextual` | `off_topic`_

- **`§ 805(b)`** (chunk_id(s): [285]):
> Communication with third parties. Except as provided in section 1692b of this title , without the prior consent of the consumer given directly to the debt collector, or the express permission of a court of competent jurisdiction, or as reasonably necessary to effectuate a postjudgment judicial remedy, a debt collector may not communicate, in connection with the collection of any debt, with any person other than the consumer, his attorney, a consumer reporting agency if otherwise permitted by law, the creditor, the attorney of the creditor, or the attorney of the debt collector.
  → _classify in JSON: `hierarchical` | `contextual` | `off_topic`_

---

## fdcpa-006
**Query:** How does the FDCPA define a debt collector?

**Expected:** `§ 803(6)`  **Cited:** `§ 803(6), § 803(6), § 803(6)`  **Recall:** 1.00  **Precision:** 1.00

**Retrieved top-5:**

| rank | chunk_id | section_ref | rerank |
|---:|---:|:---|---:|
| 1 | 271 | `§ 803(6)` | 0.857 |
| 2 | 292 | `§ 806` | 0.536 |
| 3 | 361 | `§ 814(d)` | 0.468 |
| 4 | 316 | `§ 808` | 0.467 |
| 5 | 324 | `§ 808(8)` | 0.455 |

### Claims
#### Claim 1
_Cites:_ `§ 803(6)` (chunk_id 271)

**Claim text:**
> A "debt collector" means any person who uses any instrumentality of interstate commerce or the mails in any business the principal purpose of which is the collection of any debts, or who regularly collects or attempts to collect, directly or indirectly, debts owed or due or asserted to be owed or due another.

**Cited chunk text:**
_§ 803(6)_ (chunk_id 271):
> The term “ debt collector ” means any person who uses any instrumentality of interstate commerce or the mails in any business the principal purpose of which is the collection of any debts, or who regularly collects or attempts to collect, directly or indirectly, debts owed or due or asserted to be owed or due another. Notwithstanding the exclusion provided by clause (F) of the last sentence of this paragraph, the term includes any creditor who, in the process of collecting his own debts, uses any name other than his own which would indicate that a third person is collecting or attempting to collect such debts. For the purpose of section 1692f(6) of this title , such term also includes any person who uses any instrumentality of interstate commerce or the mails in any business the principal purpose of which is the enforcement of security interests. The term does not include—

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 2
_Cites:_ `§ 803(6)` (chunk_id 271)

**Claim text:**
> The term also includes any creditor who, in the process of collecting his own debts, uses any name other than his own which would indicate that a third person is collecting or attempting to collect such debts.

**Cited chunk text:**
_§ 803(6)_ (chunk_id 271):
> The term “ debt collector ” means any person who uses any instrumentality of interstate commerce or the mails in any business the principal purpose of which is the collection of any debts, or who regularly collects or attempts to collect, directly or indirectly, debts owed or due or asserted to be owed or due another. Notwithstanding the exclusion provided by clause (F) of the last sentence of this paragraph, the term includes any creditor who, in the process of collecting his own debts, uses any name other than his own which would indicate that a third person is collecting or attempting to collect such debts. For the purpose of section 1692f(6) of this title , such term also includes any person who uses any instrumentality of interstate commerce or the mails in any business the principal purpose of which is the enforcement of security interests. The term does not include—

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 3
_Cites:_ `§ 803(6)` (chunk_id 271)

**Claim text:**
> For the purpose of § 1692f(6), the term "debt collector" also includes any person who uses any instrumentality of interstate commerce or the mails in any business the principal purpose of which is the enforcement of security interests.

**Cited chunk text:**
_§ 803(6)_ (chunk_id 271):
> The term “ debt collector ” means any person who uses any instrumentality of interstate commerce or the mails in any business the principal purpose of which is the collection of any debts, or who regularly collects or attempts to collect, directly or indirectly, debts owed or due or asserted to be owed or due another. Notwithstanding the exclusion provided by clause (F) of the last sentence of this paragraph, the term includes any creditor who, in the process of collecting his own debts, uses any name other than his own which would indicate that a third person is collecting or attempting to collect such debts. For the purpose of section 1692f(6) of this title , such term also includes any person who uses any instrumentality of interstate commerce or the mails in any business the principal purpose of which is the enforcement of security interests. The term does not include—

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

---

## fdcpa-007
**Query:** How do I get a debt collector to stop calling me?

**Expected:** `§ 805(c)`  **Cited:** `§ 805(c), § 805(a)(2), § 804(6)`  **Recall:** 1.00  **Precision:** 0.33

**Retrieved top-5:**

| rank | chunk_id | section_ref | rerank |
|---:|---:|:---|---:|
| 1 | 286 | `§ 805(c)` | 0.740 |
| 2 | 280 | `§ 804(6)` | 0.705 |
| 3 | 277 | `§ 804(3)` | 0.561 |
| 4 | 331 | `§ 809(b)` | 0.561 |
| 5 | 283 | `§ 805(a)(2)` | 0.516 |

### Claims
#### Claim 1
_Cites:_ `§ 805(c)` (chunk_id 286)

**Claim text:**
> To get a debt collector to stop contacting you, notify the debt collector **in writing** that you wish the debt collector to cease further communication with you. Once they receive this written notice, they are legally required to stop communicating with you about the debt.

**Cited chunk text:**
_§ 805(c)_ (chunk_id 286):
> Ceasing communication. If a consumer notifies a debt collector in writing that the consumer refuses to pay a debt or that the consumer wishes the debt collector to cease further communication with the consumer , the debt collector shall not communicate further with the consumer with respect to such debt, except—

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 2
_Cites:_ `§ 805(a)(2)` (chunk_id 283), `§ 804(6)` (chunk_id 280)

**Claim text:**
> Alternatively, if you hire an attorney to represent you regarding the debt, the debt collector must stop communicating with you directly and can only communicate with your attorney (unless the attorney fails to respond within a reasonable period of time or consents to direct contact with you).

**Cited chunk text:**
_§ 805(a)(2)_ (chunk_id 283):
> if the debt collector knows the consumer is represented by an attorney with respect to such debt and has knowledge of, or can readily ascertain, such attorney’s name and address, unless the attorney fails to respond within a reasonable period of time to a communication from the debt collector or unless the attorney consents to direct communication with the consumer ; or

_§ 804(6)_ (chunk_id 280):
> after the debt collector knows the consumer is represented by an attorney with regard to the subject debt and has knowledge of, or can readily ascertain, such attorney’s name and address, not communicate with any person other than that attorney, unless the attorney fails to respond within a reasonable period of time to communication from the debt collector.

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

### Extra citations (cited but not in expected)
Classify each below in the JSON's `extra_citations` array.

- **`§ 804(6)`** (chunk_id(s): [280]):
> after the debt collector knows the consumer is represented by an attorney with regard to the subject debt and has knowledge of, or can readily ascertain, such attorney’s name and address, not communicate with any person other than that attorney, unless the attorney fails to respond within a reasonable period of time to communication from the debt collector.
  → _classify in JSON: `hierarchical` | `contextual` | `off_topic`_

- **`§ 805(a)(2)`** (chunk_id(s): [283]):
> if the debt collector knows the consumer is represented by an attorney with respect to such debt and has knowledge of, or can readily ascertain, such attorney’s name and address, unless the attorney fails to respond within a reasonable period of time to a communication from the debt collector or unless the attorney consents to direct communication with the consumer ; or
  → _classify in JSON: `hierarchical` | `contextual` | `off_topic`_

---

## fdcpa-008
**Query:** Can a debt collector tell my family or my employer about my debt?

**Expected:** `§ 805(b)`  **Cited:** `§ 805(b), § 805(b), § 805(a)(3), § 804(6)`  **Recall:** 1.00  **Precision:** 0.33

**Retrieved top-5:**

| rank | chunk_id | section_ref | rerank |
|---:|---:|:---|---:|
| 1 | 284 | `§ 805(a)(3)` | 0.708 |
| 2 | 285 | `§ 805(b)` | 0.683 |
| 3 | 281 | `§ 805(a)` | 0.594 |
| 4 | 280 | `§ 804(6)` | 0.576 |
| 5 | 299 | `§ 807` | 0.481 |

### Claims
#### Claim 1
_Cites:_ `§ 805(b)` (chunk_id 285)

**Claim text:**
> Generally, a debt collector may NOT communicate with third parties (such as family members or employers) about your debt without your prior consent, the express permission of a court, or as reasonably necessary to effectuate a post-judgment judicial remedy.

**Cited chunk text:**
_§ 805(b)_ (chunk_id 285):
> Communication with third parties. Except as provided in section 1692b of this title , without the prior consent of the consumer given directly to the debt collector, or the express permission of a court of competent jurisdiction, or as reasonably necessary to effectuate a postjudgment judicial remedy, a debt collector may not communicate, in connection with the collection of any debt, with any person other than the consumer, his attorney, a consumer reporting agency if otherwise permitted by law, the creditor, the attorney of the creditor, or the attorney of the debt collector.

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 2
_Cites:_ `§ 805(b)` (chunk_id 285)

**Claim text:**
> The only third parties a debt collector is permitted to contact (under specific circumstances) include the consumer's attorney, a consumer reporting agency if otherwise permitted by law, the creditor, the creditor's attorney, or the debt collector's own attorney.

**Cited chunk text:**
_§ 805(b)_ (chunk_id 285):
> Communication with third parties. Except as provided in section 1692b of this title , without the prior consent of the consumer given directly to the debt collector, or the express permission of a court of competent jurisdiction, or as reasonably necessary to effectuate a postjudgment judicial remedy, a debt collector may not communicate, in connection with the collection of any debt, with any person other than the consumer, his attorney, a consumer reporting agency if otherwise permitted by law, the creditor, the attorney of the creditor, or the attorney of the debt collector.

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 3
_Cites:_ `§ 805(a)(3)` (chunk_id 284)

**Claim text:**
> Additionally, a debt collector is prohibited from communicating with a consumer at their place of employment if the debt collector knows or has reason to know that the consumer's employer prohibits the consumer from receiving such communications.

**Cited chunk text:**
_§ 805(a)(3)_ (chunk_id 284):
> at the consumer ’s place of employment if the debt collector knows or has reason to know that the consumer ’s employer prohibits the consumer from receiving such communication.

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 4
_Cites:_ `§ 804(6)` (chunk_id 280)

**Claim text:**
> If the consumer is represented by an attorney regarding the subject debt, and the debt collector knows the attorney's name and address, the debt collector must communicate only with that attorney and not with other persons.

**Cited chunk text:**
_§ 804(6)_ (chunk_id 280):
> after the debt collector knows the consumer is represented by an attorney with regard to the subject debt and has knowledge of, or can readily ascertain, such attorney’s name and address, not communicate with any person other than that attorney, unless the attorney fails to respond within a reasonable period of time to communication from the debt collector.

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

### Extra citations (cited but not in expected)
Classify each below in the JSON's `extra_citations` array.

- **`§ 804(6)`** (chunk_id(s): [280]):
> after the debt collector knows the consumer is represented by an attorney with regard to the subject debt and has knowledge of, or can readily ascertain, such attorney’s name and address, not communicate with any person other than that attorney, unless the attorney fails to respond within a reasonable period of time to communication from the debt collector.
  → _classify in JSON: `hierarchical` | `contextual` | `off_topic`_

- **`§ 805(a)(3)`** (chunk_id(s): [284]):
> at the consumer ’s place of employment if the debt collector knows or has reason to know that the consumer ’s employer prohibits the consumer from receiving such communication.
  → _classify in JSON: `hierarchical` | `contextual` | `off_topic`_

---

## fdcpa-009
**Query:** Can a debt collector threaten to have me arrested?

**Expected:** `§ 807(4)`  **Cited:** `§ 807(4), § 807(5), § 806`  **Recall:** 1.00  **Precision:** 0.33

**Retrieved top-5:**

| rank | chunk_id | section_ref | rerank |
|---:|---:|:---|---:|
| 1 | 319 | `§ 808(3)` | 0.706 |
| 2 | 303 | `§ 807(4)` | 0.664 |
| 3 | 292 | `§ 806` | 0.490 |
| 4 | 304 | `§ 807(5)` | 0.254 |
| 5 | 336 | `§ 811(a)` | 0.239 |

### Claims
#### Claim 1
_Cites:_ `§ 807(4)` (chunk_id 303)

**Claim text:**
> A debt collector is prohibited from representing or implying that nonpayment of a debt will result in the arrest or imprisonment of any person, unless such action is actually lawful AND the debt collector or creditor genuinely intends to take that action.

**Cited chunk text:**
_§ 807(4)_ (chunk_id 303):
> The representation or implication that nonpayment of any debt will result in the arrest or imprisonment of any person or the seizure, garnishment, attachment, or sale of any property or wages of any person unless such action is lawful and the debt collector or creditor intends to take such action.

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 2
_Cites:_ `§ 807(5)` (chunk_id 304)

**Claim text:**
> Additionally, a debt collector may not threaten to take any action that cannot legally be taken or that is not intended to be taken, which would include threats of arrest that are not legally supportable.

**Cited chunk text:**
_§ 807(5)_ (chunk_id 304):
> The threat to take any action that cannot legally be taken or that is not intended to be taken.

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 3
_Cites:_ `§ 806` (chunk_id 292)

**Claim text:**
> More broadly, a debt collector may not engage in any conduct whose natural consequence is to harass, oppress, or abuse any person in connection with the collection of a debt.

**Cited chunk text:**
_§ 806_ (chunk_id 292):
> A debt collector may not engage in any conduct the natural consequence of which is to harass, oppress, or abuse any person in connection with the collection of a debt . Without limiting the general application of the foregoing, the following conduct is a violation of this section:

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

### Extra citations (cited but not in expected)
Classify each below in the JSON's `extra_citations` array.

- **`§ 806`** (chunk_id(s): [292]):
> A debt collector may not engage in any conduct the natural consequence of which is to harass, oppress, or abuse any person in connection with the collection of a debt . Without limiting the general application of the foregoing, the following conduct is a violation of this section:
  → _classify in JSON: `hierarchical` | `contextual` | `off_topic`_

- **`§ 807(5)`** (chunk_id(s): [304]):
> The threat to take any action that cannot legally be taken or that is not intended to be taken.
  → _classify in JSON: `hierarchical` | `contextual` | `off_topic`_

---

## fdcpa-010
**Query:** Can a debt collector deposit my postdated check before the date on it?

**Expected:** `§ 808(2), § 808(3), § 808(4)`  **Cited:** `§ 808, § 808(4)`  **Recall:** 0.33  **Precision:** 0.50

**Retrieved top-5:**

| rank | chunk_id | section_ref | rerank |
|---:|---:|:---|---:|
| 1 | 318 | `§ 808(2)` | 0.817 |
| 2 | 320 | `§ 808(4)` | 0.769 |
| 3 | 319 | `§ 808(3)` | 0.475 |
| 4 | 370 | `§ 818(b)(1)` | 0.182 |
| 5 | 316 | `§ 808` | 0.113 |

### Claims
#### Claim 1
_Cites:_ `§ 808` (chunk_id 316)

**Claim text:**
> Under the FDCPA, a debt collector may not use unfair or unconscionable means to collect or attempt to collect any debt.

**Cited chunk text:**
_§ 808_ (chunk_id 316):
> A debt collector may not use unfair or unconscionable means to collect or attempt to collect any debt . Without limiting the general application of the foregoing, the following conduct is a violation of this section:

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 2
_Cites:_ `§ 808(4)` (chunk_id 320)

**Claim text:**
> Specifically, depositing or threatening to deposit any postdated check or other postdated payment instrument prior to the date on such check or instrument is a violation of the FDCPA.

**Cited chunk text:**
_§ 808(4)_ (chunk_id 320):
> Depositing or threatening to deposit any postdated check or other postdated payment instrument prior to the date on such check or instrument.

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

### Extra citations (cited but not in expected)
Classify each below in the JSON's `extra_citations` array.

- **`§ 808`** (chunk_id(s): [316]):
> A debt collector may not use unfair or unconscionable means to collect or attempt to collect any debt . Without limiting the general application of the foregoing, the following conduct is a violation of this section:
  → _classify in JSON: `hierarchical` | `contextual` | `off_topic`_

---

## fdcpa-011
**Query:** What does § 805 cover?

**Expected:** `§ 805, § 805(a)`  **Cited:** `§ 805(a), § 805(a)(1), § 805(c), § 805(c)(1), § 805(c)(2)`  **Recall:** 0.50  **Precision:** 0.20

**Retrieved top-5:**

| rank | chunk_id | section_ref | rerank |
|---:|---:|:---|---:|
| 1 | 281 | `§ 805(a)` | 0.625 |
| 2 | 286 | `§ 805(c)` | 0.624 |
| 3 | 282 | `§ 805(a)(1)` | 0.604 |
| 4 | 288 | `§ 805(c)(2)` | 0.561 |
| 5 | 287 | `§ 805(c)(1)` | 0.552 |

### Claims
#### Claim 1
_Cites:_ `§ 805(a)` (chunk_id 281)

**Claim text:**
> § 805 covers communication with the consumer generally, providing that without the prior consent of the consumer given directly to the debt collector or the express permission of a court of competent jurisdiction, a debt collector may not communicate with a consumer in connection with the collection of any debt.

**Cited chunk text:**
_§ 805(a)_ (chunk_id 281):
> Communication with the consumer generally. Without the prior consent of the consumer given directly to the debt collector or the express permission of a court of competent jurisdiction, a debt collector may not communicate with a consumer in connection with the collection of any debt—

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 2
_Cites:_ `§ 805(a)(1)` (chunk_id 282)

**Claim text:**
> § 805(a)(1) restricts debt collectors from communicating at any unusual time or place, or a time or place known to be inconvenient to the consumer. In the absence of knowledge of circumstances to the contrary, a debt collector shall assume that the convenient time for communicating with a consumer is after 8 a.m. and before 9 p.m. local time at the consumer's location.

**Cited chunk text:**
_§ 805(a)(1)_ (chunk_id 282):
> at any unusual time or place or a time or place known or which should be known to be inconvenient to the consumer . In the absence of knowledge of circumstances to the contrary, a debt collector shall assume that the convenient time for communicating with a consumer is after 8 o’clock antemeridian and before 9 o’clock postmeridian, local time at the consumer ’s location;

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 3
_Cites:_ `§ 805(c)` (chunk_id 286)

**Claim text:**
> § 805(c) covers ceasing communication: if a consumer notifies a debt collector in writing that the consumer refuses to pay a debt or wishes the debt collector to cease further communication, the debt collector shall not communicate further with the consumer with respect to such debt, with limited exceptions.

**Cited chunk text:**
_§ 805(c)_ (chunk_id 286):
> Ceasing communication. If a consumer notifies a debt collector in writing that the consumer refuses to pay a debt or that the consumer wishes the debt collector to cease further communication with the consumer , the debt collector shall not communicate further with the consumer with respect to such debt, except—

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 4
_Cites:_ `§ 805(c)(1)` (chunk_id 287)

**Claim text:**
> One exception to the ceasing communication rule allows the debt collector to advise the consumer that the debt collector's further efforts are being terminated.

**Cited chunk text:**
_§ 805(c)(1)_ (chunk_id 287):
> to advise the consumer that the debt collector’s further efforts are being terminated;

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

#### Claim 5
_Cites:_ `§ 805(c)(2)` (chunk_id 288)

**Claim text:**
> Another exception permits the debt collector to notify the consumer that the debt collector or creditor may invoke specified remedies which are ordinarily invoked by such debt collector or creditor.

**Cited chunk text:**
_§ 805(c)(2)_ (chunk_id 288):
> to notify the consumer that the debt collector or creditor may invoke specified remedies which are ordinarily invoked by such debt collector or creditor; or

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

### Extra citations (cited but not in expected)
Classify each below in the JSON's `extra_citations` array.

- **`§ 805(a)(1)`** (chunk_id(s): [282]):
> at any unusual time or place or a time or place known or which should be known to be inconvenient to the consumer . In the absence of knowledge of circumstances to the contrary, a debt collector shall assume that the convenient time for communicating with a consumer is after 8 o’clock antemeridian and before 9 o’clock postmeridian, local time at the consumer ’s location;
  → _classify in JSON: `hierarchical` | `contextual` | `off_topic`_

- **`§ 805(c)`** (chunk_id(s): [286]):
> Ceasing communication. If a consumer notifies a debt collector in writing that the consumer refuses to pay a debt or that the consumer wishes the debt collector to cease further communication with the consumer , the debt collector shall not communicate further with the consumer with respect to such debt, except—
  → _classify in JSON: `hierarchical` | `contextual` | `off_topic`_

- **`§ 805(c)(1)`** (chunk_id(s): [287]):
> to advise the consumer that the debt collector’s further efforts are being terminated;
  → _classify in JSON: `hierarchical` | `contextual` | `off_topic`_

- **`§ 805(c)(2)`** (chunk_id(s): [288]):
> to notify the consumer that the debt collector or creditor may invoke specified remedies which are ordinarily invoked by such debt collector or creditor; or
  → _classify in JSON: `hierarchical` | `contextual` | `off_topic`_

---

## fdcpa-012
**Query:** If I tell the debt collector verbally to stop, do they have to listen, or do I need to put it in writing?

**Expected:** `§ 805(c)`  **Cited:** `§ 805(c)`  **Recall:** 1.00  **Precision:** 1.00

**Retrieved top-5:**

| rank | chunk_id | section_ref | rerank |
|---:|---:|:---|---:|
| 1 | 286 | `§ 805(c)` | 0.645 |
| 2 | 331 | `§ 809(b)` | 0.458 |
| 3 | 287 | `§ 805(c)(1)` | 0.375 |
| 4 | 329 | `§ 809(a)(4)` | 0.326 |
| 5 | 280 | `§ 804(6)` | 0.261 |

### Claims
#### Claim 1
_Cites:_ `§ 805(c)` (chunk_id 286)

**Claim text:**
> Under the FDCPA, for a debt collector to be required to cease communication, the consumer must notify the debt collector **in writing** that they refuse to pay the debt or wish the debt collector to stop communicating. A verbal request is not sufficient to trigger this legal obligation.

**Cited chunk text:**
_§ 805(c)_ (chunk_id 286):
> Ceasing communication. If a consumer notifies a debt collector in writing that the consumer refuses to pay a debt or that the consumer wishes the debt collector to cease further communication with the consumer , the debt collector shall not communicate further with the consumer with respect to such debt, except—

→ _grade in JSON: `faithful` (true/false), `answer_relevant` (true/false)_

---
