"""Similar-topic checker: compare a topic with the archived projects by shared words.

The score is the Jaccard index of two word sets, J = |A ∩ B| / |A ∪ B|, where each set holds the
words of a title plus its abstract after lowercasing, removing punctuation and dropping common
English stop-words. 1.0 means the same words, 0.0 means none in common. It is a warning aid for
students and supervisors, never a rule: nothing is blocked because of a score.
See docs/explain/similarity.md for the formula and a worked example.
"""

import re

from django.conf import settings

from ..models import ArchivedProject

DEFAULT_THRESHOLD = 0.35
MATCH_LIMIT = 5

STOP_WORDS = frozenset("""
a about above after again against all also am an and any are as at be because been before being
below between both but by can could did do does doing down during each few for from further had
has have having he her here hers herself him himself his how i if in into is it its itself just
me more most my myself no nor not of off on once only or other our ours ourselves out over own
same she should so some such than that the their theirs them themselves then there these they
this those through to too under until up very was we were what when where which while who whom
why will with would you your yours yourself yourselves
""".split())

WORD = re.compile(r"[a-z0-9]+")


def tokens(text):
    """The set of meaningful words in text: lowercased, punctuation removed, stop-words dropped."""
    return {word for word in WORD.findall((text or "").lower()) if word not in STOP_WORDS}


def jaccard(a_tokens, b_tokens):
    union = a_tokens | b_tokens
    if not union:
        return 0.0  # two empty texts share nothing worth reporting
    return len(a_tokens & b_tokens) / len(union)


def similarity(a, b):
    """Jaccard similarity of two texts, from 0.0 (no shared words) to 1.0 (same words)."""
    return jaccard(tokens(a), tokens(b))


def similarity_threshold():
    return getattr(settings, "SIMILARITY_THRESHOLD", DEFAULT_THRESHOLD)


def similar_archived_projects(title, abstract="", *, exclude_id=None, limit=MATCH_LIMIT):
    """Archived projects scoring at or above the threshold, best first, at most `limit`.

    Returns a list of dicts with id, title, year and score. Every archived project is compared in
    Python; that is fine for a department-sized archive (hundreds to a few thousand rows).
    """
    topic = tokens(f"{title} {abstract}")
    if not topic:
        return []
    threshold = similarity_threshold()
    rows = ArchivedProject.objects.values_list("id", "title", "description", "year")
    if exclude_id is not None:
        rows = rows.exclude(pk=exclude_id)
    matches = []
    for pk, other_title, other_abstract, year in rows:
        score = jaccard(topic, tokens(f"{other_title} {other_abstract}"))
        if score >= threshold:
            matches.append({"id": pk, "title": other_title, "year": year, "score": score})
    matches.sort(key=lambda match: (-match["score"], -match["year"], match["title"]))
    return matches[:limit]
