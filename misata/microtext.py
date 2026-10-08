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

import bisect
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
    # Inline sugar: ((a|b|c)) picks one, [[...]] is included half the time.
    # Innermost first, so they nest.
    _CHOICE = re.compile(r"\(\(([^()]*)\)\)")
    _OPTION = re.compile(r"\[\[([^\[\]]*)\]\]")
    MAX_DEPTH = 12

    def __init__(self, rules: Dict[str, List[Rule]], rng: np.random.Generator,
                 capitalise: bool = False):
        self.rng = rng
        # Off by default: capitalisation is a property of the grammar that
        # asked for it, not of every caller of this class.
        self.capitalise = capitalise
        self._templates: Dict[str, List[str]] = {}
        self._weights: Dict[str, np.ndarray] = {}
        self._cum: Dict[str, List[float]] = {}
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
            # Cumulative weights as a plain list: one rng.random() and a
            # bisect per node is ~20x cheaper than rng.choice(p=...).
            cum = np.cumsum(w / w.sum()).tolist()
            cum[-1] = 1.0
            self._cum[symbol] = cum

    def expand(self, symbol: str, _depth: int = 0, **slots: str) -> str:
        if _depth > self.MAX_DEPTH:
            raise RecursionError(f"grammar too deep at '{symbol}'")
        templates = self._templates[symbol]
        if len(templates) == 1:
            template = templates[0]
        else:
            template = templates[bisect.bisect_right(self._cum[symbol], self.rng.random())]

        if "((" in template or "[[" in template:
            template = self._inline(template)

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

    def _inline(self, template: str) -> str:
        rng = self.rng
        while True:
            m = self._OPTION.search(template) or self._CHOICE.search(template)
            if m is None:
                return re.sub(r"  +", " ", template)
            if m.re is self._OPTION:
                rep = m.group(1) if rng.random() < 0.5 else ""
            else:
                opts = m.group(1).split("|")
                rep = opts[int(rng.integers(len(opts)))]
            template = template[:m.start()] + rep + template[m.end():]


# ---------------------------------------------------------------------------
# Review grammar — one sub-grammar per star rating
# ---------------------------------------------------------------------------

_OBJECTS = (
    "laptop bag", "bike", "car boot", "rucksack", "suitcase", "desk drawer", "bedside table",
    "kitchen counter", "windowsill", "bathroom shelf", "hallway", "garden shed", "camper van",
    "pram", "gym locker", "handbag", "glovebox", "work van", "spare room", "loft", "balcony",
    "caravan", "boat", "tent", "school bag", "nappy bag", "tool box", "fridge door", "dresser",
    "wardrobe", "airing cupboard", "office drawer", "shoe rack", "coffee table", "bookshelf",
    "sideboard", "conservatory", "porch", "utility room", "garage", "summer house", "dorm room",
    "studio flat", "houseboat", "allotment shed", "carry-on", "duffel bag", "bike pannier",
    "tote", "beach bag", "gym bag", "cool box", "picnic basket", "dog crate", "cat bed",
)
_PETS = ("the dog", "the cat", "our puppy", "the kitten", "our spaniel", "the labrador",
         "my terrier", "the rabbit", "our greyhound", "the hamster", "the parrot", "our collie")
_ACTIVITIES = (
    "a week of camping", "a long-haul flight", "a festival weekend", "the school run",
    "my morning commute", "a ten-mile hike", "a rainy week in Scotland", "a house move",
    "a wedding", "Christmas dinner", "a beach holiday", "a ski trip", "a road trip",
    "marathon training", "a stag do", "a hen weekend", "night shifts", "exam season",
    "a kitchen renovation", "a baby shower", "a garden party", "a work conference",
    "a family barbecue", "a boat trip", "a heatwave", "the January sales rush",
    "a cycling holiday", "a three-day hike", "a business trip", "a christening",
    "a power cut", "a snowstorm", "parents' evening", "a five-a-side match",
    "a yoga retreat", "a camping trip with the kids", "a city break", "a gig",
    "a long weekend away", "Sunday lunch", "a birthday party", "half-term",
)

# What people say about a particular kind of product. A clothing review talks
# about sizing, an electronics review about battery life, a kitchen review
# about cleaning up. Rendered per row from the product's family.
_FAMILY_LINES: Dict[str, List[Rule]] = {
    "num": ["two", "three", "four", "five", "six", "ten", "2", "3", "5", "8"],
    "pos_clothing": ["I'm ((usually|normally|always)) a ((size 8|size 10|size 12|size 14|size 16|small|medium|large)) and the ((S|M|L|XL|10|12|14)) fits ((perfectly|just right|like a glove|well)).",
                     "((Washed|Has been washed)) it ((three|four|five|a dozen)) times and it ((hasn't shrunk|kept its shape|still looks new|hasn't faded)).",
                     "((Fabric|Material)) is ((soft|thick|breathable|substantial)) without being ((heavy|hot|stiff|scratchy)).",
                     "((Length|The length|The cut)) is ((spot on|perfect|just right)) for ((me at 5'4\"|my height|someone tall|petite me)).",
                     "((Wore|Have worn)) it to ((a wedding|work|a party|the pub|a christening|dinner)) and got ((loads of|several|a few)) compliments.",
                     "((Pockets|The pockets)) are ((deep enough for my phone|actually usable|a great size)).",
                     "((Ordered|Got)) the ((navy|black|olive|grey|cream|burgundy|sage)) and it's ((gorgeous|exactly as pictured|even better in person)).",
                     "((Keeps|Kept)) me ((warm|dry|cool)) ((on the school run|on a {num}-mile walk|through a downpour|all day at the office))."],
    "neg_clothing": ["((Shrank|Shrunk)) ((a whole size|badly|noticeably)) after ((one|the first|two)) ((wash|washes)).",
                     "((Sizing|The sizing)) is ((way off|all over the place|tiny)), ((I'm|normally a)) ((medium|size 12|large)) and ((couldn't get it on|it swamps me|it's skin tight)).",
                     "((Bobbled|Pilled|Faded)) after ((a week|two wears|one wash)).",
                     "((Zip|Button|Seam|Hem)) ((broke|came undone|split|popped)) ((on the first wear|after {num} wears|within a week)).",
                     "((Colour|The colour)) ((ran|bled|faded)) ((in the wash|on the first wash|onto everything else)).",
                     "((Way|Much|Far)) ((thinner|scratchier|shorter)) than the ((photos|model|description)) ((suggest|make out|let on))."],
    "pos_electronics": ["Battery ((lasts|gets me|easily does)) ((about|around|over)) ((eight|ten|twelve|twenty|30)) hours((.| on a charge.| of real use.))",
                        "((Paired|Connected|Synced)) with my ((phone|laptop|iPad|TV)) ((first time|instantly|in seconds)).",
                        "((Sound|Picture|Screen)) quality is ((excellent|crisp|really clear|better than my old one)).",
                        "((Charges|Tops up)) ((fully|to 100%)) in ((under an hour|about two hours|no time)).",
                     "((App|The app)) is ((simple|clean|easy)) and ((updates|firmware updates)) ((installed|went through)) ((without a hitch|in minutes|automatically)).",
                     "((Range|Signal)) ((reaches|covers)) the ((whole house|garden|top floor|other end of the flat)) ((no problem|easily|without dropping)).",
                     "((Noise cancelling|The ANC|The mic)) is ((excellent|seriously good|better than expected)) ((on the train|on calls|on flights|in the office))."],
    "neg_electronics": ["Battery ((dies|is flat|barely lasts)) ((after|within)) ((two|three|a couple of)) hours.",
                        "((Keeps|Constantly)) ((disconnecting|dropping the connection|losing Bluetooth)).",
                        "((Gets|Runs)) ((really|uncomfortably|worryingly)) ((hot|warm)) when ((charging|in use)).",
                     "((Stopped|Quit)) ((charging|turning on|connecting)) after (({num} weeks|a fortnight|a month)).",
                     "((Firmware|Software)) update ((bricked|broke|reset)) it ((completely|twice|overnight)).",
                     "((Mic|Speaker|Screen)) ((crackles|flickers|cuts out)) ((constantly|every few minutes|on every call))."],
    "pos_home": ["((Looks|Fits in)) ((great|perfect|lovely)) in our ((living room|bedroom|hallway|spare room)).",
                 "((Colour|Shade)) ((matches|goes with)) ((our|my)) ((decor|sofa|walls|bedding)) ((perfectly|nicely|really well)).",
                     "((Washed|Has washed)) ((really|up|)) ((well|nicely|beautifully)) and ((stayed|kept)) ((soft|its colour|its shape)).",
                     "((Guests|Visitors|Everyone who comes round)) ((always|keep|)) ((comment on it|ask where it's from|notice it)).",
                     "((Assembly|Putting it up|Hanging it)) took ((ten|twenty|fifteen)) minutes with ((no tools|the screws included|a drill))."],
    "neg_home": ["((Colour|Shade)) ((clashes|looks nothing|is way off)) ((with|from)) the ((photos|rest of the room|website)).",
                 "((Smaller|Thinner|Cheaper)) in person than ((it looks|the photos suggest|expected)).",
                     "((Wobbles|Squeaks|Leans)) ((no matter what|even on a flat floor|constantly)).",
                     "((Fibres|Fluff|Threads)) ((everywhere|all over the floor|shedding)) ((after one wash|from day one|for weeks))."],
    "pos_kitchen": ["((Cleans up|Wipes clean|Washes up)) ((in seconds|easily|with no scrubbing)).",
                    "((Heats up|Boils|Warms up)) in ((under|about)) ((two|three|five)) minutes.",
                    "((Made|Cooked|Whipped up)) ((pancakes|a stir fry|soup|a roast|porridge|smoothies)) ((on day one|straight away|the first evening)) and ((loved it|it was great|no complaints)).",
                     "((Survived|Has survived)) ((the dishwasher|daily use|the kids)) ((for months|without a mark|so far)).",
                     "((Pours|Grinds|Blends|Slices)) ((cleanly|evenly|perfectly)) ((every time|without fuss|no drips)).",
                     "((Fits|Stores)) ((neatly|easily)) in ((a small cupboard|the drawer|our tiny kitchen))."],
    "neg_kitchen": ["((Food|Everything)) ((sticks|burns|catches)) ((already|after a week|even with oil)).",
                    "((Handle|Lid|Base)) ((gets|got)) ((scorching|too hot|loose)) ((within a week|after a few uses|straight away)).",
                     "((Leaks|Drips|Spits)) ((every time|whenever I use it|all over the counter)).",
                     "((Rusted|Chipped|Cracked)) after ((a week|{num} uses|the first dishwasher cycle))."],
    "pos_beauty": ["((Skin|My skin)) ((feels|looks)) ((softer|smoother|less dry|brighter)) after ((a week|a few days|two weeks)).",
                   "((Smells|Scent is)) ((lovely|subtle|fresh|gorgeous)) ((and not overpowering|without being too strong|)).",
                   "((A little|A tiny amount|One pump)) goes a long way.",
                     "((Lasts|Stays on)) ((all day|through a twelve-hour shift|from morning to night)) ((without touching up|no transfer|no fading)).",
                     "((Absorbs|Sinks in)) ((quickly|fast|in seconds)) and ((isn't greasy|doesn't leave a film|layers well under makeup)).",
                     "((My|Our)) ((sensitive|dry|combination|oily)) skin ((loves it|has calmed down|is so much happier))."],
    "neg_beauty": ["((Broke me out|Made my skin itch|Stung my eyes)) ((after one use|within a day|straight away)).",
                   "((Smell|The scent)) is ((overpowering|chemical|sickly)) and ((lingers|stays for hours|gave me a headache)).",
                     "((Pump|Lid|Tube)) ((broke|leaked|split)) ((in my bag|on day two|after a week)).",
                     "((Did|Made)) ((nothing|no difference|zero difference)) after ((a month|six weeks|two full bottles))."],
    "pos_sports": ["((Used|Took)) it to the gym ((three|four|five)) times a week ((for a month|since January|for ages)) and ((no issues|it's holding up|still like new)).",
                   "((Grip|Weight|Balance)) feels ((spot on|just right|really good)) for ((beginners|my level|home workouts)).",
                     "((Packs|Folds)) down ((small|tiny|neatly)) and ((fits in my rucksack|goes everywhere|takes no room)).",
                     "((Survived|Coped with)) ((mud|rain|a heatwave|a muddy trail run)) ((no bother|without a mark|brilliantly))."],
    "neg_sports": ["((Started|Began)) ((tearing|slipping|splitting)) after ((a few sessions|a week of use|two runs)).",
                   "((Too|Far too)) ((light|heavy|slippery|thin)) for ((proper|serious|any real)) ((training|workouts|use)).",
                     "((Smells|Stinks)) ((badly|of rubber|horrendous)) ((even after airing|for weeks|in the car)).",
                     "((Strap|Buckle|Seam)) ((snapped|gave way|ripped)) ((mid-session|on the second run|halfway up a hill))."],
    "pos_toys": ["((My|Our)) ((son|daughter|little one|kids|grandson|granddaughter)) ((hasn't put it down|plays with it every day|loves it|was thrilled)).",
                 "((Kept|Has kept)) the kids ((busy|entertained|quiet)) for ((hours|a whole afternoon|the entire weekend)).",
                     "((Easy|Simple)) enough for a ((three|four|five|six))-year-old to ((use alone|set up|play with)) ((without help|on their own|happily)).",
                     "((Good|Great|Solid)) ((quality|wood|plastic)), ((no sharp edges|nothing flimsy|built to survive toddlers))."],
    "neg_toys": ["((Broke|Fell apart|Snapped)) ((within an hour|on the first day|after one play)), ((tears all round|kids were gutted|very disappointing)).",
                 "((Pieces|Parts)) ((missing|don't fit together|keep falling off)) ((out of the box|already|constantly)).",
                     "((Batteries|The batteries)) ((ran out|died|drained)) ((in a day|within hours|by bedtime)).",
                     "((Way|Far|Much)) ((too|)) ((small|fiddly|loud)) for a ((three|four|five))-year-old."],
}

