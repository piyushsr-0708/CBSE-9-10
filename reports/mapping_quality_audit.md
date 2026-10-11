# Mapping Quality Audit Report

## 1. Confidence Score Distribution

| Score Range | Count | Cumulative % |
|---|---|---|
| 0.00-0.05 | 470 | 27.2% |
| 0.05-0.10 | 28 | 28.9% |
| 0.10-0.15 | 67 | 32.7% |
| 0.15-0.20 | 157 | 41.8% |
| 0.20-0.25 | 243 | 55.9% |
| 0.25-0.30 | 179 | 66.3% |
| 0.30-0.35 | 175 | 76.4% |
| 0.35-0.40 | 81 | 81.1% |
| 0.40-0.45 | 61 | 84.6% |
| 0.45-0.50 | 76 | 89.0% |
| 0.50-0.60 | 82 | 93.8% |
| 0.60-0.70 | 39 | 96.1% |
| >0.70 | 68 | 100.0% |

**Total canonical questions:** 1726

## 2. Per-Subject/Class Breakdown

| Class | Subject | Count | Mean Conf | Median Conf | Auto | Chap-Only | Review | Unclass | OOS |
|---|---|---|---|---|---|---|---|---|---|
| class10 | computer_application | 53 | 0.000 | 0.000 | 0 | 0 | 0 | 53 | 0 |
| class10 | home_science | 90 | 0.268 | 0.200 | 32 | 11 | 8 | 39 | 0 |
| class10 | maths | 126 | 0.000 | 0.000 | 0 | 0 | 0 | 126 | 0 |
| class10 | social_science | 116 | 0.355 | 0.335 | 30 | 49 | 25 | 12 | 0 |
| class9 | maths | 466 | 0.214 | 0.203 | 59 | 118 | 167 | 122 | 0 |
| class9 | science | 394 | 0.324 | 0.300 | 90 | 171 | 87 | 46 | 0 |
| class9 | social_science | 481 | 0.271 | 0.232 | 35 | 147 | 208 | 72 | 18 |

## 3. Suspicious Mapping Detection

**Total suspicious records flagged:** 617

### Concern Type Breakdown

| Concern | Count |
|---|---|
| TOPIC_MAPPED_LOW_CONF | 453 |
| VISUAL_CONTEXT_LIKELY_NEEDED | 92 |
| POSSIBLE_BOILERPLATE_MAPPED | 41 |
| CHAPTER_ONLY_VERY_LOW_CONF | 41 |
| SHORT_TEXT_MAPPED | 5 |

### Suspicious by Subject

| Class | Subject | Suspicious Count |
|---|---|---|
| class10 | home_science | 20 |
| class10 | social_science | 45 |
| class9 | maths | 189 |
| class9 | science | 137 |
| class9 | social_science | 226 |

## 4. Spot-Check Examples by Subject

### class10_computer_application

**unclassifiable_example:**
- text: The acronym SSH stands for_________________. a. Safe Shell b. Software Shell c. Secure Shell d. Simple Shell
- confidence: 0.0

### class10_home_science

**high_conf_example:**
- text: Which is the best way to save energy while working in the office? a. Improve posture b. Sleep in between the working hours c. Eat balanced diet d. Deep breath and exercise regularly 1 MCQ
- chapter: CBSE10_HS_02
- chapter_name: a)
- topic: CBSE10_HS_02_TOP01
- confidence: 0.4588743217531921

**borderline_auto:**
- text: Which is the best way to save energy while working in the office? a. Improve posture b. Sleep in between the working hours c. Eat balanced diet d. Deep breath and exercise regularly 1 MCQ
- chapter: CBSE10_HS_02
- chapter_name: a)
- confidence: 0.4588743217531921

**unclassifiable_example:**
- text: What could be the possible reason of cross contamination in food? a. Using same chopping boards for both vegetarian and non- vegetarian food b. Packing and labelling of food products c. Keeping the ra
- confidence: 0.0

### class10_maths

**unclassifiable_example:**
- text: If two positive integers a and b are written as a = x3y2 and b = xy3, where x, y are prime numbers, then the result obtained by dividing the product of the positive integers by the LCM (a, b) is (a) x
- confidence: 0.0

### class10_social_science

**high_conf_example:**
- text: In addition to this, separate instructions are given with each section and question, wherever necessary.
- chapter: CBSE10_SST_52
- chapter_name: Section:
- topic: nan
- confidence: 1.0

**borderline_auto:**
- text: When many countries of Europe came together to form the European Union, was chosen as its headquarters. a. Brussels b. Paris c. London d. Zurich 1
- chapter: CBSE10_SST_02
- chapter_name: I
- confidence: 0.4587202555253948

**borderline_chapter:**
- text: You are a citizen of a country that has a democratic form of government. You want to ensure that the system of power-sharing in your country is effective and that no one branch of government has absol
- chapter: CBSE10_SST_34
- chapter_name:  Power – sharing  Federalism  Gender, Religion and Caste  Political Parties  Outcomes of Democracy
- confidence: 0.2838945786514623

**unclassifiable_example:**
- text: Read the data given below and answer the question. Educational Achievement of Rural Population of Uttar Pradesh As per the data given above who has the least percentage of literacy rate in rural popul
- confidence: 0.0

### class9_maths

**high_conf_example:**
- text: Assertion (A): Every linear equation in two variables has infinitely many solutions.​ Reason (R): For every value of x, there exists a corresponding value of y.​ (a) Both A and R are true and R is the
- chapter: CBSE9_MATH_02_CHA04
- chapter_name: Linear Equations in Two Variables
- topic: CBSE9_MATH_02_CHA04_TOP01
- confidence: 0.4717335758596774

