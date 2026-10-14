# Similar-topic checker

When a student submits a topic, the platform compares it with every archived project and lists the closest ones as a warning. The same list appears on each repository detail page. It never blocks anything.

Code: `projecthub_slice1/apps/projects/services/similarity.py`. Tests: `SimilarityScoreTests` and `SimilarTopicPagesTests` in `projecthub_slice1/apps/projects/tests.py`. Setting: `SIMILARITY_THRESHOLD` in `projecthub_slice1/config/settings.py`, default `0.35`.

## The formula

Each text is the project's **title + abstract** (the `description` field) joined together. It is turned into a set of words in five steps (`tokens()`):

1. **Lowercase** the text.
2. **Strip punctuation and tokenise:** keep runs of letters and digits (`[a-z0-9]+`). Everything else is a word break, so `check-in` becomes `check` and `in`.
3. **Drop stop-words:** a fixed list of 126 common English words such as *a, the, for, and, to, in, that*.
4. **Strip suffixes** (`stem()`): a plural and then an *-ing* ending.
   - *-ies* becomes *-y* (studies → study).
   - A final *s* is dropped (seats → seat), unless the word ends in *ss*, *us* or *is* (class, bus, analysis stay as they are).
   - *-ing* is dropped (seating → seat) only when at least three letters including a vowel remain, so *string* and *thing* stay. A doubled last letter is undone (running → run).
5. **Keep each word once:** it is a set, so repeats do not count.

The score of two texts with word sets A and B is the **Jaccard index**:

```
J(A, B) = |A ∩ B| / |A ∪ B|
        = words in both / words in either
```

- 1.0 means the same set of words; 0.0 means no word in common.
- If both sets are empty (empty text, or only stop-words), the score is defined as 0.0 to avoid dividing by zero.

An archived project is listed when `J ≥ SIMILARITY_THRESHOLD`. At most five are shown: highest score first, then the newer year, then title order.

## Worked example 1: a real match in the demo

From `seed_demo`: **"Campus Shuttle Delay Tracker"** (a running topic) and **"Campus Shuttle Tracker"** (archived in 2024).

| | Title + abstract | Word set after cleaning |
|---|---|---|
| A | Campus Shuttle Delay Tracker. *A student-facing tool for reporting and reviewing campus shuttle delays.* | campus, delay, fac, report, review, shuttle, student, tool, tracker (**9**) |
| B | Campus Shuttle Tracker. *A tool for tracking campus shuttle delays and reporting them to students.* | campus, delay, report, shuttle, student, tool, track, tracker (**8**) |

- *delay* and *delays* become one word.
- *reporting* matches *reporting*; *students* matches *student*.
- *tracking* becomes *track*, which is not the same word as *tracker*.
- A ∩ B = {campus, delay, report, shuttle, student, tool, tracker} → **7**.
- A ∪ B = 9 + 8 − 7 = **10**.
- **J = 7 / 10 = 0.70**, above 0.35, so the archived project is listed on the running topic's page and would warn a student proposing it.

## Worked example 2: two unrelated demo projects

**"Campus Shuttle Delay Tracker"** (A above) and **"Student Wellbeing Check-in Chatbot"**, whose abstract is *"A chatbot that offers weekly wellbeing check-ins and points students to campus support."*

- B's word set is: campus, chatbot, check, ins, offer, point, student, support, weekly, wellbe (**10**).
- A ∩ B = {campus, student} → **2**.
- A ∪ B = 9 + 10 − 2 = **17**.
- **J = 2 / 17 = 0.118**, so it is not listed. They share only the setting (a campus, students), not the problem.

## Before and after suffix stripping

The first version had no step 4. The table below re-scores the same texts with and without it; the threshold stays 0.35.

| Comparison | Without stripping | With stripping |
|---|---|---|
| "Exam Seat Allocation for Lecture Halls" Versus archived "Exam Seating Allocation Tool" (title + abstract) | 3/13 = 0.231 (not listed) | 4/11 = 0.364 (**listed**) |
| "Exam Seat Allocation" Versus "Exam Seating Allocation" (titles only) | 0.500 | 1.000 |
| Campus Shuttle Delay Tracker versus Campus Shuttle Tracker | 0.500 | 0.700 |
| Campus Shuttle Delay Tracker versus Student Wellbeing Check-in Chatbot | 0.105 | 0.118 |

Across all 210 pairs of the 21 demo projects (the original 190 pairs plus the 20 that involve the new archived project):

| | Without | With |
|---|---|---|
| Pairs whose score changed | — | 67, all upward; none went down |
| Pairs with any shared word | 50 | 71 |
| Highest score | 0.500 | 0.700 (the shuttle pair) |
| Pairs at or above 0.35 | 1 | 1 (the shuttle pair) |
| Highest among the original 190 | 0.105 | 0.188 |

Suffix stripping can only merge words, never split them, so a score can only stay the same or rise. Unrelated demo topics stay far below the threshold (next highest 0.20).

## What it does not do (limits to state at the defence)

- **The stripping is crude.** *scheduling* becomes *schedul*, which does not match *schedule*; *wellbeing* becomes *wellbe*; *news* becomes *new*; *processes* becomes *processe*. It is a deliberately small rule set, not a full stemmer such as Porter's.
- **No synonyms or meaning.** "Timetable clash" and "schedule conflict" share no words and score 0.
- **Short texts swing a lot.** One shared word out of four is already 0.25, so a title-only topic with no abstract can score high on one common word such as "student".
- **Domain words are not stop-words.** Words like *system, app, student, campus* are kept, because removing them would be a judgement about the topic, not about English.
- **Cost.** Each check reads every archived project's title and abstract and compares them in Python. That is fine for a department-sized archive (hundreds to a few thousand rows). A much larger archive would need precomputed word sets or a search index.

These are the reasons the checker is a warning only. The supervisor, not the score, decides whether a topic overlaps too much.

## Where it shows

| Page | Who | When |
|---|---|---|
| Message after "Start project" or a proposal submission | Student | Only if at least one match; the topic is saved first (`apps/projects/views.py`, `_warn_about_similar_topics`) |
| "Similar past projects" panel on the workflow page | Student | While the project is at the proposal stage |
| "Similar past projects" panel on repository detail pages | Anyone who can open the page | Current projects and archived projects (an archived project is never matched with itself) |
