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


# Row values the entity productions weave in. Fixed here so enumeration is
# finite; the grammar never sees them as anything but opaque strings.
SLOTS = {"subject": "MV Baltic Trader", "when": "last month", "agent": "Dana Reyes"}


def _expand_all(symbol, depth=0):
    """Every string a symbol can reach. Sampling hides bad pairings; this
    cannot, because it enumerates the lot."""
    if depth > 6:
        return [""]
    if symbol in SLOTS:
        return [SLOTS[symbol]]
    out = []
    for rule in M._REVIEW_RULES.get(symbol, []):
        pat = rule[1] if isinstance(rule, tuple) else rule
        parts = re.split(r"(\{\w+\})", pat)
        pieces = [[p] if not p.startswith("{") else _expand_all(p[1:-1], depth + 1)
                  for p in parts]
        out.extend("".join(c) for c in itertools.product(*pieces))
    return out or [""]


def _sentences(symbol):
    """Every reachable string, as the reader would actually see it."""
    return [M._capitalise_sentences(x) for x in _expand_all(symbol)]


TOPICS = ("ap_quality", "ap_setup", "ap_support", "ap_delivery", "ap_perf",
          "ap_ui", "ap_value", "ap_fit", "ap_named", "an_quality", "an_setup",
          "an_support", "an_delivery", "an_perf", "an_ui", "an_value", "an_fit",
          "an_named", "ap_named_desc", "ap_named_story",
          "an_named_desc", "an_named_story")


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
            for sentence in _sentences(topic):
                assert sentence.endswith((".", "!", "?")), sentence
                assert "  " not in sentence, sentence
                assert sentence[0].isupper(), sentence
                # A tail joined to the wrong verb leaves a stranded participle.
                assert " keeps excellent" not in sentence
                assert " reads as sturdier" not in sentence
                # A plural subject on a singular verb. Shipped once.
                assert " materials feels" not in sentence

    def test_no_clause_is_capitalised_mid_sentence(self):
        """A mixed review joins two aspects with a connector, so a clause that
        capitalises its own first word emits "That said, The quality feels
        flimsy." Every aspect is reachable in both positions, so the only
        place the answer is knowable is after the whole string exists."""
        connector = re.compile(r"(?:That said,|However,|On the other hand,|But|"
                               r"Still,|To be fair,|On the plus side,) (\w+)")
        entity_words = {w for v in SLOTS.values() for w in v.split()}
        for body in ("body_mixed",):
            for sentence in _sentences(body):
                for word in connector.findall(sentence):
                    assert word == "I" or word in entity_words or word.islower(), \
                        f"{word!r} in: {sentence}"


class TestSentimentStillConforms:
    def test_five_star_reviews_never_read_negative(self):
        """The invariant this module exists for. Capacity must not cost it."""
        g = MicrotextGenerator(np.random.default_rng(2))
        rv = [str(x) for x in g.reviews(3_000, ratings=[5] * 3_000)]
        assert sum(detect_sentiment(r) == "negative" for r in rv) == 0


class TestHonestLimit:
    """What entity weaving does and does not buy, in numbers.

    Recombination multiplies SENTENCES, never words: a fixed morpheme pool has
    a Heaps exponent of zero however cleverly it is recombined. Weaving the
    row's own entity into the prose is the only thing here that mints a word,
    so vocabulary tracks the table's entity columns and nothing else. It does
    NOT reach the 0.45-0.60 Heaps exponent of natural English, and it cannot:
    that exponent comes from an open world of proper nouns, numerals and
    misspellings, and a column drawn from a finite universe saturates. Getting
    there would mean minting non-words, which is a worse column than the one
    it replaced. These record both halves so neither gets overclaimed."""

    def test_grammar_alone_has_a_closed_vocabulary(self):
        g = MicrotextGenerator(np.random.default_rng(7))
        toks = {w for t in g.reviews(20_000)
                for w in re.findall(r"[a-z']+", str(t).lower())}
        assert len(toks) < 2_000

    def test_vocabulary_grows_with_the_entity_column(self):
        """The property that is actually claimed: prose word stock is a
        function of the table, not a constant of the grammar."""
        from misata.lexicon import Lexicon, get_spec

        g = MicrotextGenerator(np.random.default_rng(7))
        names = [str(x) for x in
                 Lexicon(get_spec("vessel_name"), np.random.default_rng(2)).draw(20_000)]
        with_ctx = {w for t in g.reviews(20_000, context={"subject": names})
                    for w in re.findall(r"[a-z']+", str(t).lower())}
        without = {w for t in MicrotextGenerator(np.random.default_rng(7)).reviews(20_000)
                   for w in re.findall(r"[a-z']+", str(t).lower())}
        assert len(with_ctx) > len(without)
