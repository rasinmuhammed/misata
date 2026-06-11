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

    def __init__(self, rules: Dict[str, List[Rule]], rng: np.random.Generator):
        self.rng = rng
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

        return self._PLACEHOLDER.sub(_fill, template)


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
    "body_mixed": ["{aspect_pos} {but} {aspect_neg}", "{aspect_neg} {but_pos} {aspect_pos}"],
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
    "aspect_pos": [
        "The quality is noticeable the moment you unbox it.",
        "Setup took under five minutes.",
        "Customer service was fast and genuinely helpful.",
        "Delivery arrived two days early, well packaged.",
        "The build feels premium and sturdy.",
        "It works exactly as described.",
        "The interface is clean and intuitive.",
        "Battery life has been excellent so far.",
        "Performance is smooth even under heavy use.",
        "Instructions were clear and easy to follow.",
        "It integrates seamlessly with everything I already use.",
        "The price is more than fair for what you get.",
    ],
    "aspect_pos2": [
        "Support replied within the hour when I had a question.",
        "Even the packaging was thoughtfully done.",
        "My whole team has switched over since.",
        "Months in, it still works like day one.",
        "The little details show real care.",
    ],
    "aspect_neg": [
        "The quality feels much cheaper than advertised.",
        "Setup was confusing and the docs didn't help.",
        "Customer service took a week to respond.",
        "Delivery was late and the box arrived damaged.",
        "It stopped working properly after a few days.",
        "The interface is clunky and slow.",
        "Battery drains far faster than claimed.",
        "Several features simply don't work as described.",
        "It's overpriced for what you actually get.",
        "The sizing/specs are way off from the listing.",
    ],
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
        self._review = Grammar(_REVIEW_RULES, self.rng)
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

    def reviews(self, size: int, ratings: Optional[Sequence] = None) -> np.ndarray:
        levels = self.normalize_ratings(ratings, size, self.rng)
        return np.array([self._review.expand(f"review_{lvl}") for lvl in levels], dtype=object)

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
