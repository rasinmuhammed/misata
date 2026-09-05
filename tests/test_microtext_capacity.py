"""Prose capacity, and the honest limit of recombination.

Aspect sentences used to be whole hand-written strings, twenty-two of them,
which is why the 5-star grammar reached 3,816 distinct reviews against a
docstring claiming tens of thousands, and why half of any twenty thousand
reviews were byte-identical to another one.

Composing within a topic fixes that. It does NOT fix vocabulary growth, and
these tests record both facts so neither gets overclaimed later.
"""
import itertools
import re

import numpy as np
import pytest

import misata.microtext as M
from misata.microtext import MicrotextGenerator, detect_sentiment


def _expand_all(symbol, depth=0):
    """Every string a symbol can reach. Sampling hides bad pairings; this
    cannot, because it enumerates the lot."""
    if depth > 6:
        return [""]
    out = []
    for rule in M._REVIEW_RULES.get(symbol, []):
        pat = rule[1] if isinstance(rule, tuple) else rule
        parts = re.split(r"(\{\w+\})", pat)
        pieces = [[p] if not p.startswith("{") else _expand_all(p[1:-1], depth + 1)
                  for p in parts]
        out.extend("".join(c) for c in itertools.product(*pieces))
    return out or [""]


TOPICS = ("ap_quality", "ap_setup", "ap_support", "ap_delivery", "ap_perf",
          "ap_ui", "ap_value", "ap_fit", "an_quality", "an_setup", "an_support",
          "an_delivery", "an_perf", "an_ui", "an_value", "an_fit")


class TestCapacity:
    def test_aspect_sentences_number_in_the_hundreds_not_the_dozens(self):
        assert sum(len(_expand_all(t)) for t in TOPICS) > 800

    def test_five_star_reviews_reach_six_figures(self):
        g = MicrotextGenerator(np.random.default_rng(1))
        seen = set(str(x) for x in g.reviews(120_000, ratings=[5] * 120_000))
        assert len(seen) > 50_000

    def test_duplicate_rate_is_low_at_a_realistic_table_size(self):
        g = MicrotextGenerator(np.random.default_rng(7))
        rv = [str(x) for x in g.reviews(20_000)]
        assert 1 - len(set(rv)) / len(rv) < 0.10


class TestNoUngrammaticalPairing:
    def test_every_reachable_sentence_is_well_formed(self):
        """Slots are drawn independently, so a pool is only as good as its
        worst pairing. 'Speed keeps excellent so far' shipped once."""
        for topic in TOPICS:
            for sentence in _expand_all(topic):
                assert sentence.endswith((".", "!", "?")), sentence
                assert "  " not in sentence, sentence
                assert sentence[0].isupper() or sentence.startswith("It "), sentence
                # A tail joined to the wrong verb leaves a stranded participle.
                assert " keeps excellent" not in sentence
                assert " reads as sturdier" not in sentence


class TestSentimentStillConforms:
    def test_five_star_reviews_never_read_negative(self):
        """The invariant this module exists for. Capacity must not cost it."""
        g = MicrotextGenerator(np.random.default_rng(2))
        rv = [str(x) for x in g.reviews(3_000, ratings=[5] * 3_000)]
        assert sum(detect_sentiment(r) == "negative" for r in rv) == 0


class TestHonestLimit:
    def test_word_vocabulary_is_still_closed(self):
        """Recombination multiplies SENTENCES, never words. A fixed morpheme
        pool has a Heaps exponent of zero however cleverly it is recombined,
        so prose vocabulary growth needs genuinely open tokens (entity names,
        amounts, dates) rather than a bigger grammar. Recorded so the next
        person does not claim otherwise from the duplicate rate alone."""
        g = MicrotextGenerator(np.random.default_rng(7))
        toks = {w for t in g.reviews(20_000)
                for w in re.findall(r"[a-z']+", str(t).lower())}
        assert len(toks) < 2_000