# "On the plus side, Much better" -> "On the plus side, much better".
_CONNECTOR_CASE = re.compile(
    r"((?:That said|However|On the other hand|Then again|Sadly|Unfortunately|The downside:|"
    r"Only thing is|Mind you|Still|To be fair|On the plus side|In fairness|Credit where due|"
    r"On the bright side|Having said that|Even so),? )([A-Z])(?=[a-z])")


def _plural_np(phrase: str) -> bool:
    last = phrase.split()[-1].lower() if phrase.split() else ""
    return (not phrase.startswith(("a ", "an ")) and last.endswith("s")
            and not last.endswith(("ss", "us", "is")))


_REVIEW_RULES: Dict[str, List[Rule]] = {
    # ── star-level entry points ──
    # A real review is an opening verdict, two to four sentences of what
    # happened (who it was for, how it gets used, what is good or bad about
    # this particular thing, how it compares), and sometimes a closing word.
    "review_5": [
        "{opener_5} {body_pos} {closer_5}",
        "{opener_5} {body_pos}",
        (0.8, "{body_pos} {closer_5}"),
        (0.6, "{context_pos} {body_pos} {closer_5}"),
    ],
    "review_4": [
        "{opener_4} {body_pos} {nit}",
        "{opener_4} {body_pos} {closer_4}",
        (0.6, "{body_pos} {nit} {closer_4}"),
        (0.6, "{context_pos} {body_pos} {nit}"),
    ],
    "review_3": [
        "{opener_3} {body_mixed}",
        "{body_mixed} {closer_3}",
        "{opener_3} {body_mixed} {closer_3}",
        (0.6, "{context_any} {body_mixed} {closer_3}"),
    ],
    "review_2": [
        "{opener_2} {body_neg} {closer_2}",
        "{opener_2} {body_neg}",
        (0.6, "{body_neg} {closer_2}"),
        (0.6, "{context_neg} {body_neg} {closer_2}"),
    ],
    "review_1": [
        "{opener_1} {body_neg} {closer_1}",
        "{opener_1} {body_neg_strong} {closer_1}",
        "{body_neg_strong} {closer_1}",
        (0.6, "{context_neg} {body_neg_strong}"),
    ],
    # ── bodies ──
    "body_pos": [(1.0, "{aspect_pos}"), (1.6, "{aspect_pos} {aspect_pos2}"),
                 (1.4, "{fam_pos} {aspect_pos}"), (1.0, "{aspect_pos} {fam_pos}"),
                 (1.0, "{aspect_pos} {extra_pos}"), (0.8, "{extra_pos} {aspect_pos2}"),
                 (0.6, "{aspect_pos} {extra_pos} {aspect_pos2}")],
    "body_mixed": ["{aspect_pos_c} {but} {aspect_neg_c}",
                   "{aspect_neg_c} {but_pos} {aspect_pos_c}",
                   (0.6, "{extra_pos} {but} {aspect_neg_c}"),
                   (0.6, "{aspect_neg_c} {but_pos} {extra_pos}")],
    "body_neg": [(1.0, "{aspect_neg}"), (1.6, "{aspect_neg} {aspect_neg2}"),
                 (1.4, "{fam_neg} {aspect_neg}"), (1.0, "{aspect_neg} {fam_neg}"),
                 (1.0, "{aspect_neg} {extra_neg}"), (0.6, "{extra_neg} {aspect_neg2}")],
    "body_neg_strong": ["{aspect_neg} {aspect_neg2} {escalation}",
                        "{aspect_neg} {extra_neg} {escalation}"],
    # ── openers ──
    "opener_5": [
        "((Absolutely|Honestly|Genuinely|Totally|Really|Just)) ((love|loving)) ((it|this|this one))((!|.|!!))",
        "Couldn't be ((happier|more pleased))((.|!))",
        "((Exceeded|Beat|Surpassed)) ((every|all my|my)) expectation((s|)).",
        "((This|It))'s exactly what I ((was looking for|needed|wanted))((.|!))",
        "((Five|5)) stars((, no hesitation|, easily|, no question|)).",
        "((Honestly|Genuinely|Completely)) blown away((.|!))",
        "((Best|Easily the best|Probably the best)) ((purchase|buy)) I've made ((in a while|this year|in ages|in years)).",
        "I ((rarely|almost never|don't usually)) write reviews, but this ((earned|deserves|is worth)) one.",
        "((Wow|Brilliant|Fantastic|Superb|Excellent))((.|!|, just wow.))",
        "((So|Really|Very|Super)) ((glad|happy|pleased)) I ((bought|ordered|went for|chose)) this((.|!))",
    
        "((Obsessed|Smitten|In love)) ((with it|with this|))((!|!!|.))",
        "((Exactly|Precisely|Just)) ((as described|what I wanted|like the pictures))((.|!))",
    ],
    "opener_4": [
        "((Really|Very|Pretty)) solid ((overall|all round|on the whole)).",
        "((Very|Really|Mostly|Pretty)) ((happy|pleased)) with ((this|it|my purchase)).",
        "((Works|Does the job|Performs)) ((great|well|nicely|really well)).",
        "Good ((experience|purchase|buy)) ((from start to finish|overall|on balance)).",
        "Impressed ((for the price|at this price|for what it costs)).",
        "((Almost|Nearly|So close to)) perfect.",
        "Does ((what it promises|what it says|exactly what it says on the tin)).",
        "((Good|Nice|Great)) ((little|)) ((buy|find|product)), ((with one or two niggles|nearly five stars|minor quibbles aside)).",
    
        "((Good|Great|Nice)) ((value|quality|stuff)), ((nearly|almost)) ((perfect|five stars|there)).",
        "((Happy|Pleased|Chuffed)) ((overall|on the whole|enough))((.|!))",
    ],
    "opener_3": [
        "It's ((okay|ok|alright|fine))((.|, I guess.|, nothing more.))",
        "Mixed feelings ((on this one|about this|here)).",
        "((Decent|Fine|Passable)), but not ((great|amazing|brilliant)).",
        "Somewhere in the middle((.|, really.))",
        "Fine for the price((, I guess|, just about|)).",
        "((Meh|Hmm|Not sure))((.|...))",
        "((Average|Middling|So-so)) ((at best|overall|if I'm honest)).",
    
        "((It|This))'s ((fine|ok|alright)) ((I suppose|for what it is|nothing special)).",
        "((Not bad|Not terrible|Could be worse)), ((not great either|nothing special|but meh)).",
    ],
    "opener_2": [
        "((Disappointing|Underwhelming|A letdown))((.|, sadly.|, if I'm honest.))",
        "Expected ((better|more|a lot more))((.|, honestly.))",
        "Not ((impressed|happy|great)), ((sadly|to be honest|unfortunately)).",
        "((Wouldn't|Won't|Would not)) ((buy|order)) ((again|this again)).",
        "Below average((, sadly|, unfortunately|)).",
        "((Pretty|Quite|Really)) ((disappointed|underwhelmed|let down)).",
    
        "((Not|Wasn't)) ((what I expected|as described|worth the money))((.|, sadly.))",
        "((Meh|Hmm|Oh dear))((.|...))",
    ],
    "opener_1": [
        "((Terrible|Awful|Dreadful|Horrible)) ((experience|product|purchase))((.|!))",
        "((Complete|Total|Utter)) waste of ((money|time|money and time))((.|!))",
        "((Avoid|Steer clear|Don't bother))((.|!|, seriously.))",
        "One star is ((generous|too much|more than it deserves)).",
        "((Extremely|Really|Very|Seriously)) ((frustrated|annoyed|disappointed))((.|!))",
        "((Rubbish|Junk|Garbage))((.|!))",
    
        "((Worst|The worst)) ((purchase|buy|thing)) I've ((made|bought)) ((this year|in ages|ever))((.|!))",
        "((Broken|Faulty|Damaged)) ((on arrival|out of the box|within a day))((.|!))",
    ],
    # ── context: who it was for, why, when ──
    "context_pos": [
        "((Bought|Got|Ordered|Picked up)) ((this|one|it)) for my {relation}[[ for {occasion}]] and ((it went down a treat|it was a hit|it's been a big hit|it got used straight away)).",
        "((Bought|Got|Ordered)) ((this|it)) ((after my old one wore out|to replace a cheaper one|after reading the reviews|on a whim|for our {place}|for the {place})) {timing}.",
        "((We've|I've)) ((used|had)) it ((every day|daily|most days|twice a week|every weekend|on my commute|at work)) for ((about|nearly|over|just under)) {num} ((weeks|months)).",
        "((Second|Third)) one I've ((bought|ordered))((, the first was for my {relation}|, which says it all|)).",
        "My {relation} ((recommended|suggested|swore by)) ((it|this)) and ((they were right|I'm glad I listened|I can see why)).",
    
        "((Ordered|Bought|Got)) it ((on|after|following)) ((a recommendation|a friend's advice|a TikTok video|a magazine review|a Reddit thread)) {timing}.",
        "((Third|Fourth|Fifth)) ((purchase|order)) from this ((brand|seller|shop)) and ((never disappointed|always reliable|still happy)).",
        "((Needed|Wanted)) something ((simple|reliable|cheap|decent)) for {use} and this ((fits the bill|ticks every box|does exactly that)).",
    ],
    "context_neg": [
        "((Bought|Got|Ordered)) ((this|it)) for my {relation}[[ for {occasion}]] and ((it was embarrassing|had to apologise|it went straight back|they didn't like it)).",
        "((Bought|Ordered)) ((it|this)) {timing} ((to replace my old one|after reading the reviews|for our {place})) and ((regret it|wish I hadn't|returned it within a week)).",
        "Used it ((twice|three times|for a week|for {num} days|a handful of times)) before ((it broke|it stopped working|giving up on it)).",
        "My old ((budget|cheap|five-year-old|hand-me-down)) one was ((better|more reliable|nicer|sturdier)).",
    
        "((Ordered|Bought)) it ((on|after)) ((a recommendation|the reviews|a TikTok video|a friend's advice)), ((big mistake|wish I hadn't|regret it)).",
        "((Needed|Wanted)) something for {use} and this ((wasn't it|failed|didn't cut it)).",
    ],
    "context_any": ["{context_pos}", "{context_neg}"],
    "relation": ["mum", "dad", "partner", "son", "daughter", "sister", "brother", "flatmate",
                 "wife", "husband", "girlfriend", "boyfriend", "gran", "grandad", "nephew",
                 "niece", "best friend", "colleague", "boss", "neighbour", "teenager", "in-laws",
                 "mother-in-law", "kids", "little one", "uncle", "aunt"],
    "occasion": ["her birthday", "his birthday", "Christmas", "our anniversary", "Mother's Day",
                 "Father's Day", "a housewarming", "Eid", "Diwali", "a wedding present",
                 "a leaving gift", "Secret Santa", "graduation", "a new job", "Valentine's"],
    "place": ["new flat", "kitchen", "living room", "spare room", "office", "garden", "caravan",
              "campervan", "student house", "home office", "holiday let", "nursery", "gym bag",
              "car", "allotment"],
    "timing": ["last month", "in the spring", "a few weeks ago", "back in March", "in the sales",
               "on Black Friday", "before Christmas", "over the summer", "in January",
               "last year", "two months ago", "on Prime Day", "in the autumn", "last weekend"],
    "num": ["two", "three", "four", "five", "six", "2", "3", "4", "6", "8"],
    # ── extra sentences: the specific thing, people around it, comparisons ──
    "extra_pos": [
        "The ((colour|color|shade)) is ((exactly as pictured|even nicer in person|spot on|true to the photos)).",
        "((Much|Way|Noticeably|Miles)) better than the ((cheap|old|last|budget)) one I ((had|used to have|replaced)).",
        "My {relation} ((keeps borrowing it|wants one now|was jealous|already ordered one)).",
        "((Lighter|Smaller|Bigger|Sturdier)) than I expected, in a good way.",
        "((Arrived|Came|Turned up|Got here)) ((a day early|next day|ahead of schedule|well packed|in two days|before the weekend))((, which was a bonus|, nice surprise| too|)).",
        "((Really|Very|Super)) easy to ((clean|use|set up|put together|look after)).",
        "Fits ((perfectly|nicely|just right|well)) ((in my {place}|in the {place}|on my desk|where I needed it)).",
        "((Feels|Looks|Seems)) ((more expensive|pricier|higher-end)) than it ((was|is|cost)).",
        "((No|Zero)) ((complaints|regrets|issues)) after ((two|three|four|six|several)) ((weeks|months)).",
        "{feature_line_pos}",
        (2.5, "{fam_pos}"),
        (1.5, "((Perfect|Great|Ideal|Brilliant|Spot on|Just right)) for {use}((.|!| too.))"),
        "((Got|Bought|Use)) it ((mainly|mostly|)) for {use} and it's ((perfect|ideal|great|been brilliant|exactly right)).",
        "The {material} ((feels|looks|is)) ((lovely|really nice|great quality|better than expected|premium)).",
        "((Love|Really like)) that it's {material}((.|, feels like it'll last.))",
        "((We|I)) ((take|use|bring)) it ((everywhere|on every trip|most days|all the time)) now.",
        (1.4, "((Took|Brought|Packed)) it ((to|on a trip to|on holiday to|on a work trip to)) {city} and it ((held up brilliantly|was perfect|came in really handy|did the job))."),
        (1.4, "My ((friend|colleague|neighbour|cousin|flatmate)) {fname} ((has the same one|recommended it|bought one after seeing mine|wants one too|was the one who found it))."),
        (1.2, "((Used|Took|Had)) it ((with me|along|)) during {activity} and it was ((great|perfect|spot on|a lifesaver))."),
        (1.2, "((Lives|Sits|Stays)) in my {object} ((now|most of the time|permanently)) and ((comes out|gets used)) ((daily|all the time|most days))."),
        (1.0, "{pet_cap} ((is obsessed with it|tried to steal it|sleeps next to it|hasn't wrecked it yet))((.|, which is a first.))"),
        (1.0, "((Fits|Slots)) ((neatly|perfectly|easily)) in the {object}((.|, which was the whole point.))"),
    ],
    "extra_neg": [
        "The ((colour|color)) is ((nothing like|way off from|duller than)) the ((photos|pictures|listing)).",
        "My ((old|cheap|last|budget)) one ((was better|lasted longer|did a better job)).",
        "((Smaller|Flimsier|Cheaper-looking|Heavier)) than ((the photos suggest|expected|it looks online)).",
        "((Took|It took)) ((ten days|two weeks|over a week|forever)) to ((arrive|turn up|get here)).",
        "((Hard|Fiddly|Impossible|A nightmare)) to ((clean|set up|put together|adjust)).",
        "((Started|Began)) ((squeaking|rattling|peeling|fraying|leaking|wobbling)) after ((a week|a few days|two weeks|a month)).",
        "Customer service ((ignored|didn't answer|kept closing)) my ((emails|messages|tickets)).",
        "{feature_line_neg}",
        (2.5, "{fam_neg}"),
        (1.5, "((Not great|Useless|Pretty poor|Disappointing)) for {use}((.|, honestly.))"),
        "((Bought|Got)) it for {use} and it ((just isn't up to it|let me down|didn't cope)).",
        "The {material} ((feels|looks)) ((cheap|thin|nothing like the photos|worse than expected)).",
        (1.2, "((Took|Packed)) it ((to|on a trip to)) {city} and it ((fell apart|broke on day two|was useless|let me down))."),
        (1.2, "My ((friend|colleague|neighbour)) {fname} ((had the same problem|returned theirs too|warned me, should have listened))."),
        (1.0, "((Tried|Used)) it during {activity} and it ((gave up|wasn't up to it|was a disaster))."),
        (1.0, "((Doesn't|Won't)) even fit in the {object}, ((which was the whole point|so that's useless|annoyingly))."),
        (0.8, "{pet_cap} ((chewed|destroyed|ruined)) it in ((a day|an afternoon|ten minutes)), ((so not very durable|clearly not sturdy))."),
    ],
    "extra_pos_plain": ["((Really|Very|Super)) easy to ((clean|use|set up|look after)).",
                        "((Lighter|Sturdier|Smaller)) than I expected, in a good way.",
                        "((No|Zero)) ((complaints|regrets)) after ((two|three|six)) ((weeks|months))."],
    "extra_neg_plain": ["((Hard|Fiddly|A nightmare)) to ((clean|set up|adjust)).",
                        "((Smaller|Flimsier|Heavier)) than ((expected|the photos suggest))."],
    "feature_line_pos": ["{feature} {feature_is} ((a nice touch|really handy|the best bit|a real plus|well thought out|better than expected)).",
                         "((Love|Really like|Big fan of)) {feature_l}."],
    "feature_line_neg": ["{feature} {feature_is} ((pointless|flimsy|badly done|a gimmick|an afterthought|not great)).",
                         "{feature} ((broke|came loose|stopped working)) ((within a week|after a few days|almost immediately))."],
    # ── aspects ──
    # Aspects compose within a topic rather than being whole hand-written
    # sentences. A flat list of twelve sentences is why the 5-star grammar
    # reached 3,816 distinct strings against a docstring claiming tens of
    # thousands, and why vocabulary stopped growing at 285 words. Subject and
    # predicate are drawn from the same topic so they always agree.
    "aspect_pos": [
        "{ap_quality}", "{ap_setup}", "{ap_support}", "{ap_delivery}",
        "{ap_perf}", "{ap_ui}", "{ap_value}", "{ap_fit}", (9.0, "{ap_named}"),
    
        (2.0, "{extra_pos}"),
        "((The|My)) {n_quality} ((has held up|is holding up|has stood up)) ((really well|brilliantly|fine)) ((so far|after {num} months|despite the kids|despite daily use)).",
        "((Surprisingly|Really|Genuinely)) ((quiet|comfortable|well balanced|easy to carry|light|sturdy|solid)) for ((the size|the price|what it is)).",
    ],
    "aspect_pos_c": [
        "{ap_quality}", "{ap_setup}", "{ap_support}", "{ap_delivery}",
        "{ap_perf}", "{ap_ui}", "{ap_value}", "{ap_fit}", (6.0, "{ap_named_desc}"),
    ],
    "ap_quality": ["((the|the|my|its|this one's)) {n_quality} {v_seems} {t_quality_pos}"],
    "n_quality": ["quality", "build", "finish", "construction", "casing", "stitching", "hardware",
                  "packaging", "seams", "handle", "lid", "zip", "strap", "base", "buttons", "hinges",
                  "edges", "frame", "fabric", "lining", "sole", "padding", "clasp", "plug", "cable",
                  "screen", "wheels", "legs", "surface", "coating", "trim", "buckle", "knobs", "dial",
                  "drawstring", "cuffs", "collar", "glaze", "grip", "spout", "mesh", "laces"],
    "v_seems": ["feels", "seems", "looks", "comes across as", "is", "honestly feels", "really does feel"],
    "t_quality_pos": ["genuinely premium.", "((solid|sturdy)) and ((well made|well put together|nicely finished)).",
                      "a clear step above the ((price|price tag|cost)).", "((sturdier|better made|nicer)) than I ((expected|thought it would be|was expecting)).",
                      "built to ((last|go the distance|survive anything)).", "((far|way|much)) better than the ((photos|pictures|listing)) ((suggest|make it look|let on)).",
                      "((really|properly|seriously)) ((well made|good quality|well finished))."],
    "ap_setup": ["{n_setup} {v_took} {t_setup_pos}"],
    "n_setup": ["setup", "installation", "getting started", "the first run", "onboarding",
                "unboxing to working", "assembly", "putting it together", "pairing", "the first charge",
                "registration", "fitting it", "wall mounting", "calibration"],
    "v_took": ["took", "needed", "was done in", "wrapped up in"],
    "t_setup_pos": ["under ((five|ten|two)) minutes.", "about ((ten|fifteen|twenty)) minutes, start to finish.",
                    "one evening and no swearing.", "less time than the ((manual|instructions|box)) ((claims|says|suggests)).",
                    "((barely any|almost no|next to no)) effort."],
    "ap_support": ["{n_support} {v_replied} {t_support_pos}"],
    "n_support": ["customer service", "support", "the team", "their help desk", "the seller",
                  "the shop", "the live chat", "the returns team", "the brand", "their aftercare team"],
    "v_replied": ["replied", "got back to me", "answered", "followed up"],
    "t_support_pos": ["within ((the hour|a couple of hours|half a day)).", "the same day, and ((actually solved it|fixed it properly|sorted everything)).",
                      "((quickly|promptly|fast)) and without a script.", "before I had to ((chase them|follow up|ask twice)).",
                      "with a real answer, not a ((template|canned reply|copy-paste))."],
    "ap_delivery": ["{n_delivery} {v_arrived} {t_delivery_pos}"],
    "n_delivery": ["delivery", "shipping", "the parcel", "the order"],
    "v_arrived": ["arrived", "turned up", "landed", "showed up"],
    "t_delivery_pos": ["((two|three|a few)) days early, well ((packaged|packed|wrapped)).", "on time and ((undamaged|in one piece|perfectly packed)).",
                       "faster than the ((estimate|quoted date|tracking said)).", "properly ((boxed|packed)), no ((dents|damage|scuffs))."],
    "ap_perf": ["{n_perf} {v_runs} {t_perf_pos}"],
    "n_perf": ["performance", "battery life", "speed", "responsiveness", "range", "suction", "grip",
               "heat", "airflow", "signal", "warmth", "cushioning", "charging", "sound", "picture",
               "water resistance", "noise cancelling", "cooling", "pressure"],
    "v_runs": ["has been", "stays", "remains"],
    "t_perf_pos": ["((excellent|great|faultless)) so far.", "smooth even under ((heavy|daily|constant)) use.",
                   "((steady|reliable|consistent)) all ((week|month|day)).", "consistent ((under load|day to day|every time)).",
                   "strong after ((months|weeks|a year)) of ((daily|regular|heavy)) use."],
    "ap_ui": ["((the|the|my|its|this one's)) {n_ui} {v_is} {t_ui_pos}"],
    "n_ui": ["interface", "app", "dashboard", "layout", "menu", "control panel"],
    "v_is": ["is", "stays", "feels"],
    "t_ui_pos": ["clean and intuitive.", "obvious without a manual.",
                 "quick to learn.", "uncluttered.", "well thought through."],
    "ap_value": ["((the|the|its|this one's)) {n_price} {v_is_price} {t_value_pos}"],
    "n_price": ["price", "cost", "pricing"],
    "t_value_pos": ["more than fair for what you get.", "((honest|fair|reasonable)).",
                    "the reason I ((would|will|'d)) buy again.", "((well|way|a lot)) below what I expected to pay."],
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
    "ap_named_desc": ["{subject} {sv_seems} {t_quality_pos}",
                      "{subject} {sv_seems} ((great|lovely|really nice|well made)) ((in person|up close|for the price|so far))."],
    "ap_named_story": ["i ((tried|tested|started using|switched to)) {subject} {when} and it {v_works} {t_fit_pos}",
                       "{agent} ((on support|from the support team|on the chat|from customer care)) ((sorted it|fixed it|sorted my problem|helped me)) {when} ((without any fuss|in minutes|on the first try|really kindly)).",
                       "i ((came back to|went back to|ordered|bought)) {subject} ((again|a second time|)) {when} and ((have not regretted it|haven't looked back|it's been great))."],
    "an_named": [(3.0, "{an_named_desc}"), (2.0, "{an_named_story}")],
    "an_named_desc": ["{subject} {sv_seems} {t_quality_neg}",
                      "{subject} {sv_seems} ((cheap|flimsy|poorly made|tired)) ((already|after a week|for the price|up close))."],
    "an_named_story": ["i ((tried|tested|started using)) {subject} {when} and it {v_fails} {t_fit_neg}",
                       "{agent} ((on support|from the support team|on the chat)) ((promised a callback|said they'd email|promised a refund)) {when} that never ((came|happened|arrived)).",
                       "i ((gave up on|returned|sent back)) {subject} {when} and ((switched to something else|bought a different one|got my money back eventually))."],
    "ap_fit": ["it {v_works} {t_fit_pos}"],
    "v_works": ["works", "performs", "fits", "runs"],
    "t_fit_pos": ["exactly as ((described|advertised|pictured)).",
                  "with everything I already ((use|own|have)).",
                  "the way the ((listing|description|seller)) promised.",
                  "without a single ((surprise|problem|hiccup))."],
    "aspect_pos2": [
        "((Support|Customer service|The help desk)) ((replied|got back to me|answered)) within ((the hour|a few hours|a day)) when I ((had a question|needed help|got stuck)).",
        "Even the packaging was ((thoughtfully done|plastic-free|really nice|recyclable)).",
        "((My whole team|Half the office|My family|The whole household)) ((has switched over since|uses one now|has gone for these since|wants one now)).",
        "((Months|Weeks|A year)) in, it still ((works|performs|looks)) like ((day one|new|the day it arrived)).",
        "The little ((details|touches|things)) show ((real care|someone actually thought about it|attention to detail)).",
        "((Would|Will|Am going to)) ((buy|order|get)) ((another|a second one|one for my {relation})).",
    
        "((Gets|Has had)) ((compliments|comments|people asking about it)) ((every time|whenever|each time)) I ((use|wear|bring)) it.",
        "((No|Zero)) ((regrets|buyer's remorse|complaints)) ((whatsoever|at all|so far)).",
        "((Arrived|Came|Turned up)) ((well|beautifully|securely)) ((packed|wrapped|boxed))((, too| as well|)).",
        "((Cleaning|Looking after|Maintaining)) it is ((easy|a breeze|no effort|simple)).",
        "((Already|Have already)) ((ordered|bought|picked up)) ((a second|another|a spare)) ((for the office|for my {relation}|as a backup|for travel)).",
        "((Much|Way|Far)) ((nicer|better|sturdier)) than the ((one|version|model)) I ((had before|returned|replaced)).",
    ],
    "aspect_neg": [
        "{an_quality}", "{an_setup}", "{an_support}", "{an_delivery}",
        "{an_perf}", "{an_ui}", "{an_value}", "{an_fit}", (9.0, "{an_named}"),
    
        (2.0, "{extra_neg}"),
        "((The|My)) {n_quality} ((started to|began to)) ((wear|crack|peel|fade|wobble)) ((after {num} weeks|within a month|almost straight away)).",
        "((Really|Very|Surprisingly)) ((noisy|uncomfortable|awkward|heavy|flimsy|fiddly)) for ((the size|the price|what it is)).",
    ],
    # Deliberately carries no named production: body_mixed reaches this and
    # aspect_pos_c in the same expansion, and two independent draws that both
    # name the subject produce "X feels nothing like the photos. To be fair, X
    # feels genuinely premium." One side names it; the contrast is real.
    "aspect_neg_c": [
        "{an_quality}", "{an_setup}", "{an_support}", "{an_delivery}",
        "{an_perf}", "{an_ui}", "{an_value}", "{an_fit}",
    ],
    "an_quality": ["((the|the|my|its|this one's)) {n_quality} {v_seems} {t_quality_neg}"],
    "t_quality_neg": ["much cheaper than ((advertised|it looks|the price suggests)).", "flimsy in the hand.",
                      "nothing like the ((photos|pictures|listing)).", "((rushed|thrown together|badly finished)).",
                      "a downgrade on the ((previous|old|last)) version."],
    "an_setup": ["{n_setup} ((was|turned out to be|ended up being)) {t_setup_neg}"],
    "v_was": ["was", "turned into", "ended up being"],
    "t_setup_neg": ["confusing, and the ((docs|instructions|manual)) did not help.",
                    "an afternoon I will not get back.",
                    "((three|four|several)) attempts and a support ticket.",
                    "far harder than it needed to be."],
    "an_support": ["{n_support} {v_took_time} {t_support_neg}"],
    "v_took_time": ["took", "needed", "went"],
    "t_support_neg": ["((a week|ten days|forever)) to respond.", "((four|five|several)) emails to reach a human.",
                      "silent after the first reply.",
                      "((two|three)) weeks and still no resolution."],
    "an_delivery": ["{n_delivery} was {t_delivery_neg}"],
    "t_delivery_neg": ["late and the box ((arrived damaged|was crushed|was torn)).",
                       "((a fortnight|a week|ten days|twelve days)) past the estimate.",
                       "left in the rain with no notice.",
                       "((split open|soaked|dented)) on arrival."],
    "an_perf": ["{n_perf} {v_drops} {t_perf_neg}"],
    "v_drops": ["drops off", "degrades", "falls away", "collapses"],
    "t_perf_neg": ["far faster than claimed.", "after about a week.",
                   "the moment you actually load it.",
                   "under any real workload."],
    "an_ui": ["((the|the|my|its|this one's)) {n_ui} {v_is} {t_ui_neg}"],
    "t_ui_neg": ["clunky and slow.", "buried three menus deep.",
                 "clearly never user-tested.", "a maze."],
    "an_value": ["((the|the|its|this one's)) {n_price} {v_is_price} {t_value_neg}"],
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
        "Returning it was ((its own ordeal|a nightmare|a hassle|painful)).",
        "No response to ((two|three|several|my)) ((support emails|messages|complaints)).",
        "The replacement had ((the same problem|the same fault|a different fault|issues too)).",
        "((Photos|Pictures|The listing photos)) ((online|on the site|)) ((are|look)) nothing like the real thing.",
        "I ended up ((buying|ordering|going with)) a different ((brand|one|model)).",
        "((Had|Ended up having)) to ((chase|email|call)) ((them|support|the seller)) ((twice|three times|for a week)).",
    
        "((Packaging|The box)) was ((ripped|soaked|crushed|half open)) when it ((arrived|turned up|got here)).",
        "((Smells|Smelled)) ((strongly|horribly|weirdly)) of ((chemicals|plastic|glue)) ((for days|out of the box|even now)).",
        "((Instructions|The manual)) ((were|was)) ((useless|missing|in the wrong language|impossible to follow)).",
        "((Two|Three|Several)) ((screws|parts|pieces|buttons)) were ((missing|loose|broken)) ((out of the box|on arrival|from the start)).",
        "((Refund|My refund)) ((took|is taking)) ((weeks|ages|forever)) to ((come through|process|appear)).",
    ],
    "escalation": [
        "I've ((asked for|requested|demanded)) a refund.", "Reporting this to the ((marketplace|seller|site)).",
        "Save your money((.|!))", "Still waiting on ((a resolution|a refund|a reply)).",
        "((Sending it back|Returning it|It's going back))((.|, obviously.| tomorrow.))",
    ],
    # ── connectors, nits, closers ──
    "but": ["That said,", "However,", "On the other hand,", "But", "Then again,", "Sadly,",
            "Unfortunately,", "The downside:", "Only thing is,", "Mind you,"],
    "but_pos": ["Still,", "To be fair,", "On the plus side,", "In fairness,", "That said,",
                "Credit where due,", "On the bright side,", "Having said that,", "Even so,"],
    "nit": [
        "Only ((minor|real|small)) gripe is the ((packaging|instructions|price|colour|cable length)).",
        "Wish the ((manual|instructions|guide)) ((was|were)) clearer, but that's ((minor|a small thing|not a big deal)).",
        "((Slightly|A bit|Rather)) slow ((shipping|delivery)), though that's not the product's fault.",
        "((A|One more|Another)) ((second|different|darker|lighter|bolder)) ((colour|color|size|finish)) ((option would be nice|would be welcome|wouldn't hurt|is on my wishlist)).",
        "Docking ((one|a)) star for the ((setup process|price|packaging|delivery time)).",
        "((Would|Could)) be ((perfect|five stars)) if it ((were|was)) a ((bit|little)) ((cheaper|lighter|quieter|bigger)).",
    
        "((The|My)) only ((real|)) ((complaint|niggle|issue)): the ((plug|cable|strap|lid|clasp|zip|handle)) ((feels a bit cheap|could be better|is a little stiff|is fiddly)).",
        "((Instructions|The manual)) ((could use|needs)) ((pictures|a rewrite|more detail)), ((but|though)) I ((worked it out|got there|figured it out)) ((eventually|in the end|quickly enough)).",
        "((Runs|Comes up|Fits)) ((slightly|a touch|a bit)) ((small|large|big|narrow)), so ((size up|size down|check the chart)).",
        "((Took|It took)) ((a day|a couple of days|a week)) for the ((smell|new smell|packaging smell)) to ((go|fade|wear off)).",
        "((Bit|Slightly|A little)) ((noisier|louder|heavier|bulkier)) than I ((hoped|expected|would like)), but ((I can live with it|nothing major|no deal-breaker)).",
        "((Price|Cost)) ((went up|jumped|crept up)) ((after I bought it|since|the week after)), ((annoyingly|typically|which stings)).",
        "((Wish|Would love|I would like)) it ((came|was available)) in ((more colours|a bigger size|a smaller size|a travel version)).",
        "((Courier|Delivery driver|The driver)) ((left it|dumped it|chucked it)) ((on the doorstep|by the bins|in the porch)), ((but|though)) it ((survived|was fine|was undamaged)).",
    ],
    "closer_5": [
        "((Highly|Strongly|Totally)) recommend((.|!))", "Will ((definitely|absolutely|100%)) ((buy|order)) again.",
        "Worth every ((penny|cent|bit of the price)).", "((Already|Have already)) recommended it to ((friends|family|my {relation}|everyone)).",
        "((10/10|Five stars|A+))((.|!|, would buy again.))", "((Go for it|Just buy it|Don't hesitate))((.|!))",
    
        "((Couldn't|Can't)) ((fault it|ask for more))((.|!))",
        "((Thanks|Thank you)) ((for a great product|to the team|for the quick delivery))((!|.))",
    ],
    "closer_4": [
        "Recommended((.|!| overall.))", "((Would|Will)) ((buy|order)) again((.| at this price.))",
        "Good value ((overall|for money|all round)).", "((Happy|Pleased)) with the ((purchase|buy))((.|, overall.))",
    
        "((Pretty|Very|Mostly)) ((pleased|chuffed|content)) ((overall|all in all|on balance)).",
        "((Four|4)) stars((, would be five with tweaks|, nearly five|)).",
    ],
    "closer_3": ["Might give it another ((try|go|chance)).", "Your ((mileage|experience)) may ((vary|differ)).",
        "There are probably better ((options|choices|ones out there)).", "Not bad, not great.",
        "((It'll do|It does the job|Fine)) ((for now|I suppose|for the money)).", "((Undecided|On the fence)) ((for now|so far|really)).",
        "Wouldn't ((rush|hurry)) to buy ((another|again))."],
    "closer_2": [
        "Hard to recommend((.|, sadly.))", "Look elsewhere ((first|is my advice|)).",
        "Expected more at this price.", "((Probably|Likely)) ((returning|sending back)) it.",
    
        "((Two|2)) stars ((for the effort|because it arrived|at a push)).",
        "((Will|Might)) ((try|go for)) a different ((brand|model|seller)) next time.",
    ],
    "closer_1": [
        "((Do not|Don't|Would not)) recommend((.|!))", "Never again((.|!))", "Buyer beware((.|!))",
        "((Avoid|Steer clear))((.|!|!!))",
    
        "((Absolute|Total)) ((joke|shambles|scam))((.|!))",
        "((Returning|Sending back)) ((it|this)) ((tomorrow|today|asap))((.|!))",
    ],
}

