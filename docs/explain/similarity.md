# Similar-topic checker

When a student submits a topic, the platform compares it with every archived project and lists the closest ones as a warning. The same list appears on each repository detail page. It never blocks anything.

Code: `projecthub_slice1/apps/projects/services/similarity.py`. Tests: `SimilarityScoreTests` and `SimilarTopicPagesTests` in `projecthub_slice1/apps/projects/tests.py`. Setting: `SIMILARITY_THRESHOLD` in `projecthub_slice1/config/settings.py`, default `0.35`.

## The formula

Each text is the project's **title + abstract** (the `description` field) joined together. It is turned into a set of words in four steps (`tokens()`):

1. **Lowercase** the text.
2. **Strip punctuation and tokenise:** keep runs of letters and digits (`[a-z0-9]+`). Everything else is a word break, so `check-in` becomes `check` and `in`.
3. **Drop stop-words:** a fixed list of 126 common English words such as *a, the, for, and, to, in, that*.
4. **Keep each word once:** it is a set, so repeats do not count.

The score of two texts with word sets A and B is the **Jaccard index**:

```
J(A, B) = |A ∩ B| / |A ∪ B|
        = words in both / words in either
```

- 1.0 means the same set of words; 0.0 means no word in common.
- If both sets are empty (empty text, or only stop-words), the score is defined as 0.0 to avoid dividing by zero.

An archived project is listed when `J ≥ SIMILARITY_THRESHOLD`. At most five are shown: highest score first, then the newer year, then title order.

## Worked example with two real demo projects

From `seed_demo`: **"Campus Shuttle Delay Tracker"** (a running topic) and **"Student Wellbeing Check-in Chatbot"** (an archived project).

| | Title + abstract | Word set after cleaning |
|---|---|---|
| A | Campus Shuttle Delay Tracker. *A student-facing tool for reporting and reviewing campus shuttle delays.* | campus, delay, delays, facing, reporting, reviewing, shuttle, student, tool, tracker (**10**) |
| B | Student Wellbeing Check-in Chatbot. *A chatbot that offers weekly wellbeing check-ins and points students to campus support.* | campus, chatbot, check, ins, offers, points, student, students, support, weekly, wellbeing (**11**) |

- Removed as stop-words: *a, for, and* (A); *a, that, and, to, in* (B).
- `campus` and `shuttle` (A) and `chatbot` and `wellbeing` (B) appear twice in their texts but count once.
- A ∩ B = {campus, student} → **2** words.
- A ∪ B = 10 + 11 − 2 = **19** words.
- **J = 2 / 19 = 0.105.**

0.105 is below 0.35, so the chatbot is **not** listed as similar to the shuttle tracker, which is the right answer: they share only the setting (a campus, students), not the problem.

This is the highest-scoring pair among all 20 demo topics (190 pairs checked). The demo topics were written to be distinct, so with the default threshold every demo page shows "No archived project scores 0.35 or higher".

## What it does not do (limits to state at the defence)

- **No stemming.** `seat`, `seats` and `seating` are three different words, as are `delay`/`delays` above. A student proposing "Exam Seat Allocation for Lecture Halls" scores only **3 / 13 = 0.23** against the archived "Exam Seating Allocation Tool". It is the same idea but falls below the threshold.
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
