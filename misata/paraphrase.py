"""Word-level variation for generated prose.

A grammar multiplies sentences but not words: every review it writes is
built from the same few hundred, so a column of 2,000 reviews compresses 9x
under gzip where people's writing compresses under 3x, and a word-trigram
classifier separates the two at a glance. People say the same thing in many
ways: the parcel "arrived", "came", "showed up"; the build is "solid",
"sturdy", "well made"; they write "don't" and "do not", start with
"Honestly," or "Tbh", and mistype a word now and then.

:func:`vary` applies that variation to text a grammar has already written,
by register:

- ``casual``: reviews, ticket messages, survey comments. Synonyms,
  intensifiers, discourse markers, contractions, occasional typos and
  lower-case starts.
- ``business``: internal notes, resolutions, audit reasons. Synonyms and
  contractions in moderation, no typos.
- ``product``: catalogue copy. Synonyms only.
- ``clinical``: chart notes. Clinical synonyms and standard abbreviations
  (BID, f/u, pt).

Every swap is phrase-for-phrase within one inflection (past for past, plural
for plural), so it never breaks agreement. Variation is seeded by the RNG the
caller passes, so output stays reproducible.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

# Each tuple is one group of interchangeable phrases. A phrase belongs to one
# group; matching is case-insensitive on word boundaries, longest first.
_COMMON: List[Tuple[str, ...]] = [
    # quality and judgement
    ("great", "excellent", "fantastic", "brilliant", "superb", "terrific", "outstanding"),
    ("good", "decent", "nice", "solid"),
    ("very good", "really good", "pretty good", "quite good"),
    ("bad", "poor", "awful", "terrible", "lousy", "rubbish"),
    ("happy", "pleased", "satisfied", "content", "glad"),
    ("disappointed", "let down", "underwhelmed", "unimpressed"),
    ("disappointing", "underwhelming", "a letdown", "a disappointment"),
    ("impressed", "won over", "pleasantly surprised"),
    ("perfect", "flawless", "spot on", "ideal"),
    ("sturdy", "solid", "robust", "well built", "well made"),
    ("flimsy", "cheaply made", "fragile", "poorly made"),
    ("premium", "high-end", "quality", "upmarket"),
    ("cheap", "inexpensive", "budget"),
    ("expensive", "pricey", "costly", "steep"),
    ("overpriced", "too expensive", "not worth the money", "a rip-off"),
    ("worth it", "worth the money", "money well spent", "good value"),
    ("value", "value for money", "bang for the buck"),
    ("smooth", "seamless", "painless", "easy"),
    ("easy", "simple", "straightforward", "effortless"),
    ("hard", "difficult", "tricky", "a pain"),
    ("clear", "obvious", "easy to follow"),
    ("confusing", "unclear", "hard to follow"),
    ("slow", "sluggish"),
    ("fast", "quick", "speedy", "rapid"),
    ("quickly", "fast", "in no time", "promptly"),
    ("slowly", "at a crawl", "gradually"),
    ("compact", "space-saving", "neat"),
    ("bulky", "chunky", "hefty"),
    ("heavy", "weighty", "hefty"),
    ("light", "lightweight", "featherlight"),
    ("comfortable", "comfy", "cosy", "pleasant to wear"),
    ("beautiful", "lovely", "gorgeous", "stunning"),
    ("nice", "lovely", "pleasant"),
    ("ugly", "unattractive", "dated"),
    ("cheap-looking", "tacky", "plasticky"),
    ("strong", "tough", "durable"),
    ("reliable", "dependable", "consistent", "trustworthy"),
    ("broken", "damaged", "busted", "faulty"),
    ("useless", "pointless", "worthless", "no use"),
    ("helpful", "useful", "handy"),
    ("friendly", "kind", "polite", "courteous"),
    ("rude", "unhelpful", "dismissive"),
    ("annoying", "irritating", "frustrating"),
    ("frustrated", "fed up", "annoyed", "irritated"),
    ("amazing", "incredible", "awesome", "unbelievable"),
    ("okay", "ok", "alright", "fine"),
    ("average", "mediocre", "middling", "so-so"),
    ("mixed feelings", "mixed views", "a mixed bag"),
    ("excellent", "first-rate", "top-notch", "superb"),
    ("genuinely", "truly", "really", "honestly"),
    ("really", "very", "so", "super", "seriously"),
    ("slightly", "a little", "a bit", "somewhat", "marginally"),
    ("quite", "fairly", "pretty", "rather"),
    ("completely", "totally", "entirely", "fully"),
    ("exactly", "precisely"),
    ("probably", "likely", "most likely", "presumably"),
    ("actually", "in fact", "really"),
    ("definitely", "certainly", "absolutely", "for sure"),
    ("overall", "all in all", "on the whole", "all things considered"),
    ("however", "that said", "but"),
    ("though", "however", "mind you"),
    ("also", "plus", "on top of that", "as well"),
    ("still", "even now", "to this day"),
    ("almost", "nearly", "just about"),
    ("immediately", "straight away", "right away", "at once"),
    ("recently", "lately", "of late"),
    ("finally", "at last", "eventually"),
    ("again", "once more", "a second time"),
    ("every day", "daily", "day in, day out"),
    ("a few", "a couple of", "several"),
    ("lots of", "plenty of", "loads of", "a lot of"),
    ("a lot", "a great deal", "loads"),
    ("problem", "issue", "fault", "glitch"),
    ("problems", "issues", "faults", "glitches"),
    ("issue", "problem", "fault"),
    ("issues", "problems", "faults"),
    ("gripe", "complaint", "niggle", "quibble"),
    ("minor", "small", "slight", "trivial"),
    ("major", "big", "serious", "significant"),
    # objects and commerce
    ("product", "item"),
    ("purchase", "buy", "order"),
    ("packaging", "packing", "box", "wrapping"),
    ("parcel", "package", "delivery"),
    ("delivery", "shipping", "postage"),
    ("customer service", "customer support", "the support team", "support"),
    ("support", "customer service", "the help desk"),
    ("team", "staff", "people"),
    ("price", "cost", "price tag"),
    ("instructions", "directions"),
    ("manual", "user guide", "instruction booklet"),
    ("setup", "set-up", "installation", "getting started"),
    ("quality", "build quality", "workmanship", "craftsmanship"),
    ("finish", "surface", "coating"),
    ("colour", "color", "shade"),
    ("size", "fit", "sizing"),
    ("photos", "pictures", "images"),
    ("listing", "product page", "description"),
    ("refund", "reimbursement", "money back"),
    ("replacement", "new one", "exchange"),
    ("week", "seven days"),
    ("weeks", "a few weeks"),
    ("month", "four weeks"),
    ("months", "a few months"),
    # verbs, past tense
    ("arrived", "came", "showed up", "turned up", "got here"),
    ("bought", "purchased", "ordered"),
    ("ordered", "bought", "purchased"),
    ("tried", "tested"),
    ("noticed", "spotted", "saw", "realised"),
    ("replied", "responded", "got back to me", "answered"),
    ("helped", "assisted", "sorted me out"),
    ("fixed", "resolved", "sorted", "sorted out"),
    ("stopped working", "died", "packed in", "quit on me"),
    ("returned", "sent back"),
    ("switched", "changed", "moved"),
    ("started", "began", "kicked off"),
    ("ended", "finished", "wrapped up"),
    ("used", "relied on", "tested"),
    ("loved", "adored", "really liked"),
    ("liked", "enjoyed", "appreciated"),
    ("hated", "disliked", "couldn't stand"),
    ("regretted", "been sorry about"),
    ("charged", "billed", "debited"),
    ("cancelled", "canceled", "stopped"),
    ("contacted", "reached out to", "got in touch with", "messaged"),
    ("checked", "looked at", "went through"),
    ("confirmed", "verified", "double-checked"),
    ("sent", "emailed", "forwarded"),
    ("updated", "changed", "amended"),
    ("waited", "hung on", "held on"),
    # verbs, present
    ("works", "functions", "does the job", "performs"),
    ("work", "function", "perform"),
    ("looks", "seems", "appears"),
    ("feels", "comes across as", "seems"),
    ("seems", "looks", "appears"),
    ("love", "adore", "really like"),
    ("like", "enjoy", "appreciate"),
    ("need", "require", "want"),
    ("want", "would like", "need"),
    ("recommend", "suggest", "endorse"),
    ("use", "rely on", "reach for"),
    ("help", "assist", "sort this out"),
    ("fix", "resolve", "sort out", "sort"),
    ("check", "look into", "investigate"),
    ("keep", "continue to", "still"),
    ("try", "attempt", "have a go"),
    ("think", "reckon", "feel", "believe"),
    ("guess", "suppose", "imagine"),
    ("says", "states", "shows"),
    ("shows", "displays", "says"),
    ("keeps", "continues to"),
    ("can't", "cannot"),
    ("couldn't", "could not"),
    ("doesn't", "does not"),
    ("don't", "do not"),
    ("didn't", "did not"),
    ("isn't", "is not"),
    ("wasn't", "was not"),
    ("won't", "will not"),
    ("wouldn't", "would not"),
    ("haven't", "have not"),
    ("hasn't", "has not"),
    ("I've", "I have"),
    ("I'm", "I am"),
    ("it's", "it is"),
    ("that's", "that is"),
    ("there's", "there is"),
    ("I'd", "I would"),
    ("I'll", "I will"),
    ("we've", "we have"),
    ("we're", "we are"),
    ("you're", "you are"),
    # time
    ("yesterday", "the day before"),
    ("today", "this morning", "earlier today"),
    ("this morning", "earlier today", "first thing"),
    ("last week", "the other week", "a week ago"),
    ("last month", "a few weeks back", "a month ago"),
    ("soon", "shortly", "before long"),
    ("as soon as possible", "asap", "urgently", "at your earliest convenience"),
    ("right now", "at the moment", "currently"),
    ("at the moment", "right now", "currently", "for now"),
    ("every time", "each time", "whenever"),
    ("since", "ever since"),
    ("within an hour", "inside an hour", "in under an hour"),
    ("on time", "as promised", "when promised"),
    ("late", "delayed", "behind schedule"),
]

_PRODUCT: List[Tuple[str, ...]] = [
    ("ideal for", "perfect for", "great for", "made for", "designed for", "built for"),
    ("features", "has", "offers", "comes with", "boasts"),
    ("comes with", "includes", "ships with", "is supplied with"),
    ("includes", "comes with", "has", "packs in"),
    ("designed with", "made with", "built with", "finished with"),
    ("made from", "crafted from", "made of", "built from", "cut from"),
    ("lightweight", "light", "featherweight"),
    ("durable", "hard-wearing", "long-lasting", "tough"),
    ("compact", "space-saving", "small", "neat"),
    ("classic", "timeless", "traditional", "iconic"),
    ("modern", "contemporary", "sleek", "clean-lined"),
    ("soft", "gentle", "smooth", "plush"),
    ("everyday", "daily", "day-to-day", "all-day"),
    ("relaxed", "easy", "loose", "laid-back"),
    ("a good pick for", "a smart choice for", "a solid choice for", "well suited to"),
    ("you reach for every day", "you'll use every day", "you'll reach for again and again"),
    ("come as standard", "are included", "are standard", "come built in"),
    ("works well for", "suits", "is great for", "is well suited to"),
    ("our best-selling", "our most popular", "a customer favourite", "the best-selling"),
    ("take on the classic", "spin on the classic", "update to the classic", "version of the classic"),
    ("easy-care", "low-maintenance", "easy-clean"),
    ("guarantee", "warranty", "promise"),
    ("weekend trips", "weekends away", "short breaks", "city breaks"),
    ("travel", "trips", "travelling", "getting away"),
    ("the office", "work", "the workplace", "office days"),
]

_PRODUCT_MORE: List[Tuple[str, ...]] = [
    ("design", "silhouette", "shape", "form"), ("finish", "surface finish", "coating"),
    ("fabric", "material", "cloth"), ("handle", "grip"), ("pockets", "storage pockets"),
    ("reinforced seams", "double-stitched seams", "strengthened seams", "taped seams"),
    ("a relaxed fit", "an easy fit", "a loose fit", "a laid-back fit"),
    ("lightweight", "light", "airy", "featherlight"), ("durable", "hard-wearing", "long-lasting", "rugged"),
    ("soft", "supple", "smooth", "cosy"), ("warm", "insulating", "toasty"), ("breathable", "airy", "ventilated"),
    ("waterproof", "weatherproof", "water-resistant"), ("rechargeable", "USB-rechargeable", "battery-powered"),
    ("everyday", "daily", "go-to", "all-purpose"), ("versatile", "adaptable", "multi-purpose", "flexible"),
    ("sturdy", "solid", "robust", "stable"), ("easy to clean", "simple to clean", "wipe-clean", "low-maintenance"),
    ("comes in", "is available in", "is offered in"), ("perfect", "ideal", "spot-on", "just right"),
    ("keeps", "holds", "maintains"), ("helps", "lets you", "makes it easy to"),
    ("stylish", "smart", "good-looking", "handsome"), ("compact", "space-saving", "neat", "pared-back"),
    ("premium", "high-quality", "top-quality", "quality"), ("sustainable", "responsibly made", "eco-conscious"),
    ("handmade", "hand-finished", "made by hand"), ("timeless", "classic", "enduring"),
    ("thoughtful", "considered", "well-thought-out", "clever"), ("guarantee", "warranty", "promise"),
    ("included", "supplied", "in the box"), ("recommended", "advised", "suggested"),
]

_CASUAL_EXTRA: List[Tuple[str, ...]] = [
    ("would buy again", "would order again", "will buy again", "would definitely buy again"),
    ("would not buy again", "won't be buying again", "would never buy again", "not buying again"),
    ("highly recommend", "strongly recommend", "totally recommend"),
    ("do not recommend", "can't recommend", "wouldn't recommend", "would not recommend"),
    ("waste of money", "waste of cash", "waste of good money"),
    ("five stars", "5 stars", "five out of five", "full marks"),
    ("10/10", "ten out of ten", "100%"),
    ("so far", "up to now", "to date", "thus far"),
    ("to be fair", "in fairness", "to be honest", "fair enough"),
    ("for the price", "at this price", "for what it costs", "for the money"),
    ("does what it says", "does exactly what it says", "does what it promises", "does the job"),
    ("stays", "holds up", "remains", "keeps"),
    ("like day one", "like new", "as good as new", "like the day it arrived"),
    ("under heavy use", "with daily use", "with heavy use", "under daily use"),
    ("please help", "any help appreciated", "help please", "can someone help"),
    ("thanks", "thank you", "cheers", "many thanks", "ta"),
    ("thanks for your help", "thanks in advance", "appreciate the help", "thank you for helping"),
    ("let me know", "tell me"),
    ("as soon as possible", "asap", "quickly please", "urgently"),
]

_CASUAL_MORE: List[Tuple[str, ...]] = [
    ("packaging", "packing", "wrapping", "box it came in"),
    ("instructions", "directions"),
    ("recommended", "suggested", "pointed me to", "raved about"),
    ("nice", "lovely", "pleasant", "cute", "neat"),
    ("love it", "adore it", "really like it"),
    ("I love", "I adore", "I really like"),
    ("loves it", "adores it", "is obsessed with it"),
    ("brilliant", "fab", "smashing", "cracking", "ace"),
    ("rubbish", "naff", "pants", "dire"),
    ("ages", "forever", "an age", "donkey's years"),
    ("bonus", "nice extra", "plus", "added bonus"),
    ("arrive", "turn up", "show up", "come", "get here"),
    ("months in", "a few months in", "several months on", "months later"),
    ("weeks in", "a few weeks in", "weeks on", "weeks later"),
    ("day one", "the first day"),
    ("the photos", "the pictures", "the product photos", "the images online"),
    ("a few days", "a couple of days", "a handful of days", "three or four days"),
    ("so far", "to date", "up to now"),
    ("easily", "comfortably", "without trouble"),
    ("everyone", "anyone", "all my friends", "anybody who asks"),
    ("friends", "mates", "people", "friends and family"),
    ("kids", "children", "little ones"),
    ("honestly", "frankly", "truthfully", "seriously"),
    ("properly", "correctly", "as it should"),
    ("quick", "speedy", "snappy", "swift"),
    ("lightweight", "light as a feather", "barely weighs anything"),
    ("comfortable", "comfy", "cosy", "easy on the body"),
    ("cheaper", "less expensive", "lower priced"),
    ("better", "nicer"),
    ("worse", "poorer"),
    ("bigger", "larger", "roomier"),
    ("smaller", "tinier", "more compact"),
    ("heavier", "weightier", "chunkier"),
    ("disappointed", "gutted", "let down", "deflated"),
    ("thrilled", "delighted", "over the moon", "chuffed"),
    ("useful", "handy", "practical"),
    ("noticed", "spotted", "clocked"),
    ("returned it", "sent it back", "took it back"),
    ("the price", "the cost", "the asking price"),
    ("at this price", "for this price", "at this price point"),
    ("for the price", "for the money", "for what you pay"),
    ("worth every penny", "worth every cent", "worth the money and then some"),
    ("would be nice", "would be welcome", "would be great", "would help"),
]

_CASUAL_TICKET: List[Tuple[str, ...]] = [
    ("app", "application", "mobile app"),
    ("website", "site", "web page"),
    ("login", "sign-in", "log-in"),
    ("log in", "sign in", "get in"),
    ("screenshot", "screen grab", "screen capture"),
    ("courier", "delivery company", "delivery firm", "carrier"),
    ("tracking", "the tracking", "tracking info"),
    ("statement", "bank statement"),
    ("card", "bank card", "debit card"),
    ("account", "profile", "login"),
    ("still", "even now", "as of today"),
    ("haven't received", "haven't had", "never got", "still don't have"),
    ("hasn't arrived", "hasn't come", "hasn't turned up", "is nowhere to be seen"),
    ("as soon as possible", "asap", "quickly", "urgently"),
    ("please", "kindly"),
    ("I need", "I really need", "I urgently need"),
    ("I'd like", "I want", "I would like"),
    ("something went wrong", "it broke", "something broke"),
    ("days", "working days"),
    ("weeks", "whole weeks"),
    ("again", "once more", "for the second time"),
    ("whole team", "entire team", "whole office", "everyone here"),
    ("customer", "client", "user"),
    ("issue", "problem", "fault"),
    ("error", "error message", "message"),
    ("help", "support", "assistance"),
    ("tried", "attempted"),
]

_BUSINESS: List[Tuple[str, ...]] = [
    ("customer", "client", "account holder", "user"),
    ("confirmed", "verified", "validated", "checked"),
    ("follow-up", "follow up"),
    ("completed", "finished", "done", "wrapped up"),
    ("pending", "outstanding", "awaiting action", "open"),
    ("escalated", "raised", "passed up", "referred"),
    ("approved", "signed off", "cleared", "OK'd"),
    ("reviewed", "checked", "looked over", "went through"),
    ("updated", "amended", "revised", "refreshed"),
    ("scheduled", "booked", "lined up", "set"),
    ("documented", "recorded", "written up", "logged"),
    ("flagged", "highlighted", "raised", "called out"),
    ("sent", "issued", "dispatched", "emailed"),
    ("no further action needed", "nothing further needed", "no action required",
     "no further action required"),
    ("next week", "early next week", "by next week", "within the week"),
    ("earlier today", "this morning", "today"),
    ("end-of-month close", "month-end close", "month end", "the monthly close"),
    ("discrepancy", "mismatch", "inconsistency", "variance"),
    ("details", "information", "particulars", "specifics"),
    ("refunded", "reimbursed", "credited back", "refunded in full"),
    ("issued", "processed", "raised", "sent"),
    ("closing", "closing out", "resolving", "marking done"),
    ("resolved", "fixed", "sorted", "closed out"),
    ("investigated", "looked into", "dug into", "examined"),
    ("customer confirmed", "client confirmed", "customer verified", "user confirmed"),
    ("shipped", "dispatched", "sent out", "posted"),
    ("replacement", "new unit", "exchange"),
    ("arranged", "set up", "organised", "booked"),
    ("advised", "told", "informed", "let the customer know"),
    ("on the account", "on file", "on their account", "on the profile"),
    ("to the customer", "to the client", "to them", "to the account holder"),
    ("with the customer", "with the client", "with them"),
    ("will monitor", "keeping an eye on it", "watching this", "will keep watching"),
    ("no reply from customer", "no response from the customer", "customer went quiet", "no answer from the client"),
    ("customer was frustrated", "customer was upset", "client was annoyed", "customer was unhappy"),
    ("offered", "gave", "provided", "applied"),
    ("raised a bug", "logged a defect", "filed a bug", "opened a bug"),
    ("known-issue article", "KB article", "help article", "known issue page"),
    ("internal note", "private note", "agent note", "account note"),
    ("sent confirmation", "confirmed by email", "emailed confirmation", "sent a confirmation"),
    ("billing address", "invoice address", "billing details"),
    ("delivery details", "shipping details", "delivery address"),
    ("the warehouse", "fulfilment", "the warehouse team", "ops"),
    ("the courier", "the carrier", "the delivery partner"),
    ("engineering", "the dev team", "engineers", "tech"),
    ("customer's identity", "account ownership", "the customer's ID"),
    ("checked", "looked at", "reviewed"),
    ("emailed", "sent an email to", "messaged"),
    ("called", "rang", "phoned"),
]

_CLINICAL: List[Tuple[str, ...]] = [
    ("patient", "pt", "the patient"),
    ("reports", "endorses", "states", "describes"),
    ("denies", "reports no", "negative for"),
    ("follow-up", "f/u", "follow up", "review"),
    ("twice daily", "BID", "twice a day", "b.i.d."),
    ("once daily", "daily", "QD", "once a day"),
    ("three times daily", "TID", "three times a day"),
    ("as needed", "PRN", "when required"),
    ("prescribed", "started on", "commenced", "initiated"),
    ("advised", "counselled", "instructed", "recommended"),
    ("shows", "demonstrates", "reveals", "notable for"),
    ("reveals", "shows", "demonstrates"),
    ("no evidence of", "no signs of", "without", "negative for"),
    ("bilateral", "bilaterally", "on both sides"),
    ("normal", "unremarkable", "within normal limits", "WNL"),
    ("history of", "hx of", "known", "background of"),
    ("shortness of breath", "SOB", "dyspnoea", "breathlessness"),
    ("blood pressure", "BP"),
    ("heart rate", "HR", "pulse"),
    ("weeks", "wks"),
    ("days", "d"),
    ("return if", "re-present if", "seek review if", "come back if"),
    ("worsening", "worse", "deteriorating", "progressive"),
    ("pain", "discomfort", "ache"),
    ("mild", "slight", "minimal"),
    ("moderate", "mod", "significant"),
    ("severe", "marked", "intense"),
    ("referral", "referred", "onward referral"),
]

_INTENSIFIABLE = ("happy", "pleased", "good", "nice", "solid", "comfortable", "easy", "quick",
                  "slow", "disappointed", "impressed", "sturdy", "light", "heavy", "small",
                  "big", "cheap", "expensive", "useful", "clear", "simple", "smooth", "soft")
_INTENSIFIERS = ("really", "pretty", "super", "quite", "very", "fairly", "so", "genuinely",
                 "incredibly", "reasonably", "surprisingly", "rather")
_MARKERS = ("Honestly, ", "To be fair, ", "Overall, ", "Also, ", "Plus, ", "Anyway, ",
            "That said, ", "For what it's worth, ", "Tbh ", "Not gonna lie, ", "In short, ",
            "Basically, ", "So ", "Oh and ", "On the plus side, ", "One thing: ", "FYI ")
_EMOJI = ("👍", "🙂", "📦", "🤷", "👀", "⭐")
_BUSINESS_MARKERS = ("Note: ", "Update: ", "FYI: ", "Per call: ", "Per email: ", "", "")

_REGISTERS = {
    "casual": _CASUAL_MORE + _CASUAL_TICKET + _COMMON + _CASUAL_EXTRA,
    "business": _BUSINESS,
    "product": _PRODUCT + _PRODUCT_MORE + [g for g in _COMMON if g[0] in (
        "great", "good", "easy", "smooth", "small", "light", "strong", "reliable", "helpful",
        "beautiful", "quickly", "fast", "comfortable", "also", "every day", "lots of",
        "really", "slightly", "quite", "completely", "premium", "sturdy")],
    "clinical": _CLINICAL,
}
# Patient-facing clinical text (discharge advice): the clinical swaps
# without the abbreviations a patient would not be handed.
_REGISTERS["patient"] = [g for g in (tuple(o for o in grp if not re.search(r"[A-Z]{2,}|\.\w|\bpt\b|/", o))
                                     for grp in _CLINICAL) if len(g) >= 2]

# Words with more than one sense are offered as replacements but never
# matched: "came" in "came back", "just" in "just before", "order" in "in
# order to", "light" as a colour or a lamp. Swapping those changes meaning.
_REPLACE_ONLY = frozenset("""
came got had just took went so fine light still since plus order thing box fit work use
like keep help check need want feel feels say says shows sorted sort sent moved changed
late soon today finish quality value support team size price issue problem product
purchase delivery parcel keeps stays remains looks seems appears used tested shade
listing description surface simple little big tiny huge awful dated hard pain costly
steep budget quality craftsmanship people staff thing box regret glad kind fair
mind you daily four weeks seven days week weeks month months review raised set told
open done d mod known worse ache cost user ta had but although ended strong tough durable absolutely new a little a bit thought slightly picked though quick fix refund fault love small quite helped serious significant big suggest clear obvious come arrive
""".split())

# Expanding a contraction is always grammatical; contracting is not ("where
# it is" cannot become "where it's"), so full forms are replacements only.
_REPLACE_ONLY = _REPLACE_ONLY | frozenset("""
cannot
""".split()) | frozenset([
    "showed up", "turned up", "got here",
    "it is", "that is", "there is", "i am", "i have", "i would", "i will", "we have", "we are",
    "you are", "do not", "does not", "did not", "is not", "was not", "will not", "would not",
    "have not", "has not", "could not", "can not"])

_COMPILED: Dict[str, Tuple[re.Pattern, Dict[str, Tuple[str, ...]]]] = {}


def _compiled(register: str):
    hit = _COMPILED.get(register)
    if hit is not None:
        return hit
    index: Dict[str, Tuple[str, ...]] = {}
    for group in _REGISTERS[register]:
        for phrase in group:
            if phrase.lower() in _REPLACE_ONLY:
                continue
            index.setdefault(phrase.lower(), group)
    keys = sorted(index, key=len, reverse=True)
    pat = re.compile(r"(?<![\w'#@/-])(" + "|".join(re.escape(k) for k in keys) + r")(?![\w'-])",
                     re.IGNORECASE)
    _COMPILED[register] = (pat, index)
    return _COMPILED[register]


_INTENS_RE = re.compile(r"(?<![\w'-])(is|was|feels|looks|seems|are|were|felt|looked|seemed)"
                        r" (" + "|".join(_INTENSIFIABLE) + r")\b", re.IGNORECASE)
_OPENS_WITH_CONNECTOR = re.compile(r"^[A-Z][\w']*(?: [\w']+){0,4}[,:] ")
_PLAIN_CONNECTORS = ("But ", "And ", "So ", "However", "Yet ", "Or ", "Also ", "Plus ", "Then ", "Though")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def _match_case(src: str, rep: str) -> str:
    if src.isupper() and len(src) > 1:
        # An acronym (HR, BID, SOB) maps to a phrase with its own casing.
        return rep if len(src) <= 4 else rep.upper()
    if src[:1].isupper():
        return rep[:1].upper() + rep[1:]
    return rep


def _typo(word: str, rng: np.random.Generator) -> str:
    k = int(rng.integers(3))
    i = int(rng.integers(1, len(word) - 2))
    if k == 0:
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]      # swap
    if k == 1:
        return word[:i] + word[i + 1:]                              # drop
    return word[:i] + word[i] + word[i:]                            # double


_TERSE_SUBS = [
    (re.compile(r"\bplease\b", re.I), ("pls", "plz", "please")),
    (re.compile(r"\bthanks\b", re.I), ("thx", "ty", "thanks")),
    (re.compile(r"\bthank you\b", re.I), ("ty", "thx", "thanks")),
    (re.compile(r"\bbecause\b", re.I), ("cos", "bc", "because")),
    (re.compile(r"\bwith\b", re.I), ("w/", "with")),
    (re.compile(r"\bsomething\b", re.I), ("sth", "something")),
    (re.compile(r"\babout\b", re.I), ("abt", "about")),
    (re.compile(r"\btomorrow\b", re.I), ("tmrw", "tomorrow")),
    (re.compile(r"\bpeople\b", re.I), ("ppl", "people")),
    (re.compile(r"\bdon't\b", re.I), ("dont", "don't")),
    (re.compile(r"\bcan't\b", re.I), ("cant", "can't")),
    (re.compile(r"\bI'm\b"), ("im", "I'm")),
    (re.compile(r"\bI've\b"), ("ive", "I've")),
    (re.compile(r"\bdoesn't\b", re.I), ("doesnt", "doesn't")),
    (re.compile(r"\bisn't\b", re.I), ("isnt", "isn't")),
]
_TERSE_DROP = re.compile(r"\b(I've |I have |Just |just |really |honestly |actually |Hi, |Hello, |Hey, )")
_FORMAL_OPEN = ("I am writing regarding ", "I am writing to report that ", "I would like to inform you that ",
                "Please note that ", "I wish to raise that ")
_FORMAL_EXPAND = [(re.compile(r"\b" + re.escape(a) + r"\b"), b) for a, b in [
    ("I'm", "I am"), ("I've", "I have"), ("don't", "do not"), ("can't", "cannot"), ("won't", "will not"),
    ("isn't", "is not"), ("doesn't", "does not"), ("didn't", "did not"), ("it's", "it is"), ("It's", "It is"),
    ("I'd", "I would"), ("haven't", "have not"), ("wasn't", "was not"), ("couldn't", "could not")]]


def _terse(t: str, nxt) -> str:
    t = _TERSE_DROP.sub("", t)
    for pat, opts in _TERSE_SUBS:
        t = pat.sub(lambda m: opts[int(nxt() * len(opts)) % len(opts)], t)
    if nxt() < 0.4:
        # joined with commas, the next word is mid-sentence (keep "I" and acronyms)
        t = re.sub(r"\. ([A-Z])([a-z])", lambda m: ", " + m.group(1).lower() + m.group(2), t)
    if nxt() < 0.6:
        t = t.lower()
    return t.rstrip(".")


def _formal(t: str, nxt) -> str:
    for pat, rep in _FORMAL_EXPAND:
        t = pat.sub(rep, t)
    t = t.replace("!", ".")
    if t[:1].isupper() and not t.startswith(("I ", "Dear", "Hello", "Hi")) and nxt() < 0.5:
        op = _FORMAL_OPEN[int(nxt() * len(_FORMAL_OPEN)) % len(_FORMAL_OPEN)]
        t = op + t[0].lower() + t[1:]
    return t


_SHORTHAND = [(re.compile(r"\b" + a + r"\b", re.I), opts) for a, opts in [
    ("customer", ("cx", "cust", "customer")), ("customers", ("cxs", "custs")),
    ("refunded", ("rfnd", "refunded", "refund'd")), ("refund", ("rfnd", "refund")),
    ("confirmed", ("conf'd", "confirmed", "cnfrmd")), ("with", ("w/", "with")),
    ("and", ("&", "and", "+")), ("because", ("b/c", "bc")), ("without", ("w/o",)),
    ("approximately", ("approx", "~")), ("information", ("info",)), ("account", ("acct", "a/c", "account")),
    ("message", ("msg",)), ("received", ("rcvd", "received")), ("replacement", ("repl", "replacement")),
    ("delivery", ("dlvy", "delivery")), ("number", ("no.", "#")), ("please", ("pls",)),
    ("follow up", ("f/u", "FU")), ("follow-up", ("f/u",)), ("estimated", ("est.",)),
    ("as soon as possible", ("asap", "ASAP")), ("issue", ("iss.", "issue")),
]]


def _shorthand(t: str, nxt) -> str:
    for pat, opts in _SHORTHAND:
        t = pat.sub(lambda m: opts[int(nxt() * len(opts)) % len(opts)] if nxt() < 0.7 else m.group(0), t)
    return t


def _bullets(t: str) -> str:
    parts = [p.strip() for p in _SENT_SPLIT.split(t) if p.strip()]
    if len(parts) < 2:
        return t
    return "\n".join(f"- {p.rstrip('.')}" for p in parts)


def vary(texts: Sequence[str], rng: np.random.Generator, register: str = "casual",
         rate: Optional[float] = None, short: bool = False, styles: bool = True) -> List[str]:
    """Reword ``texts`` with the variation people's writing has.

    ``rate`` is the chance each matched phrase is swapped for another member
    of its group (default 0.75 casual, 0.6 business, 0.5 clinical, 0.4 product).
    ``short``: subject lines and titles. Word swaps only, no writing styles,
    sentence markers or typos, which would turn a title into a sentence.
    None and empty values pass through unchanged."""
    pat, index = _compiled(register)
    if rate is None:
        rate = {"casual": 0.75, "business": 0.6, "clinical": 0.5, "patient": 0.5}.get(register, 0.55)
    casual = register == "casual"
    out: List[str] = []
    for text in texts:
        if not isinstance(text, str) or not text:
            out.append(text)
            continue
        draws = iter(rng.random(64).tolist())

        def nxt() -> float:
            try:
                return next(draws)
            except StopIteration:
                return float(rng.random())

        def swap(m: re.Match) -> str:
            src = m.group(0)
            if nxt() >= rate:
                return src
            group = index[src.lower()]
            rep = group[int(nxt() * len(group)) % len(group)]
            return _match_case(src, rep)

        t = pat.sub(swap, text)
        if casual or register == "business":
            t = _INTENS_RE.sub(lambda m: (f"{m.group(1)} {_INTENSIFIERS[int(nxt() * len(_INTENSIFIERS)) % len(_INTENSIFIERS)]} {m.group(2)}"
                                          if nxt() < 0.3 else m.group(0)), t)
        if short:
            out.append(_fix_articles(t))
            continue
        style = nxt() if (casual and styles) else 1.0
        if style < 0.12:
            out.append(_fix_articles(_terse(t, nxt)))
            continue
        if style < 0.24:
            out.append(_fix_articles(_formal(t, nxt)))
            continue
        if casual and styles:
            parts = _SENT_SPLIT.split(t)
            for j in range(len(parts)):
                if (j > 0 and nxt() < 0.12 and parts[j][:1].isupper() and not parts[j].startswith("I ")
                        and not _OPENS_WITH_CONNECTOR.match(parts[j])
                        and not parts[j].startswith(_PLAIN_CONNECTORS)):
                    mk = _MARKERS[int(nxt() * len(_MARKERS)) % len(_MARKERS)]
                    parts[j] = mk + parts[j][0].lower() + parts[j][1:]
            t = " ".join(parts)
        if casual:
            r = nxt()
            if r < 0.05:
                t = t[0].lower() + t[1:]
            elif r < 0.12 and t.endswith("."):
                t = t[:-1]
            elif r < 0.15 and t.endswith("."):
                t = t[:-1] + "!"
            r2 = nxt()
            if r2 < 0.05:
                t = re.sub(r"\bI\b", "i", t)
            elif r2 < 0.08:
                t = t.rstrip(".!") + " " + _EMOJI[int(nxt() * len(_EMOJI)) % len(_EMOJI)]
            elif r2 < 0.13:
                t = re.sub(r"\. (?=[A-Za-z])", lambda m: "... " if nxt() < 0.5 else m.group(0), t, count=1)
            if nxt() < 0.18:
                words = t.split(" ")
                cand = [i for i, w in enumerate(words) if len(w) >= 6 and w.isalpha() and w.islower()]
                if cand:
                    i = cand[int(nxt() * len(cand)) % len(cand)]
                    words[i] = _typo(words[i], rng)
                    t = " ".join(words)
        if not short and register in ("casual", "business", "clinical"):
            t = _front_adjuncts(t, nxt)
        if register == "business":
            st = nxt()
            if st < 0.2:
                t = _shorthand(t, nxt)
            elif st < 0.28:
                t = _bullets(t)
        if register == "business" and nxt() < 0.15:
            mk = _BUSINESS_MARKERS[int(nxt() * len(_BUSINESS_MARKERS)) % len(_BUSINESS_MARKERS)]
            if mk:
                lower_ok = t[:1].isupper() and t[1:2].islower() and t[:2] != "I "
                t = mk + (t[0].lower() + t[1:] if lower_ok else t)
        out.append(_fix_articles(t))
    return out


_TRAILING_ADJUNCT = re.compile(
    r"^([A-Z][^.!?;:]{8,}?) ((?:on|at|in|after|before|since|during|by) "
    r"[^,.!?;:]{3,40})([.!?])$")
# Only time and date phrases move: "waiting on a reply" is not an adjunct.
_TIMEY = re.compile(r"\d|\b(Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day|\b(January|February|March|April|May|"
                    r"June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|"
                    r"Aug|Sep|Oct|Nov|Dec)\b|\b(morning|afternoon|evening|week|weekend|month|year|"
                    r"spring|summer|autumn|winter|yesterday|today|tonight|Christmas|holidays?)\b")


def _front_adjuncts(t: str, nxt, p: float = 0.3) -> str:
    """"Customer approved the quote on 3 May." -> "On 3 May, customer approved
    the quote." Writers move time and place phrases around; templates do not."""
    parts = _SENT_SPLIT.split(t)
    for j, sent in enumerate(parts):
        m = _TRAILING_ADJUNCT.match(sent)
        if m and _TIMEY.search(m.group(2)) and nxt() < p:
            head, adj, end = m.groups()
            first = head.split(" ", 1)[0]
            keep_case = first in ("I",) or (first[1:2].isupper()) or first in _PROPER_HINTS
            head = head if keep_case else head[0].lower() + head[1:]
            parts[j] = adj[0].upper() + adj[1:] + ", " + head + end
    return " ".join(parts)