_TITLE_RULES: Dict[str, List[Rule]] = {
    # Real review titles are short and repeat a lot ("Love it!"), so a few
    # fixed favourites carry weight; the rest compose around the product.
    "title_5": [
        (1, "{fixed5}"), (3, "{love} {the_subject}{bang}"), (2, "{best} {subject} {ever}"),
        (2, "{adv_pos} {adj_pos}{bang}"), (2, "{adj_pos} {subject}{bang}"),
        (1, "{adj_pos}, {adj_pos2} and {adj_pos3}"), (1, "{adj_pos}{bang}"),
        (2, "((Great|Perfect|Brilliant|Lovely|Fab)) {subject} for {use}"),
        (1, "{adj_pos} {subject}, {adj_pos2}"),
        (1, "((My|Our)) new favourite {subject}"),
        (1, "{subject} ((is|was)) ((worth it|a winner|perfect|spot on|amazing)){bang}"),
        (1, "((Bought|Got)) for {use} - ((love it|perfect|ideal|spot on)){bang}"),
        (1, "{adv_pos} {adj_pos} {subject}, ((would buy again|five stars|no regrets))"),
        (1, "((Gorgeous|Lovely|Beautiful|Great)) {material}((, love it|, so soft|, premium feel|))"),
        (1, "((Perfect|Ideal|Brilliant)) {subject} for {use}((!|))"),
        (1, "((10/10|5 stars|A+)) {subject}")],
    "fixed5": ["Outstanding in every way", "Exceeded all expectations", "Absolutely loved it",
               "Best purchase this year", "Five stars, easily", "A hidden gem",
               "Perfect from start to finish", "Couldn't ask for more", "Love it",
               "Highly recommend", "Worth every penny", "So happy with this", "Obsessed",
               "Buy it", "Exactly what I wanted"],
    "love": ["Love", "Loving", "Absolutely love", "Really love", "In love with", "Big fan of"],
    "best": ["Best", "The best", "Easily the best", "Hands down the best", "Finally, a good"],
    "ever": ["ever", "I've owned", "I've bought", "so far", "in years", "at this price", ""],
    "adv_pos": ["Really", "Very", "Super", "So", "Seriously", "Incredibly", "Just"],
    "adj_pos": ["Great", "Excellent", "Fantastic", "Brilliant", "Perfect", "Amazing", "Superb",
                "Lovely", "Gorgeous", "Solid", "Sturdy", "Comfy", "Beautiful", "Wonderful"],
    "adj_pos2": ["well made", "great value", "fast delivery", "easy to use", "looks great",
                 "fits perfectly", "works well"],
    "adj_pos3": ["highly recommended", "would buy again", "no complaints", "worth it",
                 "a great gift", "five stars"],
    "title_4": [
        (1, "{fixed4}"), (2, "{good} {subject}{bang}"), (2, "{good}, {but4}"),
        (2, "{adv_mid} {good_l}"), (1, "{good} {subject}, {but4}"), (1, "{pretty} happy with {it}"),
        (2, "((Good|Nice|Solid)) {subject} for {use}"),
        (1, "{good} {subject}, {but4}"),
        (1, "{subject}: {good_l} ((overall|so far|for the price))"),
        (1, "((Solid|Good|Nice)) for {use}, {but4}"),
        (1, "((Mostly|Pretty|Really)) {good_l} with the {subject}"),
        (1, "((Nice|Good|Decent)) {material}, ((runs small|pricey|slow delivery|minor flaws))"),
        (1, "{subject} - ((good|solid|nice)) for {use}")],
    "fixed4": ["Really solid choice", "Great value for money", "Very happy with it",
               "Works great, minor quibbles", "Almost perfect", "Would buy again", "Good buy",
               "Does the job", "Nice", "Happy with it", "Good quality", "Pleasantly surprised"],
    "good": ["Good", "Nice", "Solid", "Great", "Decent", "Very good", "Pretty good", "Lovely"],
    "good_l": ["good", "nice", "solid", "pleased", "happy", "impressed"],
    "adv_mid": ["Pretty", "Mostly", "Really", "Overall", "Quite", "Very"],
    "pretty": ["Pretty", "Mostly", "Very", "Really", "Quite"],
    "it": ["it", "this", "the purchase", "my order", "the {subject}"],
    "but4": ["a few small issues", "but not perfect", "one small gripe", "slightly pricey",
             "runs a bit small", "delivery was slow", "minor flaws", "almost five stars"],
    "title_3": [
        (1, "{fixed3}"), (2, "{ok} {subject}"), (2, "{ok}, {but3}"), (1, "{subject} is {ok_l}"),
        (1, "Not bad, {but3}"),
        (2, "{ok} {subject} for {use}"),
        (1, "{subject}: {but3}"),
        (1, "((Fine|OK|Okay)) for {use}, {but3}"),
        (1, "{material} ((feels|looks)) ((ok|average|cheap-ish))"),
        (1, "((Average|So-so|Middling)) {subject}")],
    "fixed3": ["Decent but could be better", "Average at best", "Mixed feelings",
               "Good but not great", "A little overrated", "Middle of the road", "It's ok",
               "Fine", "Meh", "Does what it says", "Okay for the price", "Not bad"],
    "ok": ["OK", "Okay", "Average", "Decent", "Fine", "Alright", "Passable"],
    "ok_l": ["ok", "fine", "average", "just okay", "decent enough", "alright"],
    "but3": ["nothing special", "could be better", "not sure yet", "expected more",
             "it'll do", "some issues", "not amazing"],
    "title_2": [
        (1, "{fixed2}"), (2, "{disappointing} {subject}"), (2, "{not_great}, {why2}"),
        (1, "{subject} {broke}"), (1, "Not {worth} it"),
        (2, "((Poor|Disappointing|Not great)) {subject} for {use}"),
        (1, "{subject}: {why2}"),
        (1, "((Not great|Disappointing)) for {use}: {why2}"),
        (1, "{material} ((feels|looks)) ((cheap|thin|flimsy))"),
        (1, "{subject} ((let me down|disappointed|wasn't great))")],
    "fixed2": ["Disappointing — expected more", "Not worth the price", "Below average",
               "Wouldn't buy again", "Falls short", "Meh", "Not great", "Underwhelming",
               "Returned it", "Could be better"],
    "disappointing": ["Disappointing", "Underwhelming", "Mediocre", "Poor", "Flimsy", "Cheap"],
    "not_great": ["Not great", "Disappointed", "Not impressed", "Hmm", "Not for me"],
    "why2": ["poor quality", "too small", "not as pictured", "stopped working", "overpriced",
             "smaller than expected", "arrived late"],
    "broke": ["broke after a week", "stopped working", "fell apart", "didn't last",
              "is not as described"],
    "worth": ["worth", "really worth", "worth the money for"],
    "title_1": [
        (1, "{fixed1}"), (2, "{awful} {subject}{bang}"), (2, "Do not buy{bang}"),
        (1, "{subject} {broke}{bang}"), (1, "{awful}, {why1}"),
        (2, "((Useless|Terrible|Awful)) {subject}{bang}"),
        (1, "{subject}: {why1}"),
        (1, "((Useless|Rubbish|Awful)) for {use}: {why1}"),
        (1, "((Cheap|Nasty|Flimsy)) {material}{bang}"),
        (1, "((Avoid|Don't buy)) this {subject}{bang}")],
    "fixed1": ["Complete waste of money", "Avoid this one", "Terrible experience",
               "Nothing like the listing", "One star is generous", "Avoid", "Rubbish",
               "Awful", "Junk", "Total disappointment", "Never again", "Returned immediately"],
    "awful": ["Terrible", "Awful", "Useless", "Horrible", "Junk", "Garbage", "Dreadful"],
    "why1": ["broke on day one", "never arrived", "complete rip-off", "doesn't work",
             "fake product", "waste of money"],
    "bang": [(6, ""), (3, "!"), (1, "!!"), (1, "!!!")],
}

