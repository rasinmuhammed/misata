"""
Seeded grammar-based microtext: human-looking short text without an LLM.

Free-text columns (reviews, comments, notes) are where synthetic data gives
itself away fastest — lorem ipsum, or six templates repeating every twenty
rows, or a five-star review that says "disappointing". This module replaces
flat template pools with a small weighted recursive grammar (a PCFG):

    review_5 → "{opener_5} {body} {closer_5}"
    body     → "{aspect_pos}" | "{aspect_pos} {aspect_pos_2}"
    ...

Each sentiment level composes opener × aspects × detail × closer, giving
tens of thousands of distinct surface strings per level instead of single
digits — and every expansion is driven by one seeded RNG, so output is
reproducible.

The headline property is **sentiment conformance**: review text is
generated FROM the row's rating. A 1-star review reads angry, a 5-star
review reads delighted, 3 stars reads mixed — an invariant the Oracle layer
can verify with a lexicon check, and one that imitation-based synthesisers
do not guarantee.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Union

import numpy as np


_SENTENCE_START = re.compile(r"(^|[.!?]\s+)([a-z])")


def _capitalise_sentences(text: str) -> str:
    """Capitalise whatever ended up starting a sentence.

    Clause rules store their first word lowercase, because whether a clause
    begins a sentence depends on the template that placed it: "the quality
    feels flimsy" opens a review in one expansion and follows "That said," in
    another. Deciding here, once, after the whole string exists, is the only
    place the answer is actually known. The pass never lowercases, so entity
    names and hand-written full sentences pass through untouched.
    """
    out = _SENTENCE_START.sub(lambda m: m.group(1) + m.group(2).upper(), text)
    # "i ordered" is the one word that is capital wherever it stands.
    return re.sub(r"\bi\b(?=\s)", "I", out)


Rule = Union[str, tuple]  # plain template, or (weight, template)


class Grammar:
    """Tiny seeded recursive template grammar.

    ``rules`` maps a symbol to a list of templates. ``{placeholders}`` in a
    template are expanded recursively when they name another rule; unknown
    placeholders raise (typos in grammars should fail loudly, not leak
    braces into output). Templates may carry weights: ``(3, "...")``.
    """

    _PLACEHOLDER = re.compile(r"\{([a-z0-9_]+)\}")
    MAX_DEPTH = 12

    def __init__(self, rules: Dict[str, List[Rule]], rng: np.random.Generator,
                 capitalise: bool = False):
        self.rng = rng
        # Off by default: capitalisation is a property of the grammar that
        # asked for it, not of every caller of this class.
        self.capitalise = capitalise
        self._templates: Dict[str, List[str]] = {}
        self._weights: Dict[str, np.ndarray] = {}
        for symbol, options in rules.items():
            templates, weights = [], []
            for option in options:
                if isinstance(option, tuple):
                    weight, template = option
                else:
                    weight, template = 1.0, option
                templates.append(template)
                weights.append(float(weight))
            w = np.array(weights)
            self._templates[symbol] = templates
            self._weights[symbol] = w / w.sum()

    def expand(self, symbol: str, _depth: int = 0, **slots: str) -> str:
        if _depth > self.MAX_DEPTH:
            raise RecursionError(f"grammar too deep at '{symbol}'")
        idx = self.rng.choice(len(self._templates[symbol]), p=self._weights[symbol])
        template = self._templates[symbol][idx]

        def _fill(match: re.Match) -> str:
            name = match.group(1)
            if name in slots:
                return str(slots[name])
            if name in self._templates:
                return self.expand(name, _depth + 1, **slots)
            raise KeyError(f"grammar symbol or slot '{name}' is not defined")

        filled = self._PLACEHOLDER.sub(_fill, template)
        if self.capitalise and _depth == 0:
            return _capitalise_sentences(filled)
        return filled


# ---------------------------------------------------------------------------
# Review grammar — one sub-grammar per star rating
# ---------------------------------------------------------------------------

_REVIEW_RULES: Dict[str, List[Rule]] = {
    # ── star-level entry points ──
    "review_5": [
        "{opener_5} {body_pos} {closer_5}",
        "{opener_5} {body_pos}",
        (0.5, "{body_pos} {closer_5}"),
    ],
    "review_4": [
        "{opener_4} {body_pos} {nit}",
        "{opener_4} {body_pos} {closer_4}",
        (0.5, "{body_pos} {nit} {closer_4}"),
    ],
    "review_3": [
        "{opener_3} {body_mixed}",
        "{body_mixed} {closer_3}",
        "{opener_3} {body_mixed} {closer_3}",
    ],
    "review_2": [
        "{opener_2} {body_neg} {closer_2}",
        "{opener_2} {body_neg}",
        (0.5, "{body_neg} {closer_2}"),
    ],
    "review_1": [
        "{opener_1} {body_neg} {closer_1}",
        "{opener_1} {body_neg_strong} {closer_1}",
        "{body_neg_strong} {closer_1}",
    ],
    # ── bodies: one or two aspect sentences ──
    "body_pos": ["{aspect_pos}", (1.5, "{aspect_pos} {aspect_pos2}")],
    "body_mixed": ["{aspect_pos_c} {but} {aspect_neg_c}",
                   "{aspect_neg_c} {but_pos} {aspect_pos_c}"],
    "body_neg": ["{aspect_neg}", (1.5, "{aspect_neg} {aspect_neg2}")],
    "body_neg_strong": ["{aspect_neg} {aspect_neg2} {escalation}"],
    # ── openers ──
    "opener_5": [
        "Absolutely loved it!", "Couldn't be happier.", "Exceeded every expectation.",
        "This is exactly what I was looking for.", "Five stars, no hesitation.",
        "Honestly blown away.", "Best purchase I've made in a while.",
        "I rarely write reviews, but this earned one.",
    ],
    "opener_4": [
        "Really solid overall.", "Very happy with this.", "Works great.",
        "Good experience from start to finish.", "Impressed for the price.",
        "Almost perfect.", "Does what it promises.",
    ],
    "opener_3": [
        "It's okay.", "Mixed feelings on this one.", "Decent, but not great.",
        "Somewhere in the middle.", "Fine for the price, I guess.",
    ],
    "opener_2": [
        "Disappointing.", "Expected better.", "Not impressed.",
        "Wouldn't buy again.", "Below average, sadly.",
    ],
    "opener_1": [
        "Terrible experience.", "Complete waste of money.", "Avoid this.",
        "One star is generous.", "Extremely frustrated.",
    ],
    # ── aspects ──
    # Aspects compose within a topic rather than being whole hand-written
    # sentences. A flat list of twelve sentences is why the 5-star grammar
    # reached 3,816 distinct strings against a docstring claiming tens of
    # thousands, and why vocabulary stopped growing at 285 words. Subject and
    # predicate are drawn from the same topic so they always agree.
    "aspect_pos": [
        "{ap_quality}", "{ap_setup}", "{ap_support}", "{ap_delivery}",
        "{ap_perf}", "{ap_ui}", "{ap_value}", "{ap_fit}", (9.0, "{ap_named}"),
    ],
    "aspect_pos_c": [
        "{ap_quality}", "{ap_setup}", "{ap_support}", "{ap_delivery}",
        "{ap_perf}", "{ap_ui}", "{ap_value}", "{ap_fit}", (6.0, "{ap_named_desc}"),
    ],
    "ap_quality": ["the {n_quality} {v_seems} {t_quality_pos}"],
    "n_quality": ["quality", "build", "finish", "construction",
                  "casing", "stitching", "hardware", "packaging"],
    "v_seems": ["feels", "seems", "looks", "comes across as"],
    "t_quality_pos": ["genuinely premium.", "solid and well made.",
                      "a clear step above the price.", "sturdier than I expected.",
                      "built to last.", "far better than the photos suggest."],
    "ap_setup": ["{n_setup} {v_took} {t_setup_pos}"],
    "n_setup": ["setup", "installation", "getting started", "the first run",
                "onboarding", "unboxing to working"],
    "v_took": ["took", "needed", "was done in", "wrapped up in"],
    "t_setup_pos": ["under five minutes.", "about ten minutes, start to finish.",
                    "one evening and no swearing.", "less time than the manual claims.",
                    "barely any effort."],
    "ap_support": ["{n_support} {v_replied} {t_support_pos}"],
    "n_support": ["customer service", "support", "the team", "their help desk"],
    "v_replied": ["replied", "got back to me", "answered", "followed up"],
    "t_support_pos": ["within the hour.", "the same day, and actually solved it.",
                      "quickly and without a script.", "before I had to chase them.",
                      "with a real answer, not a template."],
    "ap_delivery": ["{n_delivery} {v_arrived} {t_delivery_pos}"],
    "n_delivery": ["delivery", "shipping", "the parcel", "the order"],
    "v_arrived": ["arrived", "turned up", "landed", "showed up"],
    "t_delivery_pos": ["two days early, well packaged.", "on time and undamaged.",
                       "faster than the estimate.", "properly boxed, no dents."],
    "ap_perf": ["{n_perf} {v_runs} {t_perf_pos}"],
    "n_perf": ["performance", "battery life", "speed", "throughput",
               "responsiveness", "range"],
    "v_runs": ["has been", "stays", "remains"],
    "t_perf_pos": ["excellent so far.", "smooth even under heavy use.",
                   "steady all week.", "consistent under load.",
                   "strong after months of daily use."],
    "ap_ui": ["the {n_ui} {v_is} {t_ui_pos}"],
    "n_ui": ["interface", "app", "dashboard", "layout", "menu", "controls"],
    "v_is": ["is", "stays", "feels"],
    "t_ui_pos": ["clean and intuitive.", "obvious without a manual.",
                 "quick to learn.", "uncluttered.", "well thought through."],
    "ap_value": ["the {n_price} {v_is_price} {t_value_pos}"],
    "n_price": ["price", "cost", "pricing"],
    "t_value_pos": ["more than fair for what you get.", "honest.",
                    "the reason I would buy again.", "well below what I expected to pay."],
    # Entity-bearing aspects. `subject` carries the row's own value, so the
    # word stock grows with the table rather than being capped by the grammar.
    # Split descriptive from narrative. A description of the subject contrasts
    # cleanly against another aspect; a first-person story does not, and a
    # mixed review that draws two of them says it returned the thing and also
    # never looked back. Only the descriptive half is reachable from a
    # contrastive body.
    # No article, either: "the" is correct before a product and wrong before a
    # company, and the grammar cannot tell which the column holds.
    "ap_named": [(3.0, "{ap_named_desc}"), (2.0, "{ap_named_story}")],
    "ap_named_desc": ["{subject} {v_seems} {t_quality_pos}",
                      "{subject} {v_runs} {t_perf_pos}"],
    "ap_named_story": ["i tried {subject} {when} and it {v_works} {t_fit_pos}",
                       "{agent} on support sorted it {when} without any fuss.",
                       "i came back to {subject} {when} and have not regretted it."],
    "an_named": [(3.0, "{an_named_desc}"), (2.0, "{an_named_story}")],
    "an_named_desc": ["{subject} {v_seems} {t_quality_neg}",
                      "{subject} {v_drops} {t_perf_neg}"],
    "an_named_story": ["i tried {subject} {when} and it {v_fails} {t_fit_neg}",
                       "{agent} on support promised a callback {when} that never came.",
                       "i gave up on {subject} {when} and switched to something else."],
    "ap_fit": ["it {v_works} {t_fit_pos}"],
    "v_works": ["works", "performs", "fits", "runs"],
    "t_fit_pos": ["exactly as described.",
                  "with everything I already use.",
                  "the way the listing promised.",
                  "without a single surprise."],
    "aspect_pos2": [
        "Support replied within the hour when I had a question.",
        "Even the packaging was thoughtfully done.",
        "My whole team has switched over since.",
        "Months in, it still works like day one.",
        "The little details show real care.",
    ],
    "aspect_neg": [
        "{an_quality}", "{an_setup}", "{an_support}", "{an_delivery}",
        "{an_perf}", "{an_ui}", "{an_value}", "{an_fit}", (9.0, "{an_named}"),
    ],
    # Deliberately carries no named production: body_mixed reaches this and
    # aspect_pos_c in the same expansion, and two independent draws that both
    # name the subject produce "X feels nothing like the photos. To be fair, X
    # feels genuinely premium." One side names it; the contrast is real.
    "aspect_neg_c": [
        "{an_quality}", "{an_setup}", "{an_support}", "{an_delivery}",
        "{an_perf}", "{an_ui}", "{an_value}", "{an_fit}",
    ],
    "an_quality": ["the {n_quality} {v_seems} {t_quality_neg}"],
    "t_quality_neg": ["much cheaper than advertised.", "flimsy in the hand.",
                      "nothing like the photos.", "rushed.",
                      "a downgrade on the previous version."],
    "an_setup": ["{n_setup} {v_was} {t_setup_neg}"],
    "v_was": ["was", "turned into", "ended up being"],
    "t_setup_neg": ["confusing, and the docs did not help.",
                    "an afternoon I will not get back.",
                    "three attempts and a support ticket.",
                    "far harder than it needed to be."],
    "an_support": ["{n_support} {v_took_time} {t_support_neg}"],
    "v_took_time": ["took", "needed", "went"],
    "t_support_neg": ["a week to respond.", "four emails to reach a human.",
                      "silent after the first reply.",
                      "two weeks and still no resolution."],
    "an_delivery": ["{n_delivery} {v_was} {t_delivery_neg}"],
    "t_delivery_neg": ["late and the box arrived damaged.",
                       "a fortnight past the estimate.",
                       "left in the rain with no notice.",
                       "split open on arrival."],
    "an_perf": ["{n_perf} {v_drops} {t_perf_neg}"],
    "v_drops": ["drops off", "degrades", "falls away", "collapses"],
    "t_perf_neg": ["far faster than claimed.", "after about a week.",
                   "the moment you actually load it.",
                   "under any real workload."],
    "an_ui": ["the {n_ui} {v_is} {t_ui_neg}"],
    "t_ui_neg": ["clunky and slow.", "buried three menus deep.",
                 "clearly never user-tested.", "a maze."],
    "an_value": ["the {n_price} {v_is_price} {t_value_neg}"],
    "v_is_price": ["is", "feels", "seems"],
    "t_value_neg": ["hard to justify for what you get.",
                    "well above what this is worth.",
                    "the main reason I would not repeat it."],
    "an_fit": ["it {v_fails} {t_fit_neg}"],
    "v_fails": ["stopped working", "gave up", "started failing"],
    "t_fit_neg": ["properly after a few days.",
                  "on the one feature I bought it for.",
                  "within a week of ordinary use.",
                  "the moment I relied on it."],
    "aspect_neg2": [
        "Returning it was its own ordeal.",
        "No response to two support emails.",
        "The replacement had the same problem.",
        "Photos online are nothing like the real thing.",
        "I ended up buying a different brand.",
    ],
    "escalation": [
        "I've asked for a refund.", "Reporting this to the marketplace.",
        "Save your money.", "Still waiting on a resolution.",
    ],
    # ── connectors, nits, closers ──
    "but": ["That said,", "However,", "On the other hand,", "But"],
    "but_pos": ["Still,", "To be fair,", "On the plus side,"],
    "nit": [
        "Only minor gripe is the packaging.",
        "Wish the manual was clearer, but that's minor.",
        "Slightly slow shipping, though that's not the product's fault.",
        "A second color option would be nice.",
        "Docking one star for the setup process.",
    ],
    "closer_5": [
        "Highly recommend.", "Will definitely buy again.", "Worth every penny.",
        "Already recommended it to friends.", "10/10.",
    ],
    "closer_4": [
        "Recommended.", "Would buy again.", "Good value overall.",
        "Happy with the purchase.",
    ],
    "closer_3": [
        "Might give it another try.", "Your mileage may vary.",
        "There are probably better options.", "Not bad, not great.",
    ],
    "closer_2": [
        "Hard to recommend.", "Look elsewhere first.", "Expected more at this price.",
    ],
    "closer_1": [
        "Do not recommend.", "Never again.", "Buyer beware.",
    ],
}

_TITLE_RULES: Dict[str, List[Rule]] = {
    "title_5": [
        "Outstanding in every way", "Exceeded all expectations", "Absolutely loved it",
        "Best purchase this year", "Five stars, easily", "A hidden gem",
        "Perfect from start to finish", "Couldn't ask for more",
    ],
    "title_4": [
        "Really solid choice", "Great value for money", "Very happy with it",
        "Works great, minor quibbles", "Almost perfect", "Would buy again",
    ],
    "title_3": [
        "Decent but could be better", "Average at best", "Mixed feelings",
        "Good but not great", "A little overrated", "Middle of the road",
    ],
    "title_2": [
        "Disappointing — expected more", "Not worth the price", "Below average",
        "Wouldn't buy again", "Falls short",
    ],
    "title_1": [
        "Complete waste of money", "Avoid this one", "Terrible experience",
        "Nothing like the listing", "One star is generous",
    ],
}

# ---------------------------------------------------------------------------
# Generic business note grammar — replaces the lorem ipsum fallback
# ---------------------------------------------------------------------------

_NOTE_RULES: Dict[str, List[Rule]] = {
    "note": [
        "{actor} {action} {timeframe}.",
        "{actor} {action}; {follow_up}.",
        "{action_cap} {timeframe}. {follow_up_cap}.",
        (0.6, "{actor} {action}."),
    ],
    "actor": [
        "Customer", "Client", "The team", "Account manager", "Support",
        "The vendor", "Requester", "Stakeholder",
    ],
    "action": [
        "requested a follow-up call", "confirmed the updated details",
        "raised a question about billing", "approved the proposed changes",
        "asked to reschedule the next review", "flagged a discrepancy in the records",
        "submitted the remaining documents", "requested expedited processing",
        "confirmed receipt of the shipment", "asked for clarification on terms",
        "escalated the open issue", "completed the onboarding steps",
    ],
    "action_cap": [
        "Follow-up scheduled", "Documents received and verified",
        "Issue resolved and closed", "Pending review by the billing team",
        "Awaiting confirmation from the client", "Records updated",
    ],
    "timeframe": [
        "earlier today", "yesterday afternoon", "last week", "this morning",
        "on the last call", "during onboarding", "after the latest update",
    ],
    "follow_up": [
        "will follow up next week", "no further action needed",
        "needs review before Friday", "details logged in the account history",
        "second reminder sent", "awaiting response",
    ],
}
# Sentence-initial variants of follow_up for use after a full stop.
_NOTE_RULES["follow_up_cap"] = [
    s[0].upper() + s[1:] for s in _NOTE_RULES["follow_up"]  # type: ignore[index, union-attr]
]

_COMMENT_RULES: Dict[str, List[Rule]] = {
    "comment": [
        "{reaction} {elaboration}",
        "{reaction}",
        (0.7, "{question}"),
        (0.5, "{reaction} {question}"),
    ],
    "reaction": [
        "This is great!", "Love this.", "So true.", "Couldn't agree more.",
        "Interesting take.", "Well said.", "This made my day.", "Saving this for later.",
        "Not sure I agree, but well argued.", "Came here to say exactly this.",
    ],
    "elaboration": [
        "Sharing with my team.", "Exactly what I needed today.",
        "The second point especially.", "More people need to see this.",
        "Been saying this for years.",
    ],
    "question": [
        "Anyone tried this themselves?", "Is there a longer write-up anywhere?",
        "How does this compare to the usual approach?", "What's the source on this?",
        "Does this hold up at scale?",
    ],
}


class MicrotextGenerator:
    """Seeded, grammar-backed short-text generation.

    All methods are vectorised over ``size`` and reproducible under the
    provided RNG.
    """

    def __init__(self, rng: Optional[np.random.Generator] = None):
        self.rng = rng or np.random.default_rng(42)
        self._review = Grammar(_REVIEW_RULES, self.rng, capitalise=True)
        self._title = Grammar(_TITLE_RULES, self.rng)
        self._note = Grammar(_NOTE_RULES, self.rng)
        self._comment = Grammar(_COMMENT_RULES, self.rng)

    # ── ratings → sentiment levels ──

    @staticmethod
    def normalize_ratings(ratings: Sequence, size: int, rng: np.random.Generator) -> np.ndarray:
        """Coerce a rating-ish column to integer star levels 1–5.

        Handles floats, 0–10 scales (halved), and missing values (drawn from
        a J-shaped marginal — real review sites skew heavily positive)."""
        if ratings is None:
            return rng.choice([1, 2, 3, 4, 5], size=size, p=[0.06, 0.07, 0.12, 0.25, 0.50])
        arr = np.asarray(ratings, dtype=float)[:size]
        finite = np.isfinite(arr)
        if finite.any() and np.nanmax(arr[finite]) > 5.0:
            arr = arr / 2.0
        arr = np.clip(np.round(arr), 1, 5)
        # fill missing with the positive-skewed marginal
        n_missing = int((~np.isfinite(arr)).sum())
        if n_missing:
            arr[~np.isfinite(arr)] = rng.choice(
                [1, 2, 3, 4, 5], size=n_missing, p=[0.06, 0.07, 0.12, 0.25, 0.50]
            )
        return arr.astype(int)

    # Fallbacks so an entity production still reads correctly when the caller
    # has no row context to give it. Prose must never depend on plumbing.
    _GENERIC_SUBJECT = ("unit", "item", "product", "model", "order")
    _GENERIC_WHEN = ("last month", "back in the spring", "a few weeks ago",
                     "over the summer", "just before Christmas", "in the new year")
    _GENERIC_AGENT = ("The advisor", "The rep", "Someone", "The agent")

    def reviews(self, size: int, ratings: Optional[Sequence] = None,
                context: Optional[Dict[str, Sequence]] = None) -> np.ndarray:
        """Reviews whose sentiment follows the rating.

        Args:
            size: How many.
            ratings: Star levels the text must agree with.
            context: Optional per-row values woven into the prose, e.g.
                ``{"subject": product_names}``. This is the only source of OPEN
                vocabulary here: recombining a fixed morpheme pool multiplies
                sentences but never mints a new word, so the Heaps exponent
                stays at zero however large a grammar grows. A row's own entity
                name does mint one, and it also ties the review to the row it
                belongs to rather than leaving it floating free.
        """
        levels = self.normalize_ratings(ratings, size, self.rng)
        subjects = self._slot_series(context, "subject", size, self._GENERIC_SUBJECT)
        whens = self._slot_series(context, "when", size, self._GENERIC_WHEN)
        agents = self._slot_series(context, "agent", size, self._GENERIC_AGENT)
        return np.array(
            [self._review.expand(f"review_{lvl}", subject=subjects[i],
                                 when=whens[i], agent=agents[i])
             for i, lvl in enumerate(levels)], dtype=object)

    def _slot_series(self, context: Optional[Dict[str, Sequence]], key: str,
                     size: int, fallback: Sequence[str]) -> List[str]:
        """Per-row values for a slot, falling back to a generic pool."""
        values = (context or {}).get(key)
        if values is None:
            idx = self.rng.integers(0, len(fallback), size=size)
            return [fallback[i] for i in idx]
        arr = list(values)[:size]
        if len(arr) < size:
            arr += [arr[i % max(len(arr), 1)] if arr else fallback[0]
                    for i in range(size - len(arr))]
        out = []
        for v in arr:
            t = str(v).strip()
            out.append(t if t and t.lower() not in ("nan", "none", "") else fallback[0])
        return out

    def review_titles(self, size: int, ratings: Optional[Sequence] = None) -> np.ndarray:
        levels = self.normalize_ratings(ratings, size, self.rng)
        return np.array([self._title.expand(f"title_{lvl}") for lvl in levels], dtype=object)

    def notes(self, size: int) -> np.ndarray:
        return np.array([self._note.expand("note") for _ in range(size)], dtype=object)

    def comments(self, size: int) -> np.ndarray:
        return np.array([self._comment.expand("comment") for _ in range(size)], dtype=object)


# Lexicons for verifying sentiment conformance (used by tests and the Oracle
# layer): marker phrases that only occur in the respective halves of the
# review grammar.
POSITIVE_MARKERS = (
    "loved", "recommend", "great", "happy", "impressed", "excellent",
    "premium", "perfect", "blown away", "five stars", "worth every penny",
    "solid", "10/10",
)
NEGATIVE_MARKERS = (
    "disappointing", "waste of money", "avoid", "terrible", "frustrated",
    "cheaper than advertised", "stopped working", "overpriced", "do not recommend",
    "never again", "buyer beware", "expected better", "not impressed",
)


def detect_sentiment(text: str) -> Optional[str]:
    """Crude lexicon-based polarity check for conformance verification."""
    lower = str(text).lower()
    pos = any(m in lower for m in POSITIVE_MARKERS)
    neg = any(m in lower for m in NEGATIVE_MARKERS)
    if pos and not neg:
        return "positive"
    if neg and not pos:
        return "negative"
    return None