_PROPER_HINTS = frozenset()

_ARTICLE = re.compile(r"\b([Aa]n?) ([A-Za-z][\w'-]*)")
_AN_EXCEPT = ("uni", "use", "user", "usual", "euro", "one", "once", "eu")
_A_EXCEPT = ("hour", "honest", "heir", "honour", "honor")


def _fix_articles(t: str) -> str:
    """"an new one" -> "a new one" after a swap changed the next word."""
    def fix(m: re.Match) -> str:
        art, word = m.group(1), m.group(2)
        w = word.lower()
        if word.isupper() and len(word) > 1:
            return m.group(0)          # acronyms: "an SSO", "a URL" - leave as written
        vowel = w[0] in "aeiou" and not w.startswith(_AN_EXCEPT)
        vowel = vowel or w.startswith(_A_EXCEPT)
        want = "an" if vowel else "a"
        if art.lower() == want:
            return m.group(0)
        return (want.capitalize() if art[0].isupper() else want) + " " + word
    return _ARTICLE.sub(fix, t)


def vary_keeping(texts: Sequence[str], keep: Sequence, rng: np.random.Generator,
                 register: str = "casual", **kwargs) -> List[str]:
    """``vary`` that leaves each row's ``keep`` phrase or phrases (a product
    noun, a job title, a city) exactly as written, in whatever case."""
    held, found_all = [], []
    for t, k in zip(texts, keep):
        ks = [x for x in ([k] if isinstance(k, str) else list(k or [])) if x]
        found = re.findall("|".join(re.escape(x) for x in sorted(ks, key=len, reverse=True)), t, re.I) if ks else []
        for j, f in enumerate(found[:8]):
            t = t.replace(f, chr(j + 1), 1)
        held.append(t)
        found_all.append(found[:8])
    out = []
    for t, found in zip(vary(held, rng, register, **kwargs), found_all):
        for j, f in enumerate(found):
            t = t.replace(chr(j + 1), f, 1)
        out.append(t)
    return out