from misata.vocab_seeds import (
    AUDIT_REASONS,
    CHIEF_COMPLAINTS,
    CHURN_REASONS,
    CLINICAL_NOTES,
    CUSTOMER_FEEDBACK,
    DELIVERY_INSTRUCTIONS,
    DISCHARGE_INSTRUCTIONS,
    PRODUCT_DESCRIPTIONS_BY_CATEGORY,
    RESOLUTION_NOTES,
    RETURN_REASONS,
    SECONDARY_UNITS,
    STREET_NAMES,
    SYSTEM_ERROR_MESSAGES,
    TICKET_SUBJECTS,
    TRANSACTION_MEMOS,
)

# ---------------------------------------------------------------------------
# Generic business note grammar — replaces the lorem ipsum fallback
# ---------------------------------------------------------------------------

_NOTE_RULES: Dict[str, List[Rule]] = {
    "note": [
        "{actor} {action} {timeframe}.",
        "{actor} {action}; {follow_up}.",
        "{action_cap} {timeframe}. {follow_up_cap}.",
        (0.6, "{actor} {action}."),
        (0.4, "{status_note}"),
    ],
    "actor": [
        "Customer", "Client", "The team", "Account manager", "Support",
        "The vendor", "Requester", "Stakeholder", "Operations lead",
        "Compliance officer", "Engineering", "QA reviewer", "Billing admin",
    ],
    "action": [
        "requested a follow-up call", "confirmed the updated details",
        "raised a question about billing", "approved the proposed changes",
        "asked to reschedule the next review", "flagged a discrepancy in the records",
        "submitted the remaining documents", "requested expedited processing",
        "confirmed receipt of the shipment", "asked for clarification on terms",
        "escalated the open issue", "completed the onboarding steps",
        "verified credentials against policy", "initiated account security check",
        "requested contract renewal options", "confirmed delivery timeline",
        "authorized manual limit override", "signed off on deployment checklist",
    ],
    "action_cap": [
        "Follow-up scheduled", "Documents received and verified",
        "Issue resolved and closed", "Pending review by the billing team",
        "Awaiting confirmation from the client", "Records updated",
        "Security audit completed", "Manual verification pending",
        "Account review finalized", "Reconciliation completed",
    ],
    "timeframe": [
        "earlier today", "yesterday afternoon", "last week", "this morning",
        "on the last call", "during onboarding", "after the latest update",
        "prior to end-of-month close", "during the quarterly audit",
        "following customer escalation", "in the morning standup",
    ],
    "follow_up": [
        "will follow up next week", "no further action needed",
        "needs review before Friday", "details logged in the account history",
        "second reminder sent", "awaiting response",
        "ticket marked as resolved", "monitoring performance over 48 hours",
        "escalation path documented", "notified account executive",
    ],
    "status_note": [
        "All checklist items verified and approved for release.",
        "Routine monitoring indicates normal system operations.",
        "Pending final customer sign-off prior to case closure.",
        "Internal review completed with zero compliance exceptions noted.",
        "Automated sync completed successfully with zero failed records.",
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
        self._family = Grammar(_FAMILY_LINES, self.rng)
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

    _EMPTY_SLOTS: Dict[str, str] = {}
    _GENERIC_USE = ("everyday use", "work", "travel", "the weekend", "home", "the price",
                    "a beginner", "daily use", "gifting", "the commute")
    _GENERIC_MATERIAL = ("finish", "material", "fabric", "plastic", "coating")
    _GENERIC_FEATURE = ("finish", "design", "build", "packaging", "size", "weight",
                         "texture", "shape")

    def reviews(self, size: int, ratings: Optional[Sequence] = None,
                context: Optional[Dict[str, Sequence]] = None,
                vary_text: bool = True) -> np.ndarray:
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
        # A product type is a common noun and takes an article ("I tried the
        # rain jacket"); a proper name ("Ocean Star", "Northfold Parka") does not.
        subjects = [f"the {x}" if x[:1].islower() and not x.startswith(("the ", "my ", "a ", "an "))
                    else x for x in subjects]
        whens = self._slot_series(context, "when", size, self._GENERIC_WHEN)
        agents = self._slot_series(context, "agent", size, self._GENERIC_AGENT)
        uses = self._slot_series(context, "use", size, self._GENERIC_USE)
        from misata.vocab_seeds import CITIES_BY_COUNTRY, FIRST_NAMES
        _cities = [c for cs in CITIES_BY_COUNTRY.values() for c in cs]
        cities = [_cities[i] for i in self.rng.integers(0, len(_cities), size)]
        fnames = [FIRST_NAMES[i] for i in self.rng.integers(0, len(FIRST_NAMES), size)]
        acts = [_ACTIVITIES[i] for i in self.rng.integers(0, len(_ACTIVITIES), size)]
        objs = [_OBJECTS[i] for i in self.rng.integers(0, len(_OBJECTS), size)]
        pets = [_PETS[i] for i in self.rng.integers(0, len(_PETS), size)]
        fams = self._slot_series(context, "family", size, ("",))
        fam_pos, fam_neg = [], []
        for fam in fams:
            key = fam if f"pos_{fam}" in _FAMILY_LINES else None
            if key is None:
                fam_pos.append(self._review.expand("extra_pos_plain", **self._EMPTY_SLOTS))
                fam_neg.append(self._review.expand("extra_neg_plain", **self._EMPTY_SLOTS))
            else:
                fam_pos.append(self._family.expand(f"pos_{key}"))
                fam_neg.append(self._family.expand(f"neg_{key}"))
        mats = self._slot_series(context, "material", size, self._GENERIC_MATERIAL)
        feats = self._slot_series(context, "feature", size, self._GENERIC_FEATURE)
        feats = [f if f else self._GENERIC_FEATURE[0] for f in feats]
        the_feats = [re.sub(r"^(a|an) ", "the ", f) if re.match(r"^(a|an) ", f) else
                     (f if f.startswith("the ") else f"the {f}") for f in feats]
        _sv = [("feel", "seem", "look", "come across as"), ("feels", "seems", "looks", "comes across as")]
        sv = [_sv[0 if _plural_np(x.replace("the ", "", 1)) else 1][int(self.rng.integers(4))]
              for x in subjects]
        out = [self._review.expand(f"review_{lvl}", subject=subjects[i], when=whens[i], sv_seems=sv[i],
                                   agent=agents[i], feature=the_feats[i][:1].upper() + the_feats[i][1:],
                                   feature_l=the_feats[i],
                                   feature_is="are" if _plural_np(feats[i]) else "is",
                                   use=uses[i], material=mats[i], city=cities[i],
                                   fname=fnames[i], activity=acts[i],
                                   fam_pos=fam_pos[i], fam_neg=fam_neg[i], object=objs[i],
                                   pet_cap=pets[i][:1].upper() + pets[i][1:])
               for i, lvl in enumerate(levels)]
        out = [_CONNECTOR_CASE.sub(lambda m: m.group(1) + m.group(2).lower(), x) for x in out]
        if vary_text:
            from misata.paraphrase import vary
            out = vary(out, self.rng, "casual")
        return np.array(out, dtype=object)

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
            out.append(t if t and t.lower() not in ("nan", "none", "")
                       else fallback[int(self.rng.integers(len(fallback)))])
        return out

    _TITLE_SUBJECT = ("product", "purchase", "quality", "item", "buy", "value")

    def review_titles(self, size: int, ratings: Optional[Sequence] = None,
                      context: Optional[Dict[str, Sequence]] = None) -> np.ndarray:
        """Short review titles that follow the rating and, when the row says
        what was bought, name it ("Love this rain jacket!")."""
        levels = self.normalize_ratings(ratings, size, self.rng)
        subjects = self._slot_series(context, "subject", size, self._TITLE_SUBJECT)
        uses = self._slot_series(context, "use", size, self._GENERIC_USE)
        mats = self._slot_series(context, "material", size, self._GENERIC_MATERIAL)
        out = []
        for i, lvl in enumerate(levels):
            from misata.scenarios import _soft_lower
            subj = _soft_lower(subjects[i])
            t = self._title.expand(f"title_{lvl}", subject=subj, the_subject=f"this {subj}",
                                   use=uses[i], material=mats[i])
            t = re.sub(r"\s+", " ", t).strip()
            t = t[:1].upper() + t[1:]
            r = self.rng.random()
            if r < 0.06:
                t = t.lower()
            elif r < 0.08:
                t = t.upper()
            out.append(t)
        from misata.paraphrase import vary
        out = vary(out, self.rng, "casual", rate=0.4, short=True)
        return np.array(out, dtype=object)

    def notes(self, size: int) -> np.ndarray:
        return np.array([self._note.expand("note") for _ in range(size)], dtype=object)

    def comments(self, size: int) -> np.ndarray:
        return np.array([self._comment.expand("comment") for _ in range(size)], dtype=object)

    def ticket_subjects(self, size: int) -> np.ndarray:
        """Realistic customer support & IT incident ticket subjects."""
        pool = list(TICKET_SUBJECTS)
        return np.array([self.rng.choice(pool) for _ in range(size)], dtype=object)

    def ticket_bodies(self, size: int, context: Optional[Dict[str, Sequence]] = None) -> np.ndarray:
        """Structured, multi-sentence issue descriptions with contextual detail."""
        _URGENCY = [
            "This is blocking our workflow and needs immediate escalation.",
            "Impact is currently moderate; affecting several team members.",
            "Workaround in place temporarily, but need a permanent fix.",
            "Please investigate as soon as possible.",
            "Affecting multiple customer-facing accounts.",
            "",
            "",
        ]
        _STEPS = [
            "We attempted clearing cache and re-logging in with no change in behavior.",
            "The error is reproducible across both desktop Chrome and Safari.",
            "Observed right after the latest system deployment.",
            "Checked internal network logs and confirmed request reached the gateway.",
            "Occurs consistently whenever payload size exceeds 2MB.",
            "Able to reproduce reliably on staging environment.",
            "",
        ]
        subjects = self._slot_series(context, "subject", size, TICKET_SUBJECTS)
        results = []
        for i in range(size):
            subj = subjects[i]
            step = self.rng.choice(_STEPS)
            urg = self.rng.choice(_URGENCY)
            parts = [subj]
            if step:
                parts.append(step)
            if urg:
                parts.append(urg)
            results.append(" ".join(parts))
        return np.array(results, dtype=object)

    def resolution_notes(self, size: int, context: Optional[Dict[str, Sequence]] = None) -> np.ndarray:
        """Realistic engineering & support resolution notes."""
        pool = list(RESOLUTION_NOTES)
        return np.array([self.rng.choice(pool) for _ in range(size)], dtype=object)

    def transaction_memos(self, size: int) -> np.ndarray:
        """Realistic bank statement descriptors and transaction memos."""
        pool = list(TRANSACTION_MEMOS)
        return np.array([self.rng.choice(pool) for _ in range(size)], dtype=object)

    def error_messages(self, size: int, context: Optional[Dict[str, Sequence]] = None) -> np.ndarray:
        """Authentic server error messages, exceptions, and system traces."""
        pool = list(SYSTEM_ERROR_MESSAGES)
        return np.array([self.rng.choice(pool) for _ in range(size)], dtype=object)

    def clinical_notes(self, size: int, note_type: str = "clinical_notes") -> np.ndarray:
        """Authentic healthcare and clinical notes."""
        nt = str(note_type).lower()
        if "complaint" in nt:
            pool = list(CHIEF_COMPLAINTS)
        elif "discharge" in nt or "instruction" in nt:
            pool = list(DISCHARGE_INSTRUCTIONS)
        else:
            pool = list(CLINICAL_NOTES)
        return np.array([self.rng.choice(pool) for _ in range(size)], dtype=object)

    def delivery_instructions(self, size: int) -> np.ndarray:
        """Realistic delivery and shipping instructions."""
        pool = list(DELIVERY_INSTRUCTIONS)
        return np.array([self.rng.choice(pool) for _ in range(size)], dtype=object)

    def return_reasons(self, size: int) -> np.ndarray:
        """Realistic e-commerce return / refund reasons."""
        pool = list(RETURN_REASONS)
        return np.array([self.rng.choice(pool) for _ in range(size)], dtype=object)

    def churn_reasons(self, size: int) -> np.ndarray:
        """Realistic SaaS churn and cancellation reasons."""
        pool = list(CHURN_REASONS)
        return np.array([self.rng.choice(pool) for _ in range(size)], dtype=object)

    def audit_reasons(self, size: int) -> np.ndarray:
        """Realistic compliance and audit log reasons."""
        pool = list(AUDIT_REASONS)
        return np.array([self.rng.choice(pool) for _ in range(size)], dtype=object)

    def customer_feedback(self, size: int, ratings: Optional[Sequence] = None) -> np.ndarray:
        """Realistic customer feedback and survey comments."""
        pool = list(CUSTOMER_FEEDBACK)
        return np.array([self.rng.choice(pool) for _ in range(size)], dtype=object)

    def product_descriptions(self, size: int, category: Optional[Sequence] = None) -> np.ndarray:
        """Category-conditioned multi-sentence product descriptions."""
        if category is None:
            flat = [desc for descs in PRODUCT_DESCRIPTIONS_BY_CATEGORY.values() for desc in descs]
            return np.array([self.rng.choice(flat) for _ in range(size)], dtype=object)
        cats = [str(c).lower().strip() for c in list(category)[:size]]
        if len(cats) < size:
            cats += ["generic"] * (size - len(cats))
        res = []
        for cat in cats:
            matched_key = "generic"
            for k in PRODUCT_DESCRIPTIONS_BY_CATEGORY:
                if k in cat:
                    matched_key = k
                    break
            pool = PRODUCT_DESCRIPTIONS_BY_CATEGORY.get(matched_key, PRODUCT_DESCRIPTIONS_BY_CATEGORY["generic"])
            res.append(self.rng.choice(pool))
        return np.array(res, dtype=object)

    def addresses(self, size: int) -> np.ndarray:
        """Realistic street addresses with diverse street names and optional secondary units."""
        numbers = self.rng.integers(100, 9999, size=size)
        streets = self.rng.choice(STREET_NAMES, size=size)
        suffixes = self.rng.choice(["St", "Ave", "Blvd", "Way", "Dr", "Ln", "Ct", "Pkwy", "Rd"], size=size)
        has_secondary = self.rng.random(size) < 0.32
        secondaries = self.rng.choice(SECONDARY_UNITS, size=size)
        out = []
        for n, st, sfx, sec_flag, sec in zip(numbers, streets, suffixes, has_secondary, secondaries):
            base = f"{n} {st} {sfx}"
            if sec_flag:
                base += f", {sec}"
            out.append(base)
        return np.array(out, dtype=object)



# Lexicons for verifying sentiment conformance (used by tests and the Oracle
# layer): marker phrases that only occur in the respective halves of the
# review grammar.
POSITIVE_MARKERS = (
    "loved", "recommend", "great", "happy", "impressed", "excellent",
    "premium", "perfect", "blown away", "five stars", "worth every penny",
    "solid", "10/10", "love it", "brilliant", "fantastic", "superb", "outstanding",
    "flawless", "chuffed", "delighted", "thrilled", "worth every", "five out of five",
    "full marks", "won over", "pleasantly surprised", "exceeded", "obsessed", "a+",
    "couldn't be happier", "best purchase", "no complaints", "no regrets",
)
NEGATIVE_MARKERS = (
    "disappointing", "waste of money", "avoid", "terrible", "frustrated",
    "cheaper than advertised", "stopped working", "overpriced", "do not recommend",
    "never again", "buyer beware", "expected better", "not impressed",
    "waste of", "rip-off", "rubbish", "junk", "awful", "dreadful", "horrible",
    "disappointed", "let down", "underwhelm", "flimsy", "not worth", "steer clear",
    "don't bother", "do not bother", "returning it", "sent it back", "broke", "fell apart",
    "useless", "faulty", "garbage", "gutted", "fed up", "annoyed", "save your money",
    "one star", "refund", "nightmare", "shambles", "scam",
)


_NEGATED_POSITIVE = re.compile(
    r"\b(not|never|isn't|wasn't|won't|wouldn't|don't|doesn't|didn't|can't|cannot|couldn't|hardly|no|"
    r"cant|dont|wont|isnt|wasnt|doesnt|didnt|couldnt|wouldnt)"
    r"\s+(so\s+|very\s+|that\s+|really\s+|be\s+|exactly\s+)?("
    + "|".join(re.escape(m) for m in POSITIVE_MARKERS) + r")")


_POSITIVE_WORDS = re.compile(r"(?<![\w])(" + "|".join(re.escape(m) for m in POSITIVE_MARKERS) + r")(?![\w])")
_NEGATED_NEGATIVE = re.compile(
    r"\b(never|not|no|wasn't|isn't|without)\s+(been\s+|once\s+|ever\s+)?("
    + "|".join(re.escape(m) for m in NEGATIVE_MARKERS) + r")")


def detect_sentiment(text: str) -> Optional[str]:
    """Crude lexicon-based polarity check for conformance verification."""
    lower = str(text).lower()
    # "never disappointed", "no complaints": a negated negative is not one.
    lower = _NEGATED_NEGATIVE.sub(" fine ", lower)
    neg = any(m in lower for m in NEGATIVE_MARKERS)
    # "not great", "never happy": a negated positive is a negative.
    negated = _NEGATED_POSITIVE.sub(" ", lower)
    if negated != lower:
        neg = True
    # Whole words only: "recommendation" is not "recommend".
    pos = bool(_POSITIVE_WORDS.search(negated))
    if pos and not neg:
        return "positive"
    if neg and not pos:
        return "negative"
    return None