**borderline_auto:**
- text: Assertion (A): Every linear equation in two variables has infinitely many solutions.​ Reason (R): For every value of x, there exists a corresponding value of y.​ (a) Both A and R are true and R is the
- chapter: CBSE9_MATH_02_CHA04
- chapter_name: Linear Equations in Two Variables
- confidence: 0.4717335758596774

**borderline_chapter:**
- text: Assertion (A): The product of two irrational numbers is always irrational.​ Reason (R): The square of any irrational number is irrational.​ (a) Both A and R are true and R is the correct explanation o
- chapter: CBSE9_MATH_01_CHA01
- chapter_name: Number System
- confidence: 0.2517485597270744

**unclassifiable_example:**
- text: The value of (81) 3/4 is: (a) 9 (b) 27 (c) 64 (d) 16 ​
- confidence: 0.0

### class9_science

**high_conf_example:**
- text: The SI unit of acceleration is: (a) m/s (b) m/s² (c) m³/s² (d) km/h ​ ​ www.vedantu.com ​ 1 ​
- chapter: CBSE9_SCI_10
- chapter_name: Force and Laws of Motion
- topic: CBSE9_SCI_10_TOP08
- confidence: 0.4539576387419617

**borderline_auto:**
- text: The SI unit of acceleration is: (a) m/s (b) m/s² (c) m³/s² (d) km/h ​ ​ www.vedantu.com ​ 1 ​
- chapter: CBSE9_SCI_10
- chapter_name: Force and Laws of Motion
- confidence: 0.4539576387419617

**borderline_chapter:**
- text: The process of changing a gas directly into a solid is called: (a) Condensation (b) Sublimation (c) Deposition (d) Melting ​
- chapter: CBSE9_SCI_05
- chapter_name: Exploring Mixtures and their Separation
- confidence: 0.2676464514120188

**unclassifiable_example:**
- text: The building blocks of proteins are: (a) Nucleotides (b) Fatty acids (c) Amino acids (d) Sugars ​
- confidence: 0.0

### class9_social_science

**high_conf_example:**
- text: Assertion (A): India’s climate is described as monsoon type.​ Reason (R): India experiences distinct wet and dry seasons due to the monsoon winds.​ (a) Both A and R are true and R is the correct expla
- chapter: CBSE9_SST_01_CHA03
- chapter_name: Atmosphere and Climate
- topic: CBSE9_SST_01_CHA03_TOP02
- confidence: 0.4979013672901062

**borderline_auto:**
- text: Assertion (A): India’s climate is described as monsoon type.​ Reason (R): India experiences distinct wet and dry seasons due to the monsoon winds.​ (a) Both A and R are true and R is the correct expla
- chapter: CBSE9_SST_01_CHA03
- chapter_name: Atmosphere and Climate
- confidence: 0.4979013672901062

**borderline_chapter:**
- text: What is the main feature of a democratic form of government? (a) Rule by the nobility (b) Participation of citizens in decision-making (c) Hereditary leadership (d) One-party rule ​
- chapter: CBSE9_SST_02_CHA05
- chapter_name: Authority
- confidence: 0.2802089929552007

**unclassifiable_example:**
- text: The Himalayan region is divided into how many parallel ranges? (a) One (b) Two (c) Three (d) Four ​ ​ www.vedantu.com ​ 1 ​
- confidence: 0.0


## 5. Threshold Analysis

### Around AUTO_VERIFY threshold (0.45)
Questions with confidence 0.43-0.47: 76

- [0.459] `CBSE10_HS_02` -> Which is the best way to save energy while working in the office? a. Improve posture b. Sleep in between the working hours c. Eat balanced diet d. Dee
- [0.459] `CBSE10_HS_02` -> What two points each to be considered and avoided while preparing meal for school going children? 2
- [0.459] `CBSE10_HS_05` -> A 3-year-old Riyanshi do not want to play with others. She enjoys playing with herself. a. What would be the two drawbacks of not engaging in play wit
- [0.459] `CBSE10_HS_06` -> Which of the following statement is incorrect with regards to kitchen hygiene? (A) Work surfaces, floors and walls should be absorbent. (B) No food pa
- [0.459] `CBSE10_HS_05` -> “Play influences social and emotional development.” Justify this statement with two examples. 2 (CBQ)

### Around CHAPTER_ONLY threshold (0.25)
Questions with confidence 0.23-0.27: 180

- [0.246] `CBSE10_SST_22` -> Which place in India has an artificial lake to conserve water that dates to 11th century? a. Delhi b. Bhopal c. Mumbai d. Kolhapur 1
- [0.257] `CBSE10_SST_19` -> If there is a disruption by transporters and lorries refuse to transport vegetables, milk, etc. from rural areas to urban areas, food will become scar
- [0.245] `CBSE10_SST_28` -> (A): “The most powerful weapon of the Spanish conqueror was not a conventional military weapon at all.” Justify the above statement by giving two reas
- [0.254] `CBSE10_SST_23` -> Mr. Palani is from Tamil Nādu, wishes to cultivate either Tea or Wheat. Which one of the crops out of the two can he cultivate in his state? Substanti
- [0.267] `CBSE10_SST_19` -> The Indian constitution provides three lists to distribute the legislative power. State any two subjects that are included in the union list. In which

## 6. Invented ID Check

- Invented chapter IDs found: 0
- Invented topic IDs found: 0

## 7. Recommendations

*(To be filled after reviewing spot-checks and suspicious mappings above.)*
