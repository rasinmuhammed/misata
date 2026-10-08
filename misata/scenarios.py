"""Row-level scenarios: one latent story per row, rendered into every column.

A product's name, description, brand and price band, or a ticket's subject,
description, priority and resolution, describe ONE thing. Drawn column by
column from independent pools they describe different things: a linen dress
"lightweight and portable with a modern aesthetic", a ticket about a double
charge whose resolution resets a password. This module draws the thing first
(a :class:`ProductFrame` or :class:`TicketFrame`) and renders each column from
it, so the columns agree by construction.

Everything here is fictional and offline: brands, products and support
issues are written for Misata, and no row of any real dataset is used.

Capacity, not pool size, is what keeps a large table from repeating itself.
Names and descriptions are compositions (brand x attribute x noun x variant;
opener x features x use x spec), so a 100,000-row catalogue does not read the
same sentence every few rows. ``tests/test_scenarios.py`` enumerates the
grammars and gates their capacity.
"""
from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence

import numpy as np


# ── shared helpers ───────────────────────────────────────────────────────────

def zipf_weights(n: int, s: float = 1.0, q: float = 2.0) -> np.ndarray:
    """Zipf-Mandelbrot weights ``(k + q) ** -s`` for ranks 1..n, normalised.

    Real label columns (cities, employers, brands, job titles) are skewed: a
    few values cover much of the table and a long tail covers the rest. A
    uniform draw over a list is the most common tell in synthetic text."""
    if n <= 0:
        return np.array([])
    w = (np.arange(1, n + 1) + q) ** -float(s)
    return w / w.sum()


def zipf_choice(rng: np.random.Generator, pool: Sequence, size: int, *,
                s: float = 1.0, q: float = 2.0, key: Optional[str] = None,
                ranked: bool = False) -> np.ndarray:
    """Draw ``size`` values from ``pool`` with Zipf-Mandelbrot weights.

    ``ranked=True`` means the pool is already in popularity order (cities by
    population): rank follows list order. Otherwise ``key`` seeds a stable
    permutation, so which value is common is fixed per column, not always the
    first one written in the list."""
    pool = list(pool)
    if not pool:
        return np.array([], dtype=object)
    order = np.arange(len(pool))
    if not ranked:
        perm = np.random.default_rng(zlib.crc32(str(key or pool[0]).encode("utf-8")))
        order = perm.permutation(len(pool))
    idx = rng.choice(len(pool), size=size, p=zipf_weights(len(pool), s, q))
    arr = np.empty(len(pool), dtype=object)
    arr[:] = pool
    return arr[order[idx]]


_POPULATION: Optional[Dict[str, Dict[str, int]]] = None


def city_populations(country: str) -> Dict[str, int]:
    """GeoNames populations for the cities Misata's own lists name in
    ``country`` (CC BY 4.0; see DATA-PROVENANCE.md). Empty when unknown."""
    global _POPULATION
    if _POPULATION is None:
        try:
            import json
            from importlib.resources import files
            raw = files("misata").joinpath("data_packs/city_population.json").read_text("utf-8")
            _POPULATION = json.loads(raw)["populations"]
        except Exception:
            _POPULATION = {}
    return _POPULATION.get(str(country), {})


def population_choice(rng: np.random.Generator, pool: Sequence[str], size: int,
                      country: str) -> np.ndarray:
    """Cities in proportion to how many people live there.

    Falls back to a Zipf curve over the list order (lists run largest first)
    when the country has no population data, and gives a city missing from
    the data half the smallest known population."""
    pool = list(dict.fromkeys(pool))
    pops = city_populations(country)
    known = [pops[c] for c in pool if c in pops]
    if len(known) < max(3, len(pool) // 2):
        return zipf_choice(rng, pool, size, s=0.95, q=1.5, ranked=True)
    floor = min(known) / 2
    w = np.array([float(pops.get(c, floor)) for c in pool])
    # Sub-linear: online customers concentrate in big cities less than
    # residents do (suburbs, smaller towns), so weight by population^0.8.
    w = w ** 0.8
    arr = np.empty(len(pool), dtype=object)
    arr[:] = pool
    return arr[rng.choice(len(pool), size=size, p=w / w.sum())]


_SLOT = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?::(\d+)-(\d+))?\}")


_CHOICE = re.compile(r"\(\(([^()]*)\)\)")
_OPTION = re.compile(r"\[\[([^\[\]]*)\]\]")


def _inline(template: str, rng: np.random.Generator) -> str:
    """((a|b|c)) picks one, [[...]] is kept half the time; innermost first."""
    while "((" in template or "[[" in template:
        m = _OPTION.search(template) or _CHOICE.search(template)
        if m is None:
            break
        if m.re is _OPTION:
            rep = m.group(1) if rng.random() < 0.5 else ""
        else:
            opts = m.group(1).split("|")
            rep = opts[int(rng.integers(len(opts)))]
        template = template[:m.start()] + rep + template[m.end():]
    return re.sub(r"  +", " ", template).replace(" .", ".").replace(" ,", ",")


def _fill(template: str, rng: np.random.Generator, slots: Dict[str, str]) -> str:
    """Fill ``{name}`` from ``slots`` and ``{n:lo-hi}`` with an integer, after
    resolving inline ((a|b)) choices and [[optional]] parts."""
    if "((" in template or "[[" in template:
        template = _inline(template, rng)
    def sub(m: re.Match) -> str:
        name, lo, hi = m.group(1), m.group(2), m.group(3)
        if lo is not None:
            return str(int(rng.integers(int(lo), int(hi) + 1)))
        if name not in slots:
            raise KeyError(f"scenario slot '{name}' is not defined")
        return str(slots[name])
    return _SLOT.sub(sub, template)


def _pick(rng: np.random.Generator, pool):
    """One entry of a list; ``rng.choice`` converts the list to an array on
    every call, which dominated per-row rendering."""
    return pool[int(rng.integers(len(pool)))]


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def _clean_values(values: Optional[Sequence], size: int) -> Optional[List[str]]:
    if values is None:
        return None
    out = []
    for v in list(values)[:size]:
        t = "" if v is None else str(v).strip()
        out.append("" if t.lower() in ("nan", "none", "nat", "<na>") else t)
    if len(out) < size:
        out += [""] * (size - len(out))
    return out


# ── products ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ProductFamily:
    key: str
    label: str                 # display category when none is declared
    nouns: Sequence[str]
    attrs: Sequence[str]
    materials: Sequence[str]
    features: Sequence[str]    # noun phrases with an article: "a padded strap"
    uses: Sequence[str]
    specs: Sequence[str]       # complete sentences, may carry {n:lo-hi}
    variants: Sequence[str]
    brands: Sequence[str]
    price_median: float        # USD, for ordering prices across categories
    material_in_name: bool = False


_F = ProductFamily
PRODUCT_FAMILIES: Dict[str, ProductFamily] = {f.key: f for f in [
    _F("electronics", "Electronics",
       ["Wireless Headphones", "Bluetooth Speaker", "Laptop Stand", "Mechanical Keyboard",
        "Gaming Mouse", "4K Monitor", "Webcam", "Desk Lamp", "Power Bank", "Wireless Earbuds",
        "Smart Plug", "Action Camera", "Tablet", "Smartwatch", "E-Reader", "Dash Cam",
        "Portable SSD", "Wi-Fi Router", "USB-C Hub", "Soundbar", "Phone Charger",
        "Fitness Tracker", "Smart Thermostat", "Video Doorbell", "Microphone",
        "Graphics Tablet", "Projector", "Security Camera", "Smart Speaker", "Bluetooth Turntable", "Mesh Wi-Fi System", "Mirrorless Camera", "Drone", "E-Ink Tablet", "Noise Machine", "Smart Bulb", "Ring Light", "Gaming Headset", "Streaming Stick", "Wireless Charger", "Label Printer", "Air Quality Monitor", "Electric Scooter"],
       ["Compact", "Portable", "Ultra-Slim", "Noise-Cancelling@Headphones|Earbuds|Microphone", "Rechargeable", "Smart",
        "Wireless", "Pro", "Waterproof@Speaker|Camera|Earbuds|Smartwatch|Tracker", "Foldable@Stand|Headphones|Keyboard|Lamp", "Fast-Charging@Charger|Power Bank|Hub", "Low-Latency@Headphones|Earbuds|Mouse|Keyboard|Microphone|Webcam"],
       ["anodised aluminium@Stand|Hub|Monitor|Lamp|Tablet|SSD|Speaker|Keyboard|Microphone", "recycled plastic", "matte polycarbonate", "brushed steel@Stand|Lamp|Speaker|Smartwatch|Microphone",
        "soft-touch silicone@Earbuds|Smartwatch|Tracker|Mouse|Speaker"],
       ["a {n:10-60}-hour battery@Headphones|Speaker|Earbuds|Power Bank|Smartwatch|Tracker|Microphone|Camera|Reader", "USB-C fast charging@Headphones|Speaker|Earbuds|Power Bank|Smartwatch|Tracker|Charger|Tablet|Reader|Mouse|Microphone|Camera", "Bluetooth 5.3@Headphones|Speaker|Earbuds|Keyboard|Mouse|Smartwatch|Tracker|Soundbar", "a braided cable@Charger|Power Bank|Hub|Keyboard|Mouse|Microphone",
        "a magnetic mount@Camera|Charger|Lamp|Webcam|Dash", "voice-assistant support@Speaker|Smart|Soundbar|Doorbell|Thermostat", "an app for firmware updates@Smart|Router|Camera|Doorbell|Thermostat|Headphones|Earbuds|Speaker|Smartwatch|Tracker|Soundbar",
        "a fold-flat hinge@Stand|Headphones|Lamp|Tablet", "dual microphones@Headphones|Earbuds|Webcam|Speaker|Doorbell|Camera", "an IPX{n:4-7} rating@Speaker|Earbuds|Camera|Smartwatch|Tracker|Doorbell", "a carry pouch@Headphones|Earbuds|SSD|Speaker|Power Bank|Mouse|Camera",
        "((a {n:1-3}-year warranty|((a year|two years|three years)) of cover|a {n:1-3}-year manufacturer warranty|free repairs for ((a year|two years|three years))))", "((automatic standby|an eco power mode|auto power-off after {n:10-30} minutes|a low-power sleep mode))", "multipoint pairing@Headphones|Earbuds|Keyboard|Mouse|Speaker",
        "a backlit control panel@Keyboard|Router|Thermostat|Projector|Soundbar", "a {n:2-4}-port design@Hub|Charger|Power Bank|Router", "a {n:2-5}K sensor@Camera|Webcam|Drone|Doorbell", "{n:2-6} hours of playback@Speaker|Headphones|Earbuds|Turntable|Soundbar", "a {n:10-30}W output@Speaker|Charger|Soundbar|Light", "a matte anti-glare screen@Tablet|Monitor|Reader", "{n:16-64} GB of storage@Tablet|Camera|Smartwatch", "an auto-dimming display@Smartwatch|Thermostat|Monitor", "a fold-out kickstand@Tablet|Speaker|Stand", "Matter and Alexa support@Smart|Bulb|Plug|Thermostat|Speaker", "a {n:30-90}-minute flight time@Drone", "a spill-resistant design@Keyboard|Mouse|Speaker"],
       ["working from home", "long commutes", "travel", "gaming sessions", "video calls",
        "a small desk", "streaming", "the home office", "students", "content creators"],
       ["Charges fully in about {n:1-3} hours.@Headphones|Speaker|Earbuds|Power Bank|Smartwatch|Tracker|Camera|Mouse", "Weighs {n:90-900} g.@Headphones|Speaker|Mouse|Keyboard|Webcam|Power Bank|Earbuds|Plug|Action Camera|Tablet|Smartwatch|E-Reader|Dash Cam|SSD|Router|Hub|Charger|Tracker|Thermostat|Doorbell|Microphone|Security Camera|Bulb|Headset|Stick|Mirrorless|Drone|Noise Machine|Label Printer", "Weighs {n:2-9} kg.@4K Monitor|Projector|Soundbar|Turntable", "Weighs {n:11-19} kg.@Scooter",
        "((Works|Compatible)) with ((Windows, macOS, iOS and Android|Mac and PC|iPhone and Android|most laptops and phones)).@Keyboard|Mouse|Webcam|Hub|SSD|Headphones|Earbuds|Microphone|Tablet|Speaker", "((Cable|USB-C cable|Charging cable)) and ((quick-start guide|manual|setup card)) ((included|in the box|supplied)).",
        "((Gets|Supports|Receives)) ((firmware|software)) updates ((over|through|via)) the ((companion|free)) app.@Smart|Router|Camera|Doorbell|Thermostat|Headphones|Earbuds|Speaker|Smartwatch|Tracker|Soundbar", "Plug-and-play, no drivers needed.@Keyboard|Mouse|Webcam|Hub|SSD|Microphone",
        "Ships with a {n:1-2} m USB-C cable.@Keyboard|Mouse|Webcam|Hub|SSD|Microphone|Headphones|Speaker|Power Bank|Camera"],
       ["- Black", "- White", "- Graphite", "- Silver", "2nd Gen", "Mini", "Max", "Lite",
        "(2025)", "128GB@Tablet|SSD|Smartwatch|Reader", "256GB@Tablet|SSD|Reader", "- Midnight Blue"],
       ["Voltra", "Nexion", "Aurelo", "Kestrel", "Lumio", "Orbix", "Zentra", "Sonaro",
        "Helix", "Quill & Bolt", "Arcwave", "Pixelon"],
       79.0),
    _F("clothing", "Clothing",
       ["Rain Jacket", "Oxford Shirt", "Chino Trousers", "V-Neck Sweater", "Yoga Leggings",
        "Summer Dress", "Running Shorts", "Puffer Jacket", "Graphic Tee", "Straight-Leg Jeans",
        "Midi Skirt", "Hoodie", "Blazer", "Cargo Shorts", "Scarf", "Beanie", "Polo Shirt",
        "Cardigan", "Joggers", "Denim Jacket", "Wrap Dress", "Fleece Pullover", "Tank Top",
        "Overshirt", "Trench Coat", "Sweatpants", "Quilted Gilet", "Linen Shirt", "Wide-Leg Trousers", "Knitted Vest", "Utility Jacket", "Rugby Shirt", "Pleated Skirt", "Shacket", "Turtleneck", "Swim Shorts", "Bomber Jacket", "Corduroy Trousers", "Lounge Set", "Shirt Dress", "Wool Coat"],
       ["Classic", "Relaxed", "Slim-Fit", "Lightweight", "Oversized", "Cropped", "Everyday",
        "Waterproof@Jacket|Coat", "Stretch@Jeans|Trousers|Leggings|Chino|Shorts|Joggers", "Vintage-Wash@Jeans|Tee|Jacket|Hoodie", "Tailored@Blazer|Trousers|Shirt|Coat", "Ribbed@Sweater|Beanie|Tank|Cardigan|Dress"],
       ["organic cotton", "merino wool@Sweater|Beanie|Scarf|Cardigan|Pullover|Tee", "linen@Shirt|Dress|Trousers|Shorts|Overshirt|Skirt|Blazer", "recycled polyester@Jacket|Leggings|Shorts|Puffer|Coat|Tank|Pullover", "French terry@Hoodie|Joggers|Sweatpants|Pullover", "cotton twill@Chino|Trousers|Shorts|Overshirt|Trench|Jacket|Blazer", "TENCEL lyocell@Dress|Shirt|Skirt|Tee|Tank", "brushed fleece@Pullover|Hoodie|Joggers|Jacket|Sweatpants", "stretch denim@Jeans|Jacket|Skirt|Shorts", "cashmere blend@Sweater|Scarf|Beanie|Cardigan|Coat"],
       ["a relaxed fit@Shirt|Tee|Hoodie|Sweater|Trousers|Jeans|Joggers|Cardigan|Dress|Overshirt|Pullover", "((reinforced seams|double-stitched seams|taped seams|flat-felled seams))", "side pockets@Jacket|Trousers|Shorts|Hoodie|Joggers|Dress|Coat|Cardigan|Skirt|Jeans|Sweatpants|Blazer",
        "a two-way zip@Jacket|Hoodie|Pullover|Coat", "an adjustable hood@Jacket|Hoodie|Coat", "a soft brushed interior@Hoodie|Joggers|Sweatpants|Pullover|Jacket|Leggings", "flatlock stitching@Leggings|Shorts|Tank|Tee|Joggers",
        "a drawstring waist@Shorts|Joggers|Sweatpants|Trousers|Leggings", "a dropped shoulder@Tee|Hoodie|Sweater|Pullover|Cardigan|Shirt|Overshirt", "a hidden phone pocket@Leggings|Shorts|Joggers|Jacket|Sweatpants",
        "moisture-wicking fabric@Leggings|Shorts|Tank|Tee|Joggers|Polo", "a curved hem@Shirt|Tee|Overshirt|Tank|Polo", "ribbed cuffs@Sweater|Hoodie|Cardigan|Joggers|Pullover|Sweatpants|Jacket", "a {n:2-4}-button cuff@Shirt|Blazer|Coat", "a contrast lining@Jacket|Coat|Blazer|Gilet", "a regular rise@Trousers|Jeans|Chino", "an elasticated back@Trousers|Skirt|Joggers|Shorts", "a stand-up collar@Jacket|Coat|Gilet|Turtleneck", "patch pockets@Shirt|Jacket|Shacket|Overshirt", "a longline cut@Cardigan|Coat|Hoodie|Shirt", "((tonal stitching|contrast topstitching|a woven label|a hanging loop))", "a {n:60-80} cm length@Dress|Skirt|Coat", "a back vent@Blazer|Coat"],
       ["everyday wear", "the office", "weekend trips", "layering in autumn", "warm evenings",
        "the gym@Leggings|Shorts|Tank|Joggers|Hoodie|Tee", "travel", "rainy commutes@Jacket|Coat", "lounging at home@Hoodie|Joggers|Sweatpants|Pullover|Cardigan|Tee"],
       ["((Machine wash|Wash)) ((cold|at 30°C|at 40°C)), ((tumble dry low|line dry|dry flat)).", "((Hand wash|Gentle wash|Hand wash only)) ((recommended|is best|to keep it looking new)).",
        "((True to size|Fits true to size|Runs true to size)); ((size up|go a size up|take the next size)) for a ((looser|relaxed|roomier)) fit.", "Model is {n:170-190} cm and wears a size M.@Jacket|Shirt|Trousers|Sweater|Dress|Tee|Jeans|Hoodie|Blazer|Cardigan|Coat|Polo",
        "((Pre-shrunk|Pre-washed|Garment-washed))((.| for a soft feel.| so it keeps its size.))", "((Made|Sewn|Knitted)) in ((Portugal|Turkey|Italy|Lithuania|Peru|the UK)).", "((Made|Produced|Manufactured)) ((responsibly |))in ((Vietnam|India|Bangladesh|China|Cambodia)).", "Dry clean only.@Blazer|Coat|Cashmere"],
       ["- Navy", "- Black", "- Olive", "- Heather Grey", "- Ivory", "- Rust", "- Sage",
        "- Size S", "- Size M", "- Size L", "- Size XL"],
       ["Northfold", "Marlowe", "Juniper & Co", "Aster", "Fennick", "Calder", "Wren",
        "Solace", "Halden", "Common Thread"],
       45.0, material_in_name=True),
    _F("footwear", "Shoes",
       ["Running Shoes", "Chelsea Boots", "Canvas Sneakers", "Hiking Boots", "Loafers",
        "Slides", "Sandals", "Trail Runners", "High-Top Sneakers", "Ankle Boots",
        "Slip-On Shoes", "Court Shoes", "Clogs", "Walking Shoes"],
       ["Lightweight", "Waterproof@Boots|Hiking|Trail|Walking", "Cushioned", "Classic", "Low-Profile", "Grippy",
        "Everyday", "Wide-Fit", "Breathable"],
       ["full-grain leather@Boots|Loafers|Shoes|Sandals|Sneakers", "suede@Boots|Loafers|Shoes|Sneakers", "recycled mesh@Running|Trail|Walking|Sneakers", "canvas@Sneakers|Slip-On|High-Top", "vegan leather", "knit@Running|Sneakers|Slip-On|Walking"],
       ["a cushioned midsole", "a rubber outsole", "a padded collar", "a removable insole",
        "a pull tab@Boots|Sneakers|Runners|Shoes", "a reinforced toe cap", "a lugged sole@Hiking|Trail|Boots", "a breathable lining"],
       ["daily runs@Running|Trail", "city walking", "long days on your feet", "light trails@Hiking|Trail|Walking",
        "the office@Loafers|Chelsea|Court|Ankle", "summer weekends"],
       ["Fits true to size.", "Half sizes available.", "Wipe clean with a damp cloth.",
        "Heel drop {n:4-10} mm.@Running|Trail|Walking"],
       ["- Size 8", "- Size 9", "- Size 10", "- Size 11", "- White", "- Black", "- Tan",
        "- Chestnut"],
       ["Stride", "Fennick", "Trailborn", "Halden", "Cobble & Co", "Northfold"],
       85.0, material_in_name=True),
    _F("home", "Home",
       ["Throw Blanket", "Sheet Set", "Memory Foam Pillow", "Aroma Diffuser", "Air Purifier",
        "Cordless Vacuum", "Table Lamp", "Bath Towel Set", "Duvet Cover", "Wall Mirror",
        "Storage Basket", "Scented Candle", "Blackout Curtains", "Area Rug", "Photo Frame",
        "Laundry Hamper", "Doormat", "Shower Curtain", "Cushion Cover", "Wall Clock", "Linen Napkins", "Plant Pot", "Bath Mat", "Bedspread", "Floor Cushion", "Wall Art Print", "Bud Vase", "Throw Pillow", "Jute Rug", "Coat Hooks", "Room Spray", "Draught Excluder", "Weighted Blanket", "Mattress Topper", "Hanging Planter"],
       ["Soft@Blanket|Towel|Pillow|Throw|Cushion|Sheet|Duvet|Rug", "Minimalist", "Handwoven@Rug|Basket|Throw|Blanket|Doormat", "Washable@Rug|Pillow|Cushion|Blanket", "Compact@Vacuum|Purifier|Diffuser|Lamp", "Oversized@Throw|Blanket|Mirror|Clock|Pillow", "Quiet@Vacuum|Purifier|Diffuser|Clock", "Modern", "Rustic@Frame|Clock|Mirror|Basket|Candle|Lamp", "Plush@Blanket|Throw|Rug|Pillow|Towel"],
       ["cotton percale@Sheet|Duvet|Pillow", "linen@Sheet|Duvet|Cushion|Curtain|Throw|Blanket", "jute@Rug|Basket|Doormat|Hamper", "bamboo@Towel|Basket|Hamper|Frame|Sheet", "ceramic@Lamp|Diffuser|Candle", "oak@Frame|Mirror|Clock|Lamp", "recycled glass@Candle|Lamp|Diffuser", "velvet@Cushion|Curtain|Throw", "wool@Throw|Blanket|Rug|Cushion", "recycled plastic@Vacuum|Purifier|Hamper|Diffuser|Curtain", "organic cotton@Towel|Blanket|Throw|Sheet|Rug", "natural fibres", "recycled cotton", "stoneware", "rattan", "FSC-certified wood"],
       ["((a neutral colourway|a muted palette|an earthy tone|a soft, natural finish))", "((easy-care materials|wipe-clean surfaces|fade-resistant fibres|a stain-resistant finish))", "((a {n:1-5}-year guarantee|((a year|two years|three years|five years)) of cover|a no-quibble {n:1-5}-year guarantee))", "a neutral finish@Lamp|Mirror|Frame|Clock|Basket|Hamper|Candle|Diffuser", "hidden fixings@Mirror|Clock|Frame|Curtains", "a non-slip base@Rug|Doormat|Lamp|Basket|Hamper|Board|Scale|Mixer|Blender|Bed|Bowl", "a removable cover@Pillow|Cushion|Duvet|Hamper",
        "a hand-finished edge@Rug|Towel|Blanket|Throw|Mirror|Frame|Doormat|Basket|Cushion", "a timer function@Diffuser|Purifier|Lamp", "a whisper-quiet motor@Vacuum|Purifier|Diffuser",
        "a washable filter@Vacuum|Purifier", "pre-drilled holes@Mirror|Clock|Frame", "a soft-touch weave@Blanket|Towel|Sheet|Rug|Cushion|Duvet|Throw", "a {n:200-600} thread count@Sheet|Duvet|Pillow", "a {n:3-10} kg weight@Blanket", "{n:30-60} hours of burn time@Candle", "a zip closure@Cushion|Pillow|Duvet", "an anti-slip backing@Rug|Mat|Doormat", "a drainage hole@Pot|Planter", "a reversible design@Rug|Blanket|Duvet|Throw", "{n:2-6} hanging hooks@Hooks|Rack", "a fade-resistant print@Print|Art|Curtains", "a quilted top@Topper|Bedspread"],
       ["the living room", "small flats", "guest rooms", "everyday use", "the bedroom",
        "entryways", "rentals"],
       ["Machine washable at 40°C.@Blanket|Sheet|Towel|Duvet|Cushion|Curtain|Throw|Pillow", "((Spot clean|Sponge clean|Spot-clean)) ((only|with mild soap|where needed)).@Rug|Cushion|Throw|Curtains|Basket|Doormat|Pillow|Hamper", "Assembly takes about {n:5-30} minutes.@Mirror|Hamper|Lamp|Clock|Rack",
        "Measures {n:60-240} x {n:90-300} cm.@Rug|Curtain|Throw|Blanket|Bedspread|Topper|Shower Curtain", "Measures {n:20-60} x {n:20-60} cm.@Cushion|Pillow|Print|Mirror|Frame|Bath Mat|Doormat|Clock", "Covered by a {n:1-5}-year warranty."],
       ["- Set of 2", "- Set of 4", "- Large", "- Small", "- Natural", "- Charcoal",
        "- Oatmeal", "- Queen", "- King"],
       ["Hearthwell", "Oakline", "Nordhaus", "Casa Verde", "Linden", "Tidewater",
        "Ember & Ash", "Kinfolk Home"],
       39.0, material_in_name=True),
    _F("kitchen", "Kitchen",
       ["Cast Iron Skillet", "Knife Set", "Cookware Set", "Cutting Board", "French Press",
        "Pour-Over Kettle", "Dinnerware Set", "Food Storage Containers", "Baking Mat",
        "Kitchen Scale", "Stand Mixer", "Blender", "Air Fryer", "Toaster", "Coffee Grinder",
        "Spice Rack", "Dutch Oven", "Water Bottle", "Travel Mug", "Salad Spinner", "Chopping Board Set", "Pasta Maker", "Garlic Press", "Measuring Cups", "Mixing Bowls", "Pizza Stone", "Milk Frother", "Cocktail Shaker", "Bread Bin", "Utensil Set", "Wok", "Tea Infuser", "Oven Gloves", "Rolling Pin", "Spiraliser"],
       ["Non-Stick@Skillet|Cookware|Mat|Air Fryer", "Pre-Seasoned@Skillet|Dutch Oven", "Stainless@Knife|Kettle|Bottle|Mug|Rack|Cookware", "Insulated@Bottle|Mug", "Compact", "Professional@Knife|Mixer|Blender|Grinder|Cookware", "Stackable@Containers|Dinnerware", "Leak-Proof@Containers|Bottle|Mug", "Digital@Scale|Air Fryer|Toaster|Kettle"],
       ["18/10 stainless steel@Knife|Cookware|Kettle|Bottle|Mug|Rack|Toaster|Press|Mixer|Grinder|Scale|Spinner", "cast iron@Skillet|Dutch Oven", "acacia wood@Board|Rack", "borosilicate glass@Containers|Press|Kettle|Bottle", "stoneware@Dinnerware|Mug|Dutch Oven", "BPA-free plastic@Containers|Spinner|Bottle|Blender|Air Fryer", "carbon steel@Knife|Skillet", "enamelled cast iron@Dutch Oven|Skillet", "silicone@Mat|Rack|Containers", "food-grade stainless steel", "heat-resistant glass", "beech wood", "silicone"],
       ["((a {n:1-10}-year guarantee|((two years|five years|ten years)) of cover|a lifetime guarantee))", "((easy-clean surfaces|dishwasher-safe parts|a wipe-clean finish|a non-stick coating))", "((a compact footprint|a slim profile|stackable storage|a space-saving design))", "stay-cool handles@Skillet|Cookware|Dutch Oven|Kettle", "a non-slip base@Board|Scale|Mixer|Blender|Rack|Spinner|Grinder", "a pour spout@Kettle|Press|Skillet|Blender|Cookware", "a tempered glass lid@Cookware|Dutch Oven|Skillet",
        "an induction-ready base@Skillet|Cookware|Dutch Oven|Kettle", "measurement markings@Blender|Containers|Kettle|Press|Bottle|Mixer", "a locking lid@Containers|Bottle|Mug|Blender|Lunch",
        "{n:3-12} speed settings@Mixer|Blender|Grinder", "a removable blade@Blender|Grinder", "an auto shut-off@Kettle|Air Fryer|Toaster|Blender|Mixer|Grinder", "a {n:3-7}-piece set@Set|Bowls|Cups|Utensil", "a {n:20-35} cm diameter@Wok|Skillet|Stone|Bowls", "a heat-proof silicone grip@Gloves|Utensil|Wok", "{n:6-9} thickness settings@Pasta|Spiraliser", "a bamboo lid@Bin|Containers", "a built-in strainer@Shaker|Infuser", "a fine-mesh basket@Infuser|Spinner", "a one-touch froth button@Frother", "nesting storage@Bowls|Cups|Containers|Set"],
       ["weeknight cooking", "small kitchens", "meal prep", "baking@Mat|Mixer|Scale|Dutch Oven", "camping@Bottle|Mug|Skillet|Press|Kettle",
        "the morning coffee@Press|Kettle|Grinder|Mug", "entertaining"],
       ["Dishwasher safe.@Board|Dinnerware|Containers|Mat|Bottle|Mug|Spinner|Cookware", "Hand wash to keep the finish.", "Oven safe to {n:200-260}°C.@Skillet|Dutch Oven|Cookware|Mat|Dinnerware",
        "Holds {n:1-6} litres.@Dutch Oven|Kettle|Blender|Air Fryer|Mixer|Containers|Cookware", "Works on gas, electric and induction hobs.@Skillet|Cookware|Dutch Oven|Kettle"],
       ["- 10\"@Skillet", "- 12\"@Skillet", "- 6-Piece@Set", "- 12-Piece@Set", "- Black", "- Sage", "- Cream",
        "- 1.5L@Kettle|Blender|Containers|Bottle", "- 500ml@Bottle|Mug|Containers"],
       ["Hearthwell", "Copperleaf", "Kitchenry", "Old Mill", "Larder & Co", "Saltbox"],
       42.0, material_in_name=True),
    _F("furniture", "Furniture",
       ["Office Chair", "Bookshelf", "Coffee Table", "Desk", "Bed Frame", "Sofa",
        "Bar Stool", "Dining Chair", "Nightstand", "TV Stand", "Shoe Rack", "Armchair",
        "Wardrobe", "Side Table"],
       ["Mid-Century", "Ergonomic@Chair|Desk", "Adjustable@Chair|Desk|Stool|Bed", "Modular", "Solid Wood@Table|Desk|Bookshelf|Bed|Nightstand|Wardrobe|Stand", "Folding@Chair|Table|Desk|Stool",
        "Minimalist", "Upholstered@Chair|Sofa|Armchair|Bed|Stool"],
       ["solid oak", "walnut veneer@Table|Desk|Bookshelf|Nightstand|Stand|Wardrobe", "powder-coated steel@Stool|Desk|Rack|Table|Bed|Chair", "rattan@Chair|Armchair|Table|Nightstand", "boucle@Sofa|Armchair|Chair|Stool", "pine@Bookshelf|Bed|Rack|Wardrobe|Nightstand"],
       ["adjustable feet", "soft-close drawers@Desk|Nightstand|TV Stand|Wardrobe|Side Table", "lumbar support@Chair|Armchair|Sofa", "a cable cut-out@Desk|TV Stand",
        "removable cushions@Sofa|Armchair|Chair|Stool", "an anti-tip kit", "{n:2-5} shelves@Bookshelf|Shoe Rack|TV Stand|Wardrobe", "a weight limit of {n:80-150} kg"],
       ["small spaces", "the home office", "living rooms", "studio flats", "dining rooms"],
       ["Assembly required; tools included.", "Ships flat-packed in {n:1-3} boxes.",
        "Wipe clean with a dry cloth.", "Measures {n:40-200} cm wide."],
       ["- Oak", "- Walnut", "- Black", "- White", "- Grey"],
       ["Nordhaus", "Oakline", "Linden", "Fernwood", "Studio Arlo"],
       189.0, material_in_name=True),
    _F("beauty", "Beauty",
       ["Vitamin C Serum", "Moisturiser", "Night Cream", "Sunscreen SPF 50",
        "Cleansing Water", "Clay Mask", "Hair Oil", "Shampoo", "Conditioner", "Lipstick",
        "Eyeshadow Palette", "Mascara", "Setting Powder", "Tinted Moisturiser",
        "Brow Pencil", "Sheet Masks", "Body Lotion", "Hand Cream", "Eye Cream",
        "Face Cleanser", "Toner", "Lip Balm", "Bronzer", "Concealer", "Face Oil", "Body Scrub", "Dry Shampoo", "Nail Polish", "Foundation", "Eyeliner", "Cleansing Balm", "Hair Mask", "Deodorant", "Primer", "Exfoliating Toner", "Retinol Serum"],
       ["Hydrating", "Brightening@Serum|Mask|Cream|Toner|Moisturiser", "Fragrance-Free", "Gentle", "Long-Wear@Lipstick|Mascara|Eyeshadow|Powder|Pencil", "Matte@Lipstick|Powder|Eyeshadow|Sunscreen", "Nourishing", "Lightweight", "Overnight@Cream|Mask|Serum"],
       ["hyaluronic acid", "niacinamide@Serum|Moisturiser|Toner|Cream", "shea butter@Cream|Lotion|Lipstick|Conditioner", "squalane", "aloe vera", "jojoba oil", "ceramides@Cream|Moisturiser|Lotion|Cleanser", "green tea extract"],
       ["((a non-greasy finish|a fast-absorbing texture|a weightless feel|a satin finish))", "a pump bottle@Serum|Moisturiser|Cleanser|Shampoo|Conditioner|Lotion|Oil|Toner", "a fresh citrus scent@Shampoo|Conditioner|Lotion|Hand Cream|Cleanser", "((no added fragrance|a barely-there scent|no essential oils|a fragrance-free formula))",
        "a recyclable tube@Cream|Sunscreen|Cleanser|Lotion|Moisturiser|Mascara", "a buildable formula@Lipstick|Eyeshadow|Mascara|Powder|Tinted|Brow", "((a travel-size option|a refill pouch|a {n:15-30} ml mini|a cabin-friendly size))", "SPF {n:15-50}@Moisturiser|Tinted|Lip|Foundation|Primer", "{n:2-12}% active ingredients@Serum|Toner|Cream", "a {n:12-24}-hour wear@Foundation|Concealer|Lipstick|Mascara|Eyeliner", "a refillable case@Lipstick|Bronzer|Powder|Palette", "{n:8-40} shades@Foundation|Concealer|Lipstick|Nail", "a dropper bottle@Serum|Oil", "((a vitamin E boost|added panthenol|a dose of ceramides|added glycerin))", "((a non-comedogenic formula|an oil-free formula|a pH-balanced formula|a microbiome-friendly base))", "a cooling applicator@Eye|Mask", "a reef-safe formula@Sunscreen|SPF"],
       ["dry skin", "sensitive skin", "daily use", "oily skin@Cleanser|Toner|Mask|Powder|Moisturiser|Sunscreen", "a morning routine", "a night routine@Cream|Serum|Mask|Oil", "all skin types"],
       ["((Dermatologist|Clinically|Independently)) tested((.| on sensitive skin.| by {n:20-80} volunteers.))", "((Vegan|100% vegan|Plant-based)) and ((cruelty-free|never tested on animals)).", "Contains {n:30-200} ml.",
        "((Patch test|Always patch test|Test on a small area)) before ((first use|use|applying widely)).", "Apply morning and evening to clean skin.@Serum|Moisturiser|Cream|Toner"],
       ["30ml", "50ml", "100ml", "Travel Size", "- Shade 02", "- Shade 05", "Unscented"],
       ["Lumière", "Botanica", "Velour", "Pure Theory", "Saffron Lane", "Dewy Days"],
       24.0),
    _F("sports", "Sports",
       ["Resistance Bands", "Adjustable Dumbbells", "Yoga Mat", "Pull-Up Bar", "Jump Rope",
        "Foam Roller", "Cycling Helmet", "Tennis Racket", "Basketball", "Football",
        "Swim Goggles", "Gym Bag", "Kettlebell", "Camping Tent", "Sleeping Bag",
        "Hiking Backpack", "Trekking Poles", "Water Bottle", "Bike Light", "Climbing Chalk Bag", "Running Vest", "Climbing Shoes", "Paddle Board", "Skipping Rope", "Exercise Bike", "Boxing Gloves", "Hydration Pack", "Head Torch", "Ski Goggles", "Wetsuit", "Badminton Set", "Grip Trainer", "Weighted Vest", "Balance Board", "Cycling Gloves"],
       ["Non-Slip@Mat", "Lightweight", "Adjustable@Dumbbells|Helmet|Poles|Rope|Bar", "Heavy-Duty", "Packable@Tent|Sleeping|Backpack|Bag", "Anti-Fog@Goggles", "Insulated@Bottle|Sleeping", "Pro", "Compact"],
       ["natural rubber@Bands|Mat|Basketball|Football|Goggles", "TPE foam@Mat|Roller", "ripstop nylon@Tent|Sleeping|Backpack|Bag", "cast iron@Kettlebell|Dumbbells", "aluminium alloy@Poles|Bar|Racket|Light|Bottle", "recycled polyester@Bag|Backpack|Sleeping|Bands", "recycled nylon", "technical fabric", "EVA foam", "neoprene", "lightweight alloy"],
       ["((a durable build|a hard-wearing finish|tough, abrasion-resistant panels|reinforced stress points))", "((a {n:1-2}-year guarantee|((a year|two years)) of cover|a no-quibble {n:1-2}-year guarantee))", "((a lightweight design|a featherweight build|a packable design|a low-weight frame))", "a carry strap@Mat|Bag|Tent|Sleeping|Roller|Backpack", "anti-slip texture@Mat|Bar|Dumbbells|Kettlebell|Racket|Poles", "{n:3-6} resistance levels@Bands", "a ventilated shell@Helmet",
        "a quick-release buckle@Helmet|Backpack|Bag|Light", "a rain cover@Backpack|Bag|Tent", "reflective details@Helmet|Backpack|Bag|Light", "a padded grip@Racket|Rope|Poles|Bar|Dumbbells|Kettlebell", "{n:1-3} litres of capacity@Bottle|Pack|Vest|Backpack", "a {n:200-800}-lumen beam@Torch|Light", "a {n:3-5} mm neoprene shell@Wetsuit|Gloves", "{n:8-16} resistance levels@Bike|Trainer", "a breathable mesh back@Vest|Backpack|Pack", "a magnetic lens system@Goggles", "a non-slip deck@Board", "gel-padded palms@Gloves", "an adjustable chest strap@Vest|Backpack|Pack", "a {n:10-25} kg load@Vest|Kettlebell|Dumbbells"],
       ["home workouts@Bands|Dumbbells|Mat|Bar|Rope|Roller|Kettlebell", "the gym@Bands|Dumbbells|Mat|Bag|Rope|Roller|Kettlebell|Bottle", "weekend hikes@Backpack|Poles|Bottle|Tent", "yoga classes@Mat|Roller|Bands", "camping trips@Tent|Sleeping|Backpack|Light|Bottle", "training sessions", "commuting by bike@Helmet|Light|Backpack"],
       ["Weighs {n:200-2500} g.@Bands|Mat|Rope|Roller|Helmet|Racket|Basketball|Football|Goggles|Gym Bag|Sleeping Bag|Backpack|Poles|Bottle|Light|Chalk|Running Vest|Shoes|Gloves|Hydration|Torch|Wetsuit|Badminton|Grip|Balance Board|Tent", "Weighs {n:5-24} kg.@Dumbbells|Kettlebell|Weighted Vest", "Weighs {n:9-35} kg.@Exercise Bike|Paddle Board", "Supports up to {n:80-150} kg.@Bar|Roller|Mat", "((Wipe|Simply wipe|Just wipe)) ((it |))clean ((after use|with a damp cloth|after each session)).",
        "Packs down to {n:20-45} cm.@Tent|Sleeping|Backpack|Poles"],
       ["- Blue", "- Red", "- Black", "- Size 5@Football|Basketball", "- Medium@Bands|Helmet|Backpack|Bag|Tent", "- Large@Bands|Helmet|Backpack|Bag|Tent", "- 6mm@Mat", "- 15kg@Kettlebell|Dumbbells"],
       ["Peakform", "Stride", "Trailborn", "Vantage", "Ironbark", "Swiftline", "Summitry"],
       35.0),
    _F("toys", "Toys",
       ["Building Blocks Set", "Wooden Train Set", "Plush Bear", "Jigsaw Puzzle",
        "Board Game", "Remote Control Car", "Doll House", "Art Kit", "Science Kit",
        "Stacking Rings", "Kite", "Play Kitchen", "Card Game", "Marble Run", "Ride-On Scooter",
        "Magnetic Tiles", "Puppet Theatre", "Drum Set", "Dolls Pram", "Toy Kitchen Set", "Tea Set", "Ball Pit", "Shape Sorter", "Robot Kit", "Dinosaur Figures", "Musical Keyboard", "Balance Bike", "Sticker Book", "Craft Box", "Toy Garage", "Play Tent", "Water Table", "Bath Toys"],
       ["Classic", "Wooden@Blocks|Train|Puzzle|Kitchen|House|Rings|Theatre", "Educational", "Glow-in-the-Dark@Puzzle|Tiles|Kite|Blocks", "Rainbow", "Junior",
        "Deluxe", "Travel"],
       ["FSC-certified wood@Blocks|Train|Kitchen|House|Rings|Theatre|Marble", "recycled plastic@Car|Scooter|Tiles|Kite|Drum|Blocks|Rings", "soft plush@Bear|Puppet", "cardboard@Puzzle|Board|Card|Kit", "child-safe plastic", "sustainable rubberwood", "soft-touch silicone", "recycled card"],
       ["{n:24-1000} pieces@Blocks|Puzzle|Tiles|Marble|Train", "a storage tin@Blocks|Puzzle|Card|Art|Tiles|Marble", "((rounded edges|smooth, splinter-free edges|soft corners|chunky, easy-grip pieces))", "rechargeable batteries@Car|Scooter|Drum",
        "((illustrated instructions|a picture guide|a parents' guide|step-by-step cards))", "{n:2-6} play modes@Car|Kitchen|Drum|Science|Tiles", "((a carry case|a drawstring bag|a storage box|a zip-up pouch))", "{n:10-60} accessories@Kitchen|Set|Kit|Garage|Box", "a {n:3-12}-song playlist@Keyboard|Drum", "{n:4-12} dinosaurs@Dinosaur", "a fold-flat frame@Pram|Tent|Bike", "an easy-grip handle@Sorter|Pram|Rings", "{n:50-500} stickers@Sticker", "a pop-up design@Tent|Ball Pit", "a coding app@Robot", "a water-safe finish@Bath|Water", "a quiet motor@Car|Robot"],
       ["rainy afternoons", "family game night@Board|Card|Puzzle", "toddlers@Blocks|Rings|Bear|Train|Tiles|Drum", "budding scientists@Science|Marble|Blocks|Tiles",
        "birthday gifts", "travel"],
       ["Recommended for ages {n:3-10} and up.", "((Not suitable for|Unsuitable for|Keep away from)) children under ((3|36 months))((.| - small parts.))",
        "Batteries included.@Car|Drum|Science", "((Contains|Includes)) small parts((.| - adult supervision advised.))", "For {n:2-6} players.@Board|Card"],
       ["- 100 Pieces", "- 500 Pieces", "- Pastel", "- Primary Colours", "Mini", "XL"],
       ["Little Oak", "Tumbletown", "Brightbox", "Kitebird", "Pip & Pals"],
       29.0),
    _F("books", "Books",
       ["Field Guide", "Cookbook", "Novel", "Short Story Collection", "Memoir", "Atlas",
        "Workbook", "Travel Guide", "Poetry Collection", "Graphic Novel", "History",
        "Biography", "Puzzle Book", "Picture Book"],
       ["Illustrated", "Pocket", "Collector's", "Annotated", "Complete", "Beginner's",
        "Revised"],
       ["paperback", "hardcover", "clothbound"],
       ["{n:120-640} pages", "full-colour photographs@Guide|Cookbook|Atlas|Picture", "an index", "a foreword by the editor",
        "maps and diagrams@Guide|Atlas|History", "a ribbon marker"],
       ["curious readers", "gift giving", "beginners", "book clubs", "long train rides"],
       ["Published {n:2015-2025}.", "{n:120-640} pages.", "Also available as an e-book."],
       ["(Paperback)", "(Hardcover)", "(2nd Edition)", "- Illustrated Edition"],
       ["Wren Press", "Kestrel Books", "Lantern House", "Old Harbour Publishing"],
       18.0),
    _F("grocery", "Grocery",
       ["Ground Coffee", "Green Tea", "Olive Oil", "Almond Butter", "Granola", "Pasta",
        "Hot Sauce", "Honey", "Dark Chocolate", "Rolled Oats", "Sea Salt", "Protein Bars",
        "Sparkling Water", "Basmati Rice", "Maple Syrup", "Trail Mix", "Peanut Butter",
        "Coconut Milk"],
       ["Organic", "Single-Origin@Coffee|Tea|Chocolate", "Cold-Pressed@Olive Oil", "Small-Batch", "Unsweetened@Butter|Milk|Granola|Water", "Gluten-Free@Pasta|Granola|Oats|Bars", "Smoked@Salt|Hot Sauce", "Wildflower@Honey", "Roasted@Coffee|Almond|Peanut|Mix"],
       ["Arabica beans@Coffee", "whole grains@Granola|Oats|Pasta|Rice|Bars", "Spanish olives@Olive Oil", "roasted almonds@Almond|Granola|Mix|Bars", "cacao@Chocolate", "green tea leaves@Tea", "wildflower nectar@Honey", "peanuts@Peanut", "chillies@Hot Sauce", "coconut@Coconut", "maple sap@Syrup", "sea water@Salt"],
       ["no added sugar", "a resealable bag@Coffee|Granola|Oats|Mix|Rice|Tea|Bars", "a glass jar@Honey|Butter|Sauce|Syrup|Salt", "{n:8-30} servings",
        "fair-trade sourcing", "a rich, nutty flavour@Butter|Granola|Mix|Coffee|Chocolate"],
       ["breakfast", "the pantry", "snacking on the go", "baking", "weeknight dinners"],
       ["Best before {n:6-24} months from packing.", "Store in a cool, dry place.",
        "May contain traces of nuts.", "Net weight {n:100-1000} g."],
       ["250g", "500g", "1kg", "Pack of 6", "Pack of 12", "750ml"],
       ["Harvest Table", "Golden Acre", "Wildroot", "Old Mill", "Sunny Ridge", "Larder & Co"],
       9.0),
    _F("pets", "Pet Supplies",
       ["Dog Bed", "Cat Tree", "Dog Lead", "Chew Toy", "Cat Litter", "Dog Food",
        "Pet Carrier", "Feeding Bowl", "Grooming Brush", "Dog Harness", "Scratching Post",
        "Treat Pouch"],
       ["Orthopaedic@Bed", "Washable@Bed|Carrier", "Reflective@Lead|Harness", "Durable", "Calming@Bed|Toy", "Grain-Free@Food", "Adjustable@Lead|Harness|Carrier", "Clumping@Litter", "Natural"],
       ["memory foam@Bed", "natural rubber@Toy|Bowl", "stainless steel@Bowl|Brush", "sisal rope@Tree|Post|Toy", "nylon webbing@Lead|Harness|Pouch|Carrier", "natural clay@Litter", "real chicken@Food"],
       ["pet-safe materials", "an easy-clean finish", "((a durable build|a hard-wearing finish|tough, abrasion-resistant panels|reinforced stress points))", "a non-slip base@Bed|Bowl|Tree|Post", "a removable cover@Bed|Carrier", "reflective stitching@Lead|Harness", "a padded handle@Lead|Carrier|Harness",
        "a quick-release clip@Lead|Harness|Pouch"],
       ["large dogs", "indoor cats", "puppies", "daily walks", "travel"],
       ["Machine washable.@Bed|Carrier|Pouch", "Fits pets up to {n:5-40} kg.@Bed|Carrier|Harness|Tree", "Supervise during play.@Toy|Tree|Post"],
       ["- Small", "- Medium", "- Large", "- Grey", "- Navy", "2kg@Food|Litter", "10kg@Food|Litter"],
       ["Pawsome", "Waggle", "Furrow & Co", "Tailwind"],
       27.0),
    _F("garden", "Garden",
       ["Garden Hose", "Pruning Shears", "Raised Planter", "Solar Lights", "Bird Feeder",
        "Watering Can", "Patio Chair", "Compost Bin", "Seed Starter Kit", "Garden Gloves",
        "Lawn Sprinkler", "Plant Pot"],
       ["Expandable", "Weatherproof", "Heavy-Duty", "Self-Watering", "Ergonomic",
        "Solar-Powered"],
       ["galvanised steel", "terracotta", "cedar wood", "recycled plastic", "powder-coated steel"],
       ["drainage holes", "a brass fitting", "UV-resistant finish", "a locking handle",
        "{n:6-12} spray patterns"],
       ["balconies", "vegetable patches", "small gardens", "patios", "spring planting"],
       ["Leave outside year-round.", "Measures {n:20-120} cm.", "Rinse after use."],
       ["- Green", "- Terracotta", "- 15m", "- 30m", "- Set of 3"],
       ["Greenhaven", "Fernwood", "Bloom & Root", "Allotment Co"],
       32.0),
    _F("office", "Office Supplies",
       ["Notebook", "Gel Pens", "Desk Organiser", "Planner", "Sticky Notes", "Stapler",
        "Filing Box", "Highlighters", "Whiteboard", "Desk Mat", "Fountain Pen", "Label Maker"],
       ["Dotted", "Refillable", "A5", "Recycled", "Magnetic", "Quick-Dry", "Undated"],
       ["recycled paper", "vegan leather", "bamboo", "aluminium", "cork"],
       ["{n:80-240} pages", "an elastic closure", "a pen loop", "{n:6-24} colours",
        "a lay-flat binding"],
       ["planning the week", "the home office", "students", "journalling", "meetings"],
       ["{n:80-120} gsm paper.", "Pack of {n:3-24}.", "Acid-free pages."],
       ["- Black", "- Sage", "- Pack of 6", "- Pack of 12", "- A4", "- A5"],
       ["Quillery", "Paperline", "Inkwell & Co", "Deskwise"],
       14.0),
    _F("automotive", "Automotive",
       ["Car Phone Mount", "Tyre Inflator", "Jump Starter", "Seat Covers", "Dash Camera",
        "Car Vacuum", "Floor Mats", "Wiper Blades", "Roof Box", "Car Charger"],
       ["Universal", "Heavy-Duty", "Portable", "All-Weather", "Magnetic", "Cordless"],
       ["rubber", "aluminium", "neoprene", "ABS plastic"],
       ["a {n:12-24} V plug", "an LED torch", "a digital gauge", "a universal fit",
        "a storage bag"],
       ["road trips", "winter driving", "daily commutes", "SUVs", "family cars"],
       ["Fits most vehicles.", "Cable length {n:1-4} m.", "Check fitment before ordering."],
       ["- Black", "- Pair", "- 22\"", "- 26\""],
       ["Roadwise", "Torque & Co", "Milepost", "Gearline"],
       38.0),
    _F("jewelry", "Jewellery",
       ["Pendant Necklace", "Hoop Earrings", "Stud Earrings", "Bracelet", "Ring",
        "Watch", "Charm Bracelet", "Cufflinks", "Anklet", "Chain"],
       ["Minimal", "Dainty", "Classic", "Hammered", "Stackable", "Vintage"],
       ["sterling silver", "14k gold vermeil", "stainless steel", "rose gold plate"],
       ["a lobster clasp", "an adjustable chain", "a gift box", "hypoallergenic posts",
        "a polished finish"],
       ["everyday wear", "gifts", "layering", "special occasions"],
       ["Nickel-free.", "Chain length {n:40-50} cm.", "Avoid contact with water and perfume."],
       ["- Gold", "- Silver", "- Rose Gold", "- 18\""],
       ["Aurelia", "Ondine", "Mira & Co", "Silverline"],
       55.0, material_in_name=True),
    _F("health", "Health",
       ["Vitamin D Tablets", "Multivitamin", "Omega-3 Capsules", "Protein Powder",
        "Electrolyte Tablets", "Magnesium Capsules", "First Aid Kit", "Digital Thermometer",
        "Massage Gun", "Heating Pad", "Blood Pressure Monitor", "Probiotic Capsules"],
       ["Daily", "High-Strength", "Vegan", "Unflavoured", "Slow-Release", "Compact"],
       ["plant-based capsules", "whey isolate", "fish oil", "magnesium glycinate"],
       ["{n:30-120} servings", "no artificial colours", "a child-resistant cap",
        "an easy-read display", "{n:3-6} intensity levels"],
       ["daily wellness", "after workouts", "the travel bag", "busy weeks"],
       ["Do not exceed the stated dose.", "Store below 25°C.",
        "Consult your doctor if pregnant or taking medication."],
       ["- 60 Capsules", "- 90 Tablets", "- 500g", "- 1kg", "- Vanilla", "- Chocolate"],
       ["VitaCore", "Wellspring", "Pure Theory", "Northwell"],
       22.0),
    _F("baby", "Baby",
       ["Baby Carrier", "Swaddle Blanket", "Bottle Set", "Teething Ring", "Baby Monitor",
        "Changing Mat", "Sleepsuit", "High Chair", "Bath Seat", "Play Mat"],
       ["Soft", "Organic", "Breathable", "Foldable", "Easy-Clean", "Anti-Colic"],
       ["organic cotton", "muslin", "food-grade silicone", "bamboo viscose"],
       ["poppers down the front", "a padded headrest", "BPA-free parts", "a night-light",
        "adjustable straps"],
       ["newborns", "night feeds", "nursery essentials", "travel"],
       ["Suitable from birth.", "Machine washable at 30°C.", "Meets EN 71 safety standards."],
       ["- 0-3 Months", "- 3-6 Months", "- Pack of 3", "- Oat", "- Sage"],
       ["Little Oak", "Nestling", "Pip & Pals", "Cradle Co"],
       34.0),
    _F("tools", "Tools",
       ["Cordless Drill", "Screwdriver Set", "Tool Box", "Tape Measure", "Spirit Level",
        "Socket Set", "Work Light", "Utility Knife", "Stud Finder", "Glue Gun", "Ladder",
        "Workbench"],
       ["Cordless", "Heavy-Duty", "Compact", "Magnetic", "Professional", "Folding"],
       ["chrome vanadium steel", "aluminium", "hardened steel", "impact-resistant plastic"],
       ["a {n:12-20} V battery", "an LED work light", "((a carry case|a drawstring bag|a storage box|a zip-up pouch))", "a belt clip",
        "{n:20-120} pieces", "a soft-grip handle"],
       ["DIY projects", "the garage", "flat-pack furniture", "small repairs", "trades"],
       ["Battery and charger included.", "Covered by a {n:2-5}-year warranty.",
        "Weighs {n:300-2000} g.@Drill|Screwdriver|Tape|Level|Socket|Work Light|Knife|Stud|Glue Gun", "Weighs {n:4-25} kg.@Ladder|Workbench|Tool Box"],
       ["- 18V", "- 32-Piece", "- 5m", "- Yellow", "- Kit"],
       ["Ironbark", "Forgewell", "Torque & Co", "Benchmark Tools"],
       48.0),
    _F("generic", "General",
       ["Gift Set", "Storage Box", "Travel Kit", "Multi-Tool", "Tote Bag", "Desk Organiser",
        "Water Bottle", "Umbrella", "Backpack", "Keyring", "Lunch Box", "Phone Case",
        "Picnic Blanket", "Wallet"],
       ["Compact", "Classic", "Everyday", "Durable", "Lightweight", "Foldable", "Premium"],
       ["recycled materials", "canvas", "stainless steel", "vegan leather", "bamboo"],
       ["a zip closure", "a lifetime guarantee", "a carry strap", "a gift box",
        "a water-resistant finish", "an inner pocket"],
       ["everyday use", "travel", "gifts", "the office", "weekends away"],
       ["Wipe clean.", "Measures {n:10-60} cm.", "Ships in plastic-free packaging."],
       ["- Black", "- Navy", "- Sand", "- Large", "- Small"],
       ["Wayfarer", "Common Thread", "Meridian Goods", "Harbor & Pine"],
       25.0),
]}

# More features and spec lines for the smaller families, so a catalogue of a
# few thousand books or groceries does not keep repeating the same handful.
_FAMILY_EXTRA = {
    "books": (["a new introduction by the author", "{n:20-120} recipes@Cookbook", "{n:8-40} walking routes@Guide", "{n:12-30} stories@Collection",
               "an author's note", "a glossary@History|Atlas|Guide|Workbook", "{n:40-200} illustrations@Picture|Graphic|Field|Cookbook",
               "answers at the back@Workbook|Puzzle", "{n:30-120} puzzles@Puzzle", "a reading group guide@Novel|Memoir|Collection|Biography",
               "fold-out maps@Atlas|Travel|Field", "a timeline@History|Biography", "black-and-white photographs@Memoir|Biography|History",
               "{n:10-40} full-page spreads@Picture|Atlas|Cookbook"],
              ["Translated from the ((French|Spanish|Japanese|Norwegian|Italian)).@Novel|Collection|Poetry|Memoir",
               "((Shortlisted|Longlisted)) for the {n:2016-2024} ((Costa|Booker|Wainwright|Baillie Gifford)) Prize.@Novel|Memoir|Biography|History|Collection",
               "Suitable for ages {n:3-8} and up.@Picture|Sticker", "Printed on FSC-certified paper.", "Signed first edition while stocks last."]),
    "grocery": (["notes of ((caramel|cocoa|citrus|dark berries|toasted nuts))@Coffee|Chocolate|Tea", "a medium roast@Coffee", "{n:55-85}% cocoa@Chocolate",
                 "a peppery finish@Olive Oil", "{n:8-20} g of protein per bar@Bars", "a light, floral taste@Honey|Tea|Syrup", "a crunchy texture@Granola|Mix|Butter",
                 "a slow-roasted flavour@Coffee|Almond|Peanut|Mix", "bronze-die cutting@Pasta", "a {n:3-9}-month ageing@Rice", "a habanero kick@Hot Sauce",
                 "a compostable pouch@Coffee|Tea|Granola|Oats|Rice|Mix", "a vegan recipe", "single-estate sourcing@Coffee|Tea|Olive|Chocolate|Honey",
                 "a low-sugar recipe@Granola|Bars|Butter|Chocolate", "a recyclable tin@Coffee|Tea|Salt"],
                ["Suitable for vegans.", "Made in a factory that handles nuts and sesame.", "Once opened, use within {n:4-12} weeks.",
                 "Grown in ((Colombia|Ethiopia|Kenya|Sicily|Andalusia|Kerala|Assam|Peru)).@Coffee|Tea|Olive|Chocolate|Rice",
                 "((Brew|Steep)) for {n:2-5} minutes.@Tea|Coffee"]),
    "pets": (["a waterproof base@Bed|Carrier", "bolstered sides@Bed", "{n:2-4} scratching levels@Tree|Post", "a dangling toy@Tree|Post", "a squeaker inside@Toy",
              "((a lightweight design|a featherweight build|a packable design|a low-weight frame))", "a padded chest plate@Harness", "a 2 m length@Lead", "a non-tip design@Bowl", "a self-cleaning button@Brush",
              "a front clip@Harness", "low-dust granules@Litter", "a treat compartment@Toy|Pouch", "a breathable mesh panel@Carrier|Bed"],
             ["Spot clean only.@Tree|Post", "Dishwasher safe.@Bowl", "Vet-approved recipe.@Food", "Feed {n:2-3} times a day.@Food"]),
    "garden": (["a {n:15-50} m length@Hose", "a soft-grip handle@Shears|Can|Gloves", "a built-in reservoir@Planter|Pot", "a dusk-to-dawn sensor@Lights",
                "{n:6-12} hours of light@Lights", "a squirrel-proof cage@Feeder", "a {n:5-12} litre capacity@Can", "a fold-flat frame@Chair",
                "a {n:200-400} litre capacity@Compost", "{n:12-40} seed cells@Starter", "touchscreen-friendly fingertips@Gloves", "a rust-proof finish"],
               ["Assembly takes about {n:10-30} minutes.@Planter|Chair|Compost|Feeder", "Bring indoors over winter.@Lights|Chair|Pot",
                "Charges in direct sunlight.@Lights", "Fits standard hose connectors.@Hose|Sprinkler"]),
    "office": (["a ribbon bookmark@Notebook|Planner", "numbered pages@Notebook|Planner", "a back pocket@Notebook|Planner", "a fine 0.5 mm tip@Pens|Pen",
                "a non-slip base@Organiser|Stapler|Mat", "{n:4-8} compartments@Organiser|Box", "a {n:20-40}-sheet capacity@Stapler",
                "a magnetic surface@Whiteboard", "a converter and {n:3-6} cartridges@Fountain", "smudge-proof ink@Pens|Highlighters|Pen",
                "monthly and weekly views@Planner", "a stitched edge@Mat"],
               ["Fits A4 sheets.@Box|Organiser", "Refills available.@Pens|Pen|Planner|Notebook", "Includes {n:2-5} marker pens.@Whiteboard"]),
    "automotive": (["a {n:150-1500} A peak current@Jump", "auto shut-off at the set pressure@Inflator", "a 360° swivel@Mount", "a wet-and-dry nozzle@Vacuum",
                    "raised edges@Mats", "a {n:400-600} litre capacity@Roof", "{n:2-4} USB ports@Charger", "airbag-compatible seams@Seat",
                    "a night-vision lens@Dash", "a one-touch release@Mount", "a beam-blade design@Wiper"],
                   ["Fits most roof bars.@Roof", "Charges from a 12 V socket.@Vacuum|Inflator|Charger", "Sold as a pair.@Wiper|Seat"]),
    "jewelry": (["a {n:8-20} mm drop@Earrings", "an extender chain@Necklace|Chain|Anklet|Bracelet", "a slim profile@Ring|Bracelet|Cufflinks",
                 "a sapphire-crystal face@Watch", "a hand-hammered texture", "a {n:1-3} mm band@Ring", "an engravable plate@Bracelet|Cufflinks|Pendant",
                 "a box-chain style@Chain|Necklace", "a {n:30-40} mm case@Watch", "a tarnish-resistant coating"],
                ["Water-resistant to {n:3-10} ATM.@Watch", "Comes in a recycled gift box.", "Made to order in {n:3-10} days.", "Free resizing within 30 days.@Ring"]),
    "health": (["{n:1000-4000} IU per tablet@Vitamin", "a pleasant citrus taste@Electrolyte|Multivitamin|Protein", "{n:20-30} g of protein per scoop@Protein",
                "{n:4-10} billion cultures@Probiotic", "{n:60-120} plasters and dressings@First Aid", "a 10-second reading@Thermometer|Monitor",
                "an auto-off timer@Heating|Massage", "{n:4-8} massage heads@Massage", "irregular heartbeat detection@Monitor", "a fever alert@Thermometer",
                "a travel pouch@First Aid|Massage|Thermometer"],
               ["Take one a day with food.@Tablets|Capsules|Multivitamin", "Mix one scoop with 300 ml of water.@Protein|Electrolyte",
                "Clinically validated.@Monitor|Thermometer", "Batteries included.@Thermometer|Monitor"]),
    "baby": (["a {n:3-5}-point harness@Chair|Carrier|Seat", "a wipe-clean tray@Chair", "two-way zips@Sleepsuit", "a slow-flow teat@Bottle",
              "a two-way talkback@Monitor", "a temperature sensor@Monitor", "a padded edge@Mat", "{n:4-8} hanging toys@Play", "a lumbar support belt@Carrier",
              "a textured surface@Teething", "a suction base@Seat"],
             ["Suitable from {n:3-6} months.@Chair|Seat|Teething", "Supports babies up to {n:9-15} kg.@Carrier|Seat|Chair", "Sterilise before first use.@Bottle|Teething",
              "Range up to {n:200-300} m.@Monitor"]),
    "tools": (["a {n:2-3}-speed gearbox@Drill", "a magnetic bit holder@Drill|Screwdriver", "{n:1-3} bubble vials@Level", "a {n:5-10} m blade@Tape",
               "a quick-release blade@Knife", "AC wire detection@Stud", "a {n:7-11} mm nozzle@Glue", "{n:3-6} steps@Ladder", "a lockable lid@Box",
               "a clamping top@Workbench", "a {n:1000-3000} lumen output@Work Light", "a ratcheting handle@Socket|Screwdriver"],
              ["Includes {n:10-30} glue sticks.@Glue", "Supports up to {n:100-150} kg.@Ladder|Workbench", "Spare blades included.@Knife"]),
    "generic": (["a padded laptop sleeve@Backpack", "a {n:15-30} L capacity@Backpack|Box|Bag", "a windproof frame@Umbrella", "{n:10-18} functions@Multi-Tool",
                 "RFID blocking@Wallet", "a leak-proof lid@Bottle|Lunch", "a waterproof backing@Picnic", "a magnetic clasp@Case|Wallet", "{n:3-6} compartments@Lunch|Kit|Organiser|Box",
                 "a reinforced base@Tote|Box|Backpack"],
                ["Keeps drinks cold for {n:12-24} hours.@Bottle", "Folds to {n:20-30} cm.@Umbrella|Picnic", "Dishwasher safe.@Lunch|Bottle"]),
}
for _k, (_feat, _spec) in _FAMILY_EXTRA.items():
    _f = PRODUCT_FAMILIES[_k]
    PRODUCT_FAMILIES[_k] = replace(_f, features=list(_f.features) + _feat, specs=list(_f.specs) + _spec)

# Category label -> family, first match wins. Ordered so "kids clothing"
# reads as clothing and "kitchen appliances" as kitchen, not electronics.
_FAMILY_KEYWORDS = [
    ("footwear", ("shoe", "footwear", "sneaker", "boot")),
    ("clothing", ("cloth", "apparel", "fashion", "garment", "wear", "dress", "outfit")),
    ("kitchen", ("kitchen", "cook", "dining", "tableware", "appliance")),
    ("furniture", ("furniture", "furnishing")),
    ("baby", ("baby", "infant", "nursery", "toddler", "maternity")),
    ("toys", ("toy", "game", "kids", "puzzle", "hobby", "hobbies")),
    ("beauty", ("beauty", "cosmetic", "skin", "makeup", "make-up", "hair", "fragrance",
                "personal care", "grooming")),
    ("health", ("health", "wellness", "supplement", "pharma", "vitamin", "medical")),
    ("sports", ("sport", "fitness", "outdoor", "gym", "athlet", "camping", "cycling")),
    ("books", ("book", "literature", "reading", "media")),
    ("grocery", ("food", "grocer", "snack", "beverage", "drink", "pantry", "coffee",
                 "tea", "gourmet")),
    ("pets", ("pet", "dog", "cat", "animal")),
    ("garden", ("garden", "lawn", "patio", "plant")),
    ("office", ("office", "stationery", "school", "supplies", "paper")),
    ("automotive", ("auto", "car ", "cars", "vehicle", "motor")),
    ("jewelry", ("jewel", "watch", "accessor")),
    ("tools", ("tool", "hardware", "diy", "industrial", "improvement")),
    ("electronics", ("electronic", "tech", "gadget", "computer", "audio", "phone",
                     "camera", "gaming", "tv", "laptop")),
    ("home", ("home", "decor", "bedding", "bath", "household", "living", "house")),
]

# When the table has no category to follow: roughly how a general retailer's
# catalogue splits across departments.
_DEFAULT_FAMILY_MIX = [("electronics", 0.18), ("clothing", 0.2), ("home", 0.14),
                       ("kitchen", 0.08), ("beauty", 0.1), ("sports", 0.09),
                       ("toys", 0.05), ("footwear", 0.05), ("books", 0.04),
                       ("grocery", 0.04), ("pets", 0.03)]


def family_for_category(category) -> Optional[str]:
    """The product family a category label names, or None."""
    c = f" {str(category).strip().lower()} "
    if c.strip() in ("", "nan", "none"):
        return None
    for key, words in _FAMILY_KEYWORDS:
        if any(w in c for w in words):
            return key
    return None


@dataclass
class ProductFrame:
    family: List[str]
    brand: List[str]
    noun: List[str]
    attr: List[str]
    material: List[str]
    name: List[str]


def draw_products(rng: np.random.Generator, size: int,
                  categories: Optional[Sequence] = None,
                  key: str = "products") -> ProductFrame:
    """One latent product per row, following ``categories`` when given."""
    cats = _clean_values(categories, size)
    if cats is not None:
        fam = [family_for_category(c) or "generic" for c in cats]
    else:
        keys, w = zip(*_DEFAULT_FAMILY_MIX)
        w = np.array(w) / sum(w)
        fam = [keys[i] for i in rng.choice(len(keys), size=size, p=w)]
    fam_arr = np.array(fam, dtype=object)
    brand = np.empty(size, dtype=object)
    noun = np.empty(size, dtype=object)
    attr = np.empty(size, dtype=object)
    material = np.empty(size, dtype=object)
    names = np.empty(size, dtype=object)
    for f in sorted(set(fam)):
        idx = np.flatnonzero(fam_arr == f)
        F = PRODUCT_FAMILIES[f]
        n = len(idx)
        # Brands are concentrated, product types less so.
        brand[idx] = zipf_choice(rng, F.brands, n, s=1.1, key=f"{key}|{f}|brand")
        noun[idx] = zipf_choice(rng, F.nouns, n, s=0.7, q=4, key=f"{key}|{f}|noun")
        for i in idx:
            a_pool = eligible(F.attrs, noun[i]) or [""]
            m_pool = eligible(F.materials, noun[i]) or [""]
            attr[i] = a_pool[int(rng.integers(len(a_pool)))]
            material[i] = m_pool[int(rng.integers(len(m_pool)))]
        use_brand = rng.random(n) < 0.6
        use_attr = rng.random(n) < 0.55
        use_mat = (rng.random(n) < 0.3) if F.material_in_name else np.zeros(n, bool)
        use_var = rng.random(n) < 0.4
        variants = [eligible(F.variants, noun[i]) for i in idx]
        variants = [v[int(rng.integers(len(v)))] if v else "" for v in variants]
        for j, i in enumerate(idx):
            parts = []
            if use_brand[j]:
                parts.append(brand[i])
            if use_attr[j] and attr[i] and str(attr[i]).split("-")[0].lower() not in str(noun[i]).lower():
                parts.append(attr[i])
            if use_mat[j] and material[i] and not (set(str(material[i]).lower().split())
                                                   & set(str(noun[i]).lower().split())):
                parts.append(" ".join(w.capitalize() if w.islower() else w
                                      for w in str(material[i]).split()))
            parts.append(noun[i])
            nm = " ".join(parts)
            if use_var[j] and variants[j]:
                nm = f"{nm} {variants[j]}"
            names[i] = nm
    return ProductFrame(list(fam), list(brand), list(noun), list(attr),
                        list(material), list(names))


# (weight, template, features it consumes)
_DESC_OPENERS = [
    (2, "((Built|Made|Designed)) for {use}: the {brand} {noun}((.|, in {material}.))", 0),
    (2, "((If you need|If you want|For anyone who needs|When you want)) {a_noun} ((that lasts|that just works|without the fuss)), ((this is it|start here|meet this one)).", 0),
    (1, "((Our take on|Our version of|We redesigned)) the {noun}((: {material}, {f1}.| around {f1}.))", 1),
    (2, "{Brand} {noun}((. {Material}, {f1}.|, with {f1} and a {attr} finish.))", 1),
    (1, "((Small|Big|Quiet)) ((upgrade|change|detail)), ((big|real|noticeable)) difference: {f1} on ((our|the)) {attr} {noun}.", 1),
    (2, "{A_attr_noun} with {f1}((.|, {f2} and nothing you don't need.))", 2),
    (1, "((Fresh|New|Just landed)) ((for|this)) {season}: {a_attr_noun}((.| in {material}.))", 0),
    (3, "{A_attr_noun} {made} {material}((.|, ((finished|made|built)) to last.|, ((designed|made)) for everyday use.))", 0),
    (2, "{This} {attr} {noun} {is} {made} {material}((.| and ((built|made|designed)) to last.))", 0),
    (2, "{Brand}'s {attr} {noun}((, in {material}.|, now in {material}.| - {material}, ((reimagined|done right|made better)).))", 0),
    (2, "The {noun} ((you reach for every day|you'll actually use|that goes everywhere|we couldn't stop using)), ((now in|made in|crafted from)) {material}.", 0),
    (2, "((A|An honest|A thoughtful|A modern)) ((take|spin|update)) on the ((classic|everyday|humble|trusty)) {noun}.", 0),
    (1, "((Our best-selling|Our most-loved|The customer favourite)) {noun}((, refined.|, improved.|, now even better.| is back.))", 0),
    (1, "((Meet|Say hello to|Introducing)) the {brand} {noun}((.|!))", 0),
    (2, "{A_noun} ((built|designed|made)) around {f1}.", 1),
    (1, "{Noun} with {f1} and {f2}((.|, nothing more, nothing less.))", 2),
    (1, "((Simple|Clever|Honest|Considered)) {noun}((s|)) ((for|built for|made for)) {use}.".replace("{noun}((s|))", "{noun}"), 0),
    (1, "((Everything|All) you need|Exactly what you need|Just what you need)) in ((a|one)) {attr} {noun}.".replace("((Everything|All) you need|", "((Everything you need|All you need|"), 0),
]
_DESC_FEATURES = {
    1: [(2, "((Comes|Arrives)) with {f1}."), (2, "((Includes|Also has|With)) {f1}((.|, as standard.))"), (2, "((Features|Look out for|Finished with)) {f1}.")],
    2: [(3, "((Features|Has|Offers)) {f1} and {f2}."), (2, "((Designed|Made|Finished)) with {f1} and {f2}."),
        (1, "((Comes|Arrives)) with {f1} ((and|plus)) {f2}.")],
    3: [(2, "((It has|You get|Inside the box:|Along with that:)) {f1}, {f2} and {f3}."), (1, "{F1}, {f2} and {f3} ((come as standard|are included|are built in|all feature|round it out))."),
        (1, "((Features|Details|Highlights)): {f1}, {f2} ((and|plus)) {f3}.")],
}
_DESC_USES = [
    (2, "((Use it|Reach for it|Take it)) ((for|on|during)) {use}((.|, then {use2}.))"),
    (1, "((Popular|A favourite|Loved)) ((with|among)) ((people who|anyone who|those who)) ((need|want)) it for {use}."),
    (1, "((Handy|Useful|Ideal)) ((for|on)) {use}((.|, especially {use2}.))"),
    (1, "((Goes|Works)) from {use} to {use2} ((without fuss|with ease|easily))."),
    (3, "((Ideal|Perfect|Great)) for {use}((.|, and more.))"), (2, "((Made|Designed|Built)) for {use}."),
    (2, "((A good|A smart|A solid)) ((pick|choice|bet)) for {use}."), (1, "((Works well|Shines)) ((for|in)) {use}."),
    (1, "((Great|Ideal)) for {use} and {use2}."), (1, "((Whether it's|From)) {use} ((to|or)) {use2}, ((it's ready|it delivers|it's up to it))."),
]
_NOT_PLURAL = {"atlas", "canvas", "glass", "dress", "harness", "press", "gloss"}


def is_plural(noun: str) -> bool:
    last = noun.split()[-1].lower() if noun.split() else ""
    return (last.endswith("s") and not last.endswith(("ss", "us", "is"))
            and last not in _NOT_PLURAL)


def _soft_lower(phrase: str) -> str:
    """Lowercase ordinary words, keep acronyms and model names (SPF, USB-C, V-Neck)."""
    return " ".join(w if any(ch.isupper() for ch in w[1:]) or w[:1].isdigit() else w.lower()
                    for w in phrase.split())


_ELIGIBLE: Dict[tuple, List[str]] = {}


def eligible(pool: Sequence[str], noun: str) -> List[str]:
    """Entries of ``pool`` that fit ``noun``.

    An entry may end in ``@Kw1|Kw2``: it then fits only nouns containing one
    of those words ("a washable filter@Vacuum|Purifier"). Untagged entries fit
    every noun in the family. A noun no tagged entry names gets the untagged
    ones, so nothing is left empty while a vacuum never gets a "soft-touch
    weave"."""
    k = (id(pool), noun)
    hit = _ELIGIBLE.get(k)
    if hit is not None:
        return hit
    tagged, plain = [], []
    for e in pool:
        if "@" in e:
            text, kws = e.rsplit("@", 1)
            if any(w.lower() in noun.lower() for w in kws.split("|")):
                tagged.append(text)
        else:
            plain.append(e)
    out = tagged + plain
    _ELIGIBLE[k] = out
    _SPECIFIC[k] = len(tagged)
    return out


_SPECIFIC: Dict[tuple, int] = {}


def _specific_first(rng, pool: Sequence[str], noun: str, k: int) -> List[str]:
    """``k`` distinct entries that fit ``noun``, three in four drawn from the
    ones written for it, so a lipstick is not sold on "((a durable build|a hard-wearing finish|tough, abrasion-resistant panels|reinforced stress points))"."""
    fits = eligible(pool, noun)
    n_tag = _SPECIFIC[(id(pool), noun)]
    tagged, plain = list(range(n_tag)), list(range(n_tag, len(fits)))
    out = []
    while len(out) < min(k, len(fits)):
        src = tagged if tagged and (not plain or rng.random() < 0.75) else plain
        out.append(fits[src.pop(int(rng.integers(len(src))))])
    return out


_CUM: Dict[int, List[float]] = {}


def _weighted(rng, options):
    cum = _CUM.get(id(options))
    if cum is None:
        w = np.cumsum([float(o[0]) for o in options])
        cum = (w / w[-1]).tolist()
        _CUM[id(options)] = cum
    import bisect
    return options[min(bisect.bisect_right(cum, rng.random()), len(options) - 1)][1]


def _distinct(rng, pool, k):
    """``k`` distinct entries of ``pool`` (pool order randomised)."""
    n = len(pool)
    k = min(k, n)
    out, seen = [], set()
    while len(out) < k:
        j = int(rng.integers(n))
        if j not in seen:
            seen.add(j)
            out.append(pool[j])
    return out


_KNOWN_NOUNS: Optional[List[str]] = None


def _noun_from_name(name: str) -> str:
    """The product type in a name: a known product noun when the name holds
    one ("Northfold Relaxed Rain Jacket - Navy" is a rain jacket), else the
    last two words before any variant suffix."""
    global _KNOWN_NOUNS
    if _KNOWN_NOUNS is None:
        _KNOWN_NOUNS = sorted({n for f in PRODUCT_FAMILIES.values() for n in f.nouns},
                              key=len, reverse=True)
    text = str(name)
    for n in _KNOWN_NOUNS:
        if n in text:
            return n if n.isupper() or n[:2].isupper() else n.lower()
    base = re.split(r"\s[-–(]\s?|\(", text)[0].strip()
    words = base.split()
    return " ".join(words[-2:]).lower() if words else "product"


_COLOURS = ["charcoal", "sage", "oat", "navy", "terracotta", "ivory", "forest green", "slate", "rust",
            "sand", "dusty pink", "ochre", "midnight blue", "stone", "olive", "burgundy", "teal", "mustard",
            "graphite", "cream", "pebble grey", "clay", "moss", "ink", "blush", "copper", "sky blue",
            "black", "white", "natural", "walnut", "smoke", "lilac", "chalk", "pine", "tan"]
_ORIGINS = ["Portugal", "Denmark", "Japan", "Italy", "Vietnam", "India", "Turkey", "Poland", "Sweden",
            "the UK", "Spain", "Germany", "Morocco", "Peru", "Taiwan", "Lithuania", "Mexico", "Ireland"]
_STORIES = ["long walks on the coast", "our founder's grandmother's kitchen", "city commuting", "rainy Scottish summers",
            "small flats with big ideas", "weekends in the hills", "the way people actually live", "a decade of customer feedback",
            "mid-century Scandinavian design", "Japanese minimalism", "the first cold morning of autumn", "busy family mornings",
            "workshops in {origin}", "years of testing with real users", "the simple things done well"]
_DESC_EXTRAS = [
    "((Available|Comes|Offered)) in {c1}, {c2} and {c3}.", "((Shown|Pictured)) in {c1}.",
    "((Designed|Made|Crafted)) in {origin} ((by a family-run workshop|in small batches|by a team of {k} makers|to order)).",
    "((Inspired by|Designed for|Born from)) {story}.", "((Packaged|Shipped|Sent)) in ((recycled|plastic-free|compostable|minimal)) ((card|packaging|paper)).",
    "((Each piece|Every one|Each unit)) is ((slightly different|hand-checked|individually numbered|inspected before dispatch)).",
    "((Pair it|Team it|Use it)) with ((our matching|the {c1}|the coordinating)) ((range|collection|set)) for ((a complete look|the full set|extra storage)).",
    "((Part of|From)) our {season} ((collection|range|edit)).", "((Over|More than)) {k},{k}00 ((sold|happy customers|five-star reviews)) ((since {year}|and counting|this year)).",
    "((Ships|Dispatches|Leaves us)) within ((24 hours|2 working days|{k} days))((.|; free returns within 30 days.))",
    "((Rated|Voted)) ((best in class|a top pick|editor's choice)) by ((our customers|{origin}-based testers|a leading home magazine)) in {year}.",
    "{k}-((year|month)) ((guarantee|warranty)) ((included|as standard|on parts and labour)).",
    "((Our|The)) {c1} ((colourway|shade|finish)) ((sold out twice|is the most popular|was a customer request)) ((last {season}|in {year}|this year)).",
    "((Restocked|Back in stock|Now shipping)) ((after a {k}-week wait|for {season}|in {c1} and {c2})).",
    "((We|Our team)) ((tested|lived with|used)) it for {k} months ((before launch|in real homes|on real commutes)) - ((it held up|no complaints|it stayed in rotation)).",
    "((Made|Produced|Finished)) in a ((solar-powered|family-run|{k}-person|B Corp-certified)) ((factory|workshop|studio)) in {origin}.",
    "((Reviewers|Customers|Testers)) ((call it|say it's|describe it as)) ((“the one worth paying for”|“better than expected”|“a proper upgrade”|“quietly brilliant”)).",
    "((Free|Complimentary)) ((engraving|gift wrap|monogramming|next-day delivery)) ((on request|over $50|this {season}|at checkout)).",
    "((Designed|Drawn up|Developed)) ((with|alongside|by)) ((a {origin}-based studio|our in-house team|{k} independent designers)).",
    "((Look for|Spot|Find)) the ((small|stitched|embossed)) {brand} ((logo|tag|stamp)) ((on the base|inside|on the back)).",
    "((Ten|{k}0)) per cent of ((profits|sales)) from this ((range|piece|line)) ((goes to|supports)) ((local repair cafés|tree planting in {origin}|a community workshop)).",
    "((Spare parts|Replacement parts|Refills)) ((available|sold separately|in stock)) ((for {k} years|for life|on our site)).",
    "((Arrives|Ships|Comes)) ((fully assembled|ready to use|charged and ready|gift-wrapped on request))((.|, in {c1} tissue paper.))",
    "((The|This)) {c1} version ((pairs well with|sits nicely next to|goes with)) ((oak|walnut|white walls|{c2} accents|darker tones)).",
    "((Limited|Small|Seasonal)) run of {k}00 ((pieces|units|made)) ((for {season}|this year|in {year})).",
    "((Thoughtfully|Carefully|Responsibly)) ((made|sourced|packed)) - ((see|read)) our ((impact report|supplier list|materials guide)) ((for details|online|on the label)).",
    "((Questions|Not sure about sizing|Need advice))? ((Our|The)) ((team|customer care team|{origin} studio)) ((replies within the hour|is on chat {k} days a week|will help)).",
    "((Rated|Scored)) {k}.{k}/10 ((by|across)) ((over {k},{k}00 reviews|{k}00 verified buyers|our testers)).",
    "((Upgraded|Improved|Refined)) for {year}: ((a sturdier build|softer edges|less packaging|a lower price|new colours)).",
    "((Size|Fit|Scale)) ((guide|check|note)): ((compare it with one you own|see the photos with a hand for scale|measure your space first)).",
    "((Every|Each)) order ((plants a tree|funds a repair workshop|includes a handwritten note)) ((in {origin}|from our team|with your first order)).",
    "((Questions|Not sure)) ((about|on)) {c1} or {c2}? ((Order both|Ask for swatches|Try both)) - ((returns are free|we'll collect the other|swaps are easy)).",
    "((Five|{k}) things|{k} reasons|Why customers)) ((love|keep buying|recommend)) it: ((it lasts|it looks good|it's easy to clean|it's the right size)).".replace("((Five|{k}) things|{k} reasons|Why customers))", "((Five things|{k} reasons|Why customers))"),
    "((Originally|First)) ((designed|made|sold)) in {origin} in ((the 1970s|the 80s|{year}|the 1990s)), ((and|now)) ((still made the same way|updated for today|back by demand)).",
]


def _desc_slots(rng) -> Dict[str, str]:
    cs = _distinct(rng, _COLOURS, 3)
    return {"c1": cs[0], "c2": cs[1], "c3": cs[2], "w": str(int(rng.integers(8, 180))), "h": str(int(rng.integers(5, 120))),
            "d": str(int(rng.integers(3, 80))), "g": str(int(rng.integers(40, 9000))), "origin": _pick(rng, _ORIGINS),
            "story": _fill(_pick(rng, _STORIES), rng, {"origin": _pick(rng, _ORIGINS)}), "k": str(int(rng.integers(2, 9))),
            "season": _pick(rng, ["spring", "summer", "autumn", "winter", "holiday", "everyday", "core"]),
            "year": str(int(rng.integers(2019, 2026)))}


def render_product_descriptions(rng: np.random.Generator, frame: ProductFrame,
                                names: Optional[Sequence] = None) -> np.ndarray:
    """Descriptions of the products in ``frame``.

    ``names``: the row's actual product names when they did not come from the
    frame (a user's own vocabulary). The description then talks about the
    product type in that name rather than about a different product."""
    size = len(frame.family)
    names = _clean_values(names, size)
    out = np.empty(size, dtype=object)
    n_sent = rng.choice([1, 2, 3, 4, 5], size=size, p=[0.08, 0.25, 0.32, 0.22, 0.13])
    bullet = rng.random(size) < 0.1
    kept: List[str] = []
    for i in range(size):
        F = PRODUCT_FAMILIES[frame.family[i]]
        key_noun = frame.noun[i]
        if names is not None and names[i] and names[i] != frame.name[i]:
            key_noun = _noun_from_name(names[i]).title()
        noun = _soft_lower(key_noun)
        kept.append(noun)
        plural = is_plural(noun)
        feats = [_fill(f, rng, {}) for f in _specific_first(rng, F.features, key_noun, 3)]
        uses = _distinct(rng, eligible(F.uses, key_noun), 2) or ["everyday use"]
        uses += uses[:1]
        specs = eligible(F.specs, key_noun)
        attr = (frame.attr[i] or "classic").lower()
        if attr.split("-")[0] in noun.lower():
            attr = "classic" if "classic" not in noun.lower() else "everyday"
        material = frame.material[i] or "durable materials"
        made = "made with" if frame.family[i] in ("beauty", "health", "grocery", "pets") else "made from"
        slots = {
            "noun": noun, "Noun": _cap(noun), "attr": attr, "brand": frame.brand[i],
            "Brand": frame.brand[i], "material": material,
            "made": made, "A_attr_noun": _cap(f"{attr} {noun}" if plural else f"{_article(attr)} {attr} {noun}"),
            "A_noun": _cap(noun if plural else f"{_article(noun)} {noun}"),
            "This": "These" if plural else "This", "is": "are" if plural else "is",
            "use": uses[0], "use2": uses[1], "Material": _cap(material),
            "a_noun": noun if plural else f"{_article(noun)} {noun}",
            "a_attr_noun": f"{attr} {noun}" if plural else f"{_article(attr)} {attr} {noun}",
            "season": ("spring", "summer", "autumn", "winter")[int(rng.integers(4))],
        }
        for k, f in enumerate(feats, 1):
            slots[f"f{k}"] = f
        if feats:
            slots["F1"] = _cap(feats[0])

        def spec():
            if specs:
                return _fill(specs[int(rng.integers(len(specs)))], rng, {})
            return _fill(_weighted(rng, _DESC_USES), rng, slots)

        if bullet[i] and len(feats) >= 2:
            out[i] = (f"{_cap(noun)} in {material}. Key features: " + "; ".join(feats)
                      + f". {spec()}")
            continue
        openers = [o for o in _DESC_OPENERS if o[2] <= len(feats)]
        w = np.array([o[0] for o in openers], dtype=float)
        tmpl, used = openers[int(rng.choice(len(openers), p=w / w.sum()))][1:]
        sentences = [_fill(tmpl, rng, slots)]
        rest = feats[used:]
        tail = []
        if rest:
            fs = dict(slots, **{f"f{k}": f for k, f in enumerate(rest, 1)}, F1=_cap(rest[0]))
            tail.append(lambda fs=fs, n=len(rest): _fill(_weighted(rng, _DESC_FEATURES[n]), rng, fs))
        tail.append(lambda: _fill(_weighted(rng, _DESC_USES), rng, slots))
        tail.append(spec)
        tail.append(lambda: _fill(_pick(rng, _DESC_EXTRAS), rng, dict(slots, **_desc_slots(rng))))
        tail.append(lambda: _fill(_pick(rng, _DESC_EXTRAS), rng, dict(slots, **_desc_slots(rng))))
        order = rng.permutation(len(tail)) if rng.random() < 0.5 else np.arange(len(tail))
        for k in order[: int(n_sent[i]) - 1]:
            sentences.append(tail[k]())
        if rng.random() < 0.7:
            sentences.append(_fill(_pick(rng, _DESC_EXTRAS), rng, dict(slots, **_desc_slots(rng))))
        out[i] = " ".join(sentences)
    from misata.paraphrase import vary_keeping
    return np.array(vary_keeping(list(out), kept, rng, "product"), dtype=object)


# ── support tickets ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Issue:
    key: str
    family: str                 # billing, shipping, returns, technical, account, product
    subjects: Sequence[str]     # short subject lines
    symptoms: Sequence[str]     # first sentence of the description
    details: Sequence[str]
    causes: Sequence[str]       # resolution: what was wrong
    fixes: Sequence[str]        # resolution: what the agent did
    severity: float = 1.0       # >1 leans high/urgent, <1 leans low


_I = Issue
ISSUES: List[Issue] = [
    # billing
    _I("double_charge", "billing",
       ["((Charged|Billed)) twice for order #{order}", "Double ((charge|payment)) on my ((card|account))",
        "Duplicate ((payment|transaction))[[ of ${amount}]]", "((Billed|Charged)) twice this month",
        "Two charges for ((one|the same)) order", "((Duplicate|Double)) debit[[ on {day}]]"],
       ["I was ((charged|billed)) twice for order #{order}[[ on the {day}]].",
        "My ((card|bank statement|account)) shows two ((identical|matching)) charges of ${amount}.",
        "I ((see|can see|noticed)) a duplicate payment on my statement for the same order.",
        "((You've|You have)) taken ${amount} from my ((card|account)) twice for ((one|a single)) order."],
       ["Both charges ((posted|went through|cleared)) on the same day.", "My bank says both are ((settled|final)), not pending.",
        "I only ((placed|made)) one order.", "((The|My)) order number is #{order}.",
        "((A screenshot of the statement|My bank statement|The statement)) is attached."],
       ["The payment provider ((retried|re-sent the charge)) after a timeout and both attempts were captured.",
        "A duplicate authorisation was captured instead of ((voided|released))."],
       ["((Refunded|Reversed)) the duplicate charge of ${amount}; it should ((appear|show)) in ((3-5|2-4|5-7)) business days.",
        "((Voided|Cancelled)) the second payment and ((emailed|sent)) the customer the refund reference."],
       1.3),
    _I("subscription_cancelled_billed", "billing",
       ["Still ((billed|charged)) after cancelling", "((Charged|Billed)) after ((cancellation|I cancelled))",
        "Cancelled but charged ((again|anyway))", "Subscription not ((cancelled|cancelling))?",
        "Charged for a plan I ((cancelled|ended))"],
       ["I cancelled my ((subscription|plan|membership)) ((last month|on the {day}|a few weeks ago)) but was charged again.",
        "I was ((billed|charged)) ${amount} even though I ((cancelled|ended)) my ((plan|subscription)).",
        "((Why am I|How come I'm|I'm)) still being charged for the {plan} plan? I cancelled it."],
       ["I have the cancellation ((confirmation|email|reference)).", "The account still shows as ((active|live)).",
        "This is the ((second|third)) month this has happened.", "I cancelled through the ((app|website|account page))."],
       ["The cancellation was scheduled for the end of the term but the renewal ran first.",
        "The cancellation request ((did not sync|never reached)) the billing system."],
       ["Cancelled the subscription, refunded the last charge and confirmed by email.",
        "Issued a full refund of ${amount} and closed the subscription."],
       1.2),
    _I("invoice_request", "billing",
       ["Need a VAT invoice", "Invoice for order #{order}", "Request for ((invoice|receipt)) copy",
        "Company details on ((invoice|receipt))", "((Receipt|Invoice)) missing", "Invoice for {month} please"],
       ["Could you ((send|email)) me an invoice for order #{order}?",
        "I need a VAT invoice with my company name for my last payment[[ of ${amount}]].",
        "I can't find the ((receipt|invoice)) for my payment of ${amount}.",
        "Our ((finance|accounts)) team needs a ((proper|VAT|itemised)) invoice for {month}."],
       ["Our finance team needs it by the end of the month.", "The billing email went to an old address.",
        "The company name is {company}.", "We need the VAT number on it."],
       ["The invoice email was sent to an outdated address.",
        "Company details were not on the account when the invoice was generated."],
       ["Regenerated the invoice with the company details and sent it to the customer.",
        "Updated the billing email and resent all invoices from this year."],
       0.6),
    _I("payment_declined", "billing",
       ["Payment declined at checkout", "Card keeps ((getting declined|failing))", "Can't ((complete|make)) payment",
        "Checkout payment error", "((Payment|Card)) rejected[[ again]]"],
       ["My payment keeps ((failing|getting declined)) at checkout, I've tried {n} different cards.",
        "Checkout says my card was declined but my bank says there's no ((block|problem)).",
        "Every time I try to pay ((it|the site)) says 'payment could not be processed'."],
       ["The error just says 'payment could not be processed'.", "It worked fine ((last week|last month|before)).",
        "I'm trying to pay ${amount}.", "I tried on {browser} and in the app."],
       ["The card issuer rejected the transaction under 3-D Secure.", "The billing postcode did not match the card."],
       ["Asked the customer to complete 3-D Secure in their banking app; payment went through.",
        "Corrected the billing postcode on the account and the payment succeeded."],
       1.1),
    _I("price_dispute", "billing",
       ["Wrong price charged", "Discount code not applied", "Promo code ((didn't work|not working))",
        "Charged full price", "Code {code} ((not accepted|rejected))"],
       ["I was charged full price even though I used the code {code}.",
        "The price at checkout was ((higher|more)) than the price on the product page.",
        "((Your|The)) code {code} ((didn't|wouldn't)) apply and I paid ${amount} instead."],
       ["The code was still valid according to your email.", "The difference is ${amount}.",
        "The {item} was on offer when I ordered."],
       ["The promo code excluded sale items.", "The product page showed a cached price."],
       ["Refunded the ${amount} difference as a goodwill gesture.", "Applied the discount retroactively and refunded the difference."],
       0.8),
    # shipping
    _I("not_received", "shipping",
       ["Order #{order} not ((received|arrived))", "((Package|Parcel)) marked delivered but not here",
        "Where is my ((order|parcel))?", "Missing ((parcel|delivery))", "Never ((received|got)) my {item}",
        "Delivered? ((No|Not here|Nothing here))"],
       ["My order #{order} shows as delivered but I haven't received ((anything|it|a thing)).",
        "Tracking says my ((parcel|package)) was delivered on the {day} but it isn't here.",
        "I ordered {n} weeks ago and the ((parcel|{item})) still hasn't arrived.",
        "The courier says ((they left it|it was left)) ((with a neighbour|in a safe place|at the door)) but there's nothing."],
       ["I've checked with ((neighbours|the neighbours)) and the building's ((mailroom|concierge)).",
        "There's no photo of the delivery in the tracking.", "I was ((home|in)) all day.",
        "I live in a ((flat|block of flats)) in {city}.", "It was meant to be a ((present|gift)) for {occasion}."],
       ["The courier left the parcel at a neighbouring address.", "The parcel was lost in transit at the regional depot."],
       ["Shipped a replacement with express delivery at no charge.", "Opened a claim with the courier and refunded the order in full."],
       1.2),
    _I("delayed", "shipping",
       ["Delivery delayed", "Order still processing", "Shipping taking ((too long|ages|forever))",
        "When will order #{order} ship?", "Tracking not updating", "Late delivery[[ - order #{order}]]"],
       ["My order #{order} has been 'processing' for {n} days.", "Tracking hasn't updated since the {day}.",
        "The estimated delivery date has passed[[ and I've heard nothing]].",
        "I paid for ((express|next-day)) delivery and it's been {n} days."],
       ["I need it before the weekend.", "I paid for express shipping.", "It's for {occasion}.",
        "I'm away from the {day} so timing matters."],
       ["The item was backordered at the warehouse.", "The parcel was held at customs pending paperwork."],
       ["Upgraded shipping to express and refunded the shipping fee.", "Confirmed a new dispatch date with the warehouse and updated the customer."],
       1.0),
    _I("damaged", "shipping",
       ["Item arrived damaged", "Broken on arrival", "Damaged packaging, item cracked",
        "Order #{order} arrived broken", "{item} ((cracked|smashed|dented)) in transit"],
       ["My order arrived ((today|this morning|yesterday)) and the {item} is ((cracked|broken|dented)).",
        "The box was ((crushed|soaked|torn open)) and the {item} inside is damaged.",
        "((Opened|Unpacked)) my {item} and ((it's|it was)) ((in pieces|scratched all over|missing a leg))."],
       ["I've attached photos of the box and the item.", "The outer packaging was torn.",
        "The courier ((threw|dropped)) it over the gate.", "It cost ${amount}, so I'd like this sorted."],
       ["Insufficient packaging for a fragile item.", "The parcel was damaged in transit by the courier."],
       ["Sent a replacement and asked the customer to keep the damaged item.", "Refunded the item and flagged the SKU for better packaging."],
       1.0),
    _I("change_address", "shipping",
       ["Change delivery address", "Wrong shipping address", "Update address on order #{order}",
        "Moved house - new address", "Delivery address typo"],
       ["I entered the wrong delivery address for order #{order}.",
        "Can I change the shipping address on my order? I've ((moved|just moved house)).",
        "There's a typo in my postcode on order #{order}."],
       ["The order hasn't shipped yet.", "The new address is in {city}.", "It's the same street, different flat number."],
       ["The customer selected an old saved address at checkout."],
       ["Updated the address before dispatch and confirmed with the customer.", "Redirected the parcel through the courier's portal."],
       0.7),
    # returns
    _I("return_request", "returns",
       ["Return request for order #{order}", "How do I return ((an item|my {item}))?", "Return label please",
        "Want to return {item}", "Exchange for a different size", "Return - {item}"],
       ["I'd like to return the {item} from order #{order}.",
        "The {item} ((doesn't fit|is too small|is too big)), can I exchange it for a different size?",
        "How do I start a return? I can't find the option in my account.",
        "The {item} isn't ((what I expected|right for me|the colour shown)), I'd like to send it back."],
       ["It's unworn with the tags still on.", "I ordered it {n} days ago.", "I still have the original box."],
       ["The return window was still open.", "The return option was hidden for marketplace items."],
       ["Emailed a prepaid return label; refund will be issued on receipt.", "Arranged an exchange and dispatched the new size."],
       0.6),
    _I("refund_not_received", "returns",
       ["Refund not received", "Where is my refund?", "Returned item, no refund yet",
        "Refund for order #{order}", "Still waiting for ${amount} refund"],
       ["I returned my order {n} weeks ago and still haven't had a refund.",
        "The courier confirmed my return was delivered but no refund has been issued.",
        "It's been {n} weeks since I sent back the {item} and ((nothing|no refund|no money))."],
       ["The tracking shows it arrived at your warehouse on the {day}.", "The refund amount should be ${amount}.",
        "I have the return receipt from the drop-off point."],
       ["The return was received but not scanned into the returns system.", "The refund was issued to an expired card."],
       ["Processed the refund of ${amount} manually and sent confirmation.", "Reissued the refund as store credit at the customer's request."],
       1.0),
    _I("wrong_item", "returns",
       ["Wrong item received", "Received the wrong size", "Not what I ordered", "Wrong colour sent",
        "Got someone else's order?"],
       ["I ordered the {item} but received something completely different.",
        "I received the wrong size in order #{order}.",
        "The ((colour|model|size)) I got isn't the one I ordered."],
       ["The packing slip shows the right item.", "I've attached a photo of what arrived.",
        "The label has someone else's name on it."],
       ["A picking error at the warehouse.", "Two orders were swapped at packing."],
       ["Sent the correct item by express and a return label for the wrong one.", "Refunded the order and arranged a courier collection."],
       0.9),
    # technical
    _I("app_crash", "technical",
       ["App crashes on startup", "App keeps crashing", "Crash when opening settings",
        "iOS app closes immediately", "Android app freezing", "App crash after update {version}"],
       ["The app crashes every time I open the ((settings|profile|orders)) page.",
        "Since the latest update the app closes as soon as I open it.",
        "The app freezes on the loading screen[[ on my {device}]].",
        "Every time I tap ((checkout|my basket|notifications)) the app ((crashes|closes|goes white))."],
       ["I'm on version {version}.", "I've reinstalled it twice.", "It works fine on my tablet but not my phone.",
        "I'm using a {device}."],
       ["A null pointer in the settings screen for accounts without a profile photo.", "A bug in release {version} on older OS versions."],
       ["Fix shipped in version {version}; confirmed with the customer after updating.", "Shared a workaround (clear app data) and linked the bug to the next release."],
       1.2),
    _I("login_error", "technical",
       ["Error 500 on login", "Login page not loading", "Stuck on loading screen", "Can't log in on mobile",
        "Login broken[[ since {when}]]"],
       ["I get an error 500 every time I try to log in.", "The login page just ((spins|hangs|keeps loading)) and never loads.",
        "I can't get past the login screen on {browser}."],
       ["It happens on Chrome and Safari.", "Started this morning.", "My colleagues have the same problem."],
       ["A failed deploy on the authentication service.", "An expired TLS certificate on the login subdomain."],
       ["Rolled back the deploy; logins are working again.", "Renewed the certificate and confirmed login with the customer."],
       1.6),
    _I("export_broken", "technical",
       ["CSV export is empty", "Export not working", "Report download fails", "Data export stuck at 0%",
        "{month} report won't download"],
       ["The export feature produces an empty CSV file.", "When I download the monthly report the file is blank.",
        "The export ((gets stuck at|hangs at|freezes at)) {n}0% and never finishes."],
       ["It worked last month with the same filters.", "The table on screen has data.", "I need it for a meeting on {weekday}."],
       ["The export timed out for date ranges over a year.", "A filter on the archived field excluded every row."],
       ["Increased the export timeout; export works for the full date range.", "Fixed the filter and re-ran the export for the customer."],
       0.9),
    _I("api_key", "technical",
       ["API key not working", "401 errors from the API", "Regenerated key rejected", "API authentication failing"],
       ["My API key returns 401 since I regenerated it.", "Every API call fails with 'invalid credentials' since {when}.",
        "Our ((integration|script|nightly job)) gets 401 ((Unauthorized|errors)) on every request."],
       ["The key is copied exactly from the dashboard.", "The old key also stopped working.", "We're on the {plan} plan."],
       ["The new key had not been granted the write scope.", "The key was created in the sandbox environment, not production."],
       ["Added the missing scope to the key; calls succeed now.", "Pointed the customer to the production key and confirmed a successful call."],
       1.2),
    _I("integration", "technical",
       ["Integration stopped syncing", "Webhook not firing", "Slack notifications stopped",
        "Sync error with calendar", "Zapier integration broken"],
       ["The integration stopped sending notifications on the {day}.", "Webhooks are no longer reaching our endpoint.",
        "Our calendar sync has been failing since the {day}."],
       ["Nothing changed on our side.", "The status page shows everything green.", "About {n}0 events are missing."],
       ["The OAuth token expired and the refresh failed silently.", "The webhook endpoint was disabled after repeated timeouts."],
       ["Reconnected the integration and replayed the missed events.", "Re-enabled the webhook and advised the customer to respond within 10 seconds."],
       1.1),
    _I("slow", "technical",
       ["Dashboard very slow", "Pages taking ages to load", "Performance issues", "Site is really slow today",
        "Everything timing out"],
       ["The dashboard takes over {n}0 seconds to load.", "Everything has been ((very|really|painfully)) slow since {when}.",
        "Pages ((time out|hang|take minutes)) whenever I open ((reports|the dashboard|our account))."],
       ["It's affecting the whole team.", "Other websites are fine.", "We're in {city}, if that matters."],
       ["A slow database query on accounts with large histories.", "A regional CDN outage."],
       ["Added an index for the slow query; load time is back under two seconds.", "CDN provider resolved the outage; confirmed performance is normal."],
       1.3),
    # account
    _I("password_reset", "account",
       ["Password reset email not arriving", "Can't reset password", "Reset link expired",
        "Locked out of my account", "Forgot password, no email"],
       ["I've requested a password reset {n} times but the email never arrives.",
        "The password reset link says it has expired as soon as I click it.",
        "I'm locked out after too many login attempts."],
       ["I've checked my spam folder.", "I'm using the email address on my account.", "I'm on a {device}."],
       ["Reset emails to this domain were being blocked by the recipient's mail server.", "The account was locked after repeated failed attempts."],
       ["Unlocked the account and sent a reset link to a verified backup address.", "Reset the password manually and enabled two-factor authentication."],
       1.0),
    _I("two_factor_sms", "account",
       ["2FA code not arriving", "Verification code never comes", "No SMS code", "Two-factor problem"],
       ["Two-factor authentication isn't sending the verification code.", "I never receive the SMS code when I try to log in.",
        "The text with my login code ((never arrives|takes 20 minutes|comes after it's expired))."],
       ["My phone number hasn't changed.", "I've waited over ten minutes for it.", "I'm with a different mobile network now."],
       ["SMS delivery to the customer's carrier was delayed.", "The phone number on file was missing the country code."],
       ["Switched the customer to app-based codes after SMS delays.", "Corrected the phone number format; codes arrive now."],
       1.1),
    _I("two_factor_device", "account",
       ["Lost access to authenticator", "New phone, can't log in", "Reset 2FA please"],
       ["I got a new phone and lost my authenticator app.", "My old phone broke and I can't get past the two-factor step."],
       ["I still have access to my email.", "I don't have the backup codes.", "The new phone is a {device}."],
       ["The authenticator was tied to the old device."],
       ["Verified identity and reset two-factor; customer re-enrolled successfully.", "Reset two-factor after ID check and sent new backup codes."],
       1.1),
    _I("change_email", "account",
       ["Change email address", "Update my email", "New email for my account", "Can't update email"],
       ["How do I change the email address on my account?", "I'm trying to update my email but the field is greyed out."],
       ["The old email is no longer active.", "I signed up with Google originally.", "I've left {company}, so that address is gone."],
       ["The email field is read-only for accounts created via social login.", "The new address was already linked to a second account."],
       ["Updated the email after verifying the customer's identity.", "Released the address from the unused account and updated the email."],
       0.5),
    _I("merge_accounts", "account",
       ["Merge two accounts", "Duplicate accounts", "Two accounts, same person"],
       ["I have two accounts and would like to merge them.", "I accidentally created a second account and my orders are split between them."],
       ["Both accounts are in my name.", "One uses my work email."],
       ["A second account was created at guest checkout."],
       ["Merged the accounts and kept the full order history.", "Moved the orders to the main account and closed the duplicate."],
       0.5),
    _I("delete_account", "account",
       ["Delete my account", "Close account request", "Remove my data", "GDPR deletion request"],
       ["Please delete my account and all my personal data.", "I'd like to close my account permanently."],
       ["I no longer use the service.", "Please confirm by email once it's done."],
       ["Customer requested erasure under data-protection rules."],
       ["Deleted the account and confirmed under the data-protection request.", "Closed the account and scheduled data deletion within 30 days."],
       0.6),
    _I("unsubscribe", "account",
       ["Unsubscribe from emails", "Too many marketing emails", "Still getting newsletters", "Stop sending me emails"],
       ["I keep getting marketing emails even though I unsubscribed.", "I unsubscribed {n} times and the newsletters keep coming."],
       ["I only want order updates.", "The unsubscribe link says I'm already removed."],
       ["Marketing preferences were stored per list, not per account."],
       ["Removed the customer from all marketing lists; order emails still on.", "Turned off every marketing list and confirmed the preference change."],
       0.4),
    # product
    _I("dark_mode", "product",
       ["Feature request: dark mode", "Dark mode please", "Any plans for dark mode?"],
       ["It would be great to have a dark mode in the app.", "Is a dark theme on the roadmap? The white screen is harsh at night."],
       ["Our team uses this every day.", "A competitor already offers this."],
       ["Not a defect; logged as a feature request."],
       ["Logged the request with the product team and shared the public roadmap.", "Added the customer's vote to the existing dark-mode request."],
       0.4),
    _I("bulk_edit", "product",
       ["Feature request: bulk edit", "Edit several items at once?", "Bulk update option"],
       ["Could you add a way to edit several items at once?", "Updating {n}00 records one by one takes hours. Is there a bulk edit?"],
       ["We have to do this every month."],
       ["Not a defect; bulk edit exists for admins only."],
       ["Explained the admin bulk-edit tool and raised the request for other roles.", "Shared the CSV import as a workaround and logged the request."],
       0.4),
    _I("pdf_export", "product",
       ["Can you add export to PDF?", "PDF export for reports", "Request: printable reports"],
       ["We'd love an export to PDF option for reports.", "Is there a way to save reports as PDF for our board pack?"],
       ["Right now we screenshot the dashboard."],
       ["Not a defect; logged as a feature request."],
       ["Shared the print-to-PDF workaround and logged the request.", "Added the customer to the beta for scheduled PDF reports."],
       0.4),
    _I("product_question", "product",
       ["Question about {item}", "Is this compatible?", "Sizing question", "Product information", "{item} - ((dimensions|warranty|compatibility))?"],
       ["Is the {item} compatible with my current setup?", "What are the exact dimensions of the {item}?",
        "Does the {item} come with a warranty?", "Before I order, does the {item} come in other colours?"],
       ["I couldn't find it on the product page.", "I want to buy it for {occasion}."],
       ["Information missing from the product page."],
       ["Answered with the specifications and updated the product page.", "Confirmed compatibility and sent the setup guide."],
       0.4),
]

_ISSUE_FAMILY_KEYWORDS = [
    ("returns", ("return", "refund", "exchange")),
    ("billing", ("bill", "payment", "invoice", "charge", "pay", "finance", "subscription")),
    ("shipping", ("ship", "deliver", "logistic", "order", "fulfil", "fulfill", "courier")),
    ("account", ("account", "login", "access", "auth", "security", "password", "privacy")),
    ("technical", ("tech", "bug", "software", "app", "it ", "outage", "integration", "api",
                   "incident", "error", "performance", "support")),
    ("product", ("product", "feature", "request", "feedback", "question", "inquiry",
                 "enquiry", "general", "sales", "other")),
]

_PRIORITY_RANK = {"lowest": 0, "trivial": 0, "low": 0, "minor": 0, "p4": 0, "p3": 1,
                  "normal": 1, "medium": 1, "moderate": 1, "major": 2, "high": 2, "p2": 2,
                  "urgent": 3, "critical": 3, "blocker": 3, "highest": 3, "p1": 3,
                  "p0": 3, "emergency": 3}

_OPEN_STATUSES = {"open", "new", "pending", "in progress", "in_progress", "waiting",
                  "awaiting", "on hold", "on_hold", "assigned", "escalated", "triage",
                  "reopened", "awaiting customer", "awaiting_customer", "todo", "backlog",
                  "active", "investigating", "acknowledged"}


def issue_family_for(category) -> Optional[str]:
    c = f" {str(category).strip().lower()} "
    if c.strip() in ("", "nan", "none"):
        return None
    for fam, words in _ISSUE_FAMILY_KEYWORDS:
        if any(w in c for w in words):
            return fam
    return None


def is_open_status(status) -> bool:
    s = str(status).strip().lower()
    return s in _OPEN_STATUSES or s.startswith(("open", "pending", "waiting", "in prog"))


@dataclass
class TicketFrame:
    issue: List[Issue]
    slots: List[Dict[str, str]]
    urgency: List[int]          # 0 low .. 3 urgent
    open_: List[bool]
    subject: List[str]


_FAMILY_ISSUES: Dict[str, List[Issue]] = {}
for _iss in ISSUES:
    _FAMILY_ISSUES.setdefault(_iss.family, []).append(_iss)


_DEVICES = ["iPhone 15", "iPhone 13", "Pixel 8", "Galaxy S23", "Galaxy A54", "iPad",
            "MacBook Air", "Windows laptop", "Chromebook", "work PC", "Android tablet"]
_BROWSERS = ["Chrome", "Safari", "Firefox", "Edge", "the app", "Brave"]
_WHENS = ["yesterday", "this morning", "last night", "Monday", "Tuesday", "the weekend",
          "Friday", "last week", "two days ago", "the last update", "about an hour ago"]
_PLANS = ["Basic", "Plus", "Pro", "Premium", "Business", "Family", "Starter", "Team"]


def _ticket_slots(rng, item: Optional[str]) -> Dict[str, str]:
    return _ticket_slot_rows(rng, 1, [item])[0]


def _ticket_slot_rows(rng, size: int, items: Optional[Sequence] = None) -> List[Dict[str, str]]:
    """Per-row slot values, drawn as whole columns."""
    def pick(pool):
        idx = rng.integers(0, len(pool), size)
        return [pool[i] for i in idx]
    devices, browsers, whens, plans = pick(_DEVICES), pick(_BROWSERS), pick(_WHENS), pick(_PLANS)
    from misata.vocab_seeds import CITIES_BY_COUNTRY, FIRST_NAMES, LAST_NAMES
    lnames = pick(LAST_NAMES)
    phones = [f"07{int(a):03d} {int(b):06d}" for a, b in zip(rng.integers(100, 999, size), rng.integers(0, 999999, size))]
    mails = pick(["gmail.com", "outlook.com", "yahoo.co.uk", "icloud.com", "hotmail.com", "proton.me"])
    cities = pick([c for cs in CITIES_BY_COUNTRY.values() for c in cs])
    fnames = pick(FIRST_NAMES)
    months = pick(["January", "February", "March", "April", "May", "June", "July", "August",
                   "September", "October", "November", "December"])
    weekdays = pick(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
    occasions = pick(["a birthday", "Christmas", "an anniversary", "a wedding", "my daughter's party",
                      "a trip next week", "the weekend", "my mum's birthday", "a work event"])
    companies = pick([f"{a} {b}" for a in ("Northwind", "Harbor", "Kestrel", "Lumen", "Cobalt",
                                             "Redwood", "Marlow", "Pioneer")
                      for b in ("Ltd", "Group", "Studio", "Partners", "Labs")])
    codes = pick(["SPRING20", "WELCOME10", "SAVE15", "FREESHIP", "VIP25"])
    mins = rng.integers(5, 90, size)
    last4 = rng.integers(0, 10000, size)
    refp = pick(["RF", "REF", "CR", "RMA", "INC", "CS", "TRK"])
    refn = rng.integers(10000, 999999, size)
    dd = rng.integers(1, 29, size)
    mon3 = pick(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    hh = rng.integers(7, 21, size)
    mm = rng.integers(0, 60, size)
    inits = pick([a + b for a in "ABCDEGHJKLMNPRST" for b in "ABCDEGHJKLMNPRSTW"])
    tix = rng.integers(10000, 999999, size)
    orders = rng.integers(100000, 999999, size)
    amounts = np.exp(rng.normal(3.6, 0.8, size))
    ns = rng.integers(2, 6, size)
    days = rng.integers(1, 29, size)
    va, vb, vc = rng.integers(3, 9, size), rng.integers(0, 15, size), rng.integers(0, 6, size)
    # Customers name what they bought. With no product on the row, a product
    # type from the catalogue stands in for "the item".
    _nouns = [n for k, F in PRODUCT_FAMILIES.items() if k not in ("books", "grocery", "health")
              for n in F.nouns]
    fallback_items = [_soft_lower(_nouns[j]) for j in rng.integers(0, len(_nouns), size)]
    out = []
    for i in range(size):
        it = items[i] if items is not None and i < len(items) and items[i] else fallback_items[i]
        out.append({
            "device": devices[i], "browser": browsers[i], "when": whens[i], "plan": plans[i],
            "mins": str(int(mins[i])), "order": str(int(orders[i])),
            "amount": f"{float(amounts[i]):.2f}", "n": str(int(ns[i])), "day": _day(int(days[i])),
            "code": codes[i], "version": f"{va[i]}.{vb[i]}.{vc[i]}", "item": it or "item",
            "city": cities[i], "fname": fnames[i], "month": months[i], "weekday": weekdays[i],
            "occasion": occasions[i], "company": companies[i],
            "last4": f"{int(last4[i]):04d}", "ref": f"{refp[i]}-{int(refn[i])}",
            "date": f"{int(dd[i])} {mon3[i]}", "time": f"{int(hh[i]):02d}:{int(mm[i]):02d}",
            "initials": inits[i], "ticket": str(int(tix[i])), "lname": lnames[i], "phone": phones[i],
            "email": f"{fnames[i].lower()}.{lnames[i].lower()}@{mails[i]}".replace(" ", ""),
        })
    return out


def _day(d: int) -> str:
    return f"{d}{'th' if 11 <= d <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(d % 10, 'th')}"


def draw_tickets(rng: np.random.Generator, size: int, *,
                 categories: Optional[Sequence] = None,
                 priorities: Optional[Sequence] = None,
                 statuses: Optional[Sequence] = None,
                 items: Optional[Sequence] = None) -> TicketFrame:
    """One latent support issue per row, conditioned on what the row says.

    The declared category picks the issue family; the declared priority
    leans the draw toward severe issues (an urgent ticket is a login outage
    more often than a feature request); the status decides whether the
    ticket has a resolution yet. None of those columns are changed."""
    cats = _clean_values(categories, size)
    pris = _clean_values(priorities, size)
    stats = _clean_values(statuses, size)
    items = _clean_values(items, size)
    import bisect
    issues: List[Issue] = []
    urg: List[int] = []
    fam_cache: Dict[str, Optional[str]] = {}
    cum_cache: Dict[tuple, List[float]] = {}
    draws = rng.random(size)
    noise = rng.normal(0, 0.6, size)
    for i in range(size):
        c = cats[i] if cats else ""
        if c not in fam_cache:
            fam_cache[c] = issue_family_for(c) if c else None
        fam = fam_cache[c]
        pool = (_FAMILY_ISSUES.get(fam) if fam else None) or ISSUES
        u = _PRIORITY_RANK.get(pris[i].lower(), None) if pris else None
        key = (fam, u)
        cum = cum_cache.get(key)
        if cum is None:
            # severity^(2(u-1.5)): urgent rows favour severe issues, low rows mild ones
            w = np.array([1.0 if u is None else iss.severity ** (2.0 * (u - 1.5)) for iss in pool])
            cum = np.cumsum(w / w.sum()).tolist()
            cum_cache[key] = cum
        issues.append(pool[min(bisect.bisect_right(cum, draws[i]), len(pool) - 1)])
        if u is None:
            sev = issues[-1].severity
            u = int(np.clip(round(1 + (sev - 1) * 2.5 + noise[i]), 0, 3))
        urg.append(int(u))
    open_ = [is_open_status(s) for s in stats] if stats else [False] * size
    slots = _ticket_slot_rows(rng, size, [(_noun_from_name(x) if x else None) for x in items]
                              if items else None)
    subjects = []
    for i, iss in enumerate(issues):
        if rng.random() < 0.55 and iss.family in _FAMILY_SUBJECTS and iss.key not in _SPECIFIC_ONLY:
            s = _fill(str(_pick(rng, _FAMILY_SUBJECTS[iss.family])), rng, slots[i])
        else:
            s = _fill(str(_pick(rng, iss.subjects)), rng, slots[i])
        q = rng.random()
        if q < 0.5:
            pool = _SUBJECT_SUFFIXES + ([" - {item}"] * 3 if iss.family in ("shipping", "returns") else [])
            s = s + _fill(str(_pick(rng, pool)), rng, slots[i])
            q = 1.0
        if q < 0.12 and "#" not in s and iss.family in ("billing", "shipping", "returns"):
            s = f"{s} (order #{slots[i]['order']})"
        elif q < 0.2 and iss.family == "technical":
            s = f"{s} since {slots[i]['when']}"
        elif q < 0.26 and iss.family in ("technical",):
            s = f"{s} on {slots[i]['device']}"
        elif q < 0.32 and items and items[i]:
            s = f"{s} - {items[i] if len(items[i]) < 40 else slots[i]['item']}"
        elif q < 0.36:
            s = f"{_pick(rng, ['Help: ', 'Question: ', 'Issue: ', 'Problem: '])}{s[0].lower() + s[1:]}"
        r = rng.random()
        if r < 0.06:
            s = f"Re: {s}"
        elif r < 0.10:
            s = s.lower()
        elif r < 0.13 and urg[i] >= 2:
            s = f"URGENT: {s}"
        elif r < 0.16:
            s = f"{s}!"
        subjects.append(s)
    from misata.paraphrase import vary
    subjects = vary(subjects, rng, "casual", rate=0.5, short=True)
    return TicketFrame(issues, slots, urg, open_, subjects)


# Family-level subject lines; each names its topic so the subject still says
# what the ticket is about.
_FAMILY_SUBJECTS = {
    "billing": ["((Charge|Payment|Billing|Invoice|Refund)) ((query|issue|problem|question|error))[[ - order #{order}]]",
                "((Wrong|Extra|Duplicate|Unexpected)) ((charge|payment|bill))[[ of ${amount}]][[ on {date}]]",
                "((Billing|Payment)) ((help|issue)) ((for {month}|on card {last4}|re ${amount}|- {plan} plan))"],
    "shipping": ["((Order|Delivery|Parcel|Shipping)) ((problem|issue|query|delay)) - #{order}",
                 "((My|Our)) {item} ((order|delivery)) ((hasn't arrived|is late|is missing|is stuck))",
                 "((Delivery|Shipping)) ((update|status|ETA)) ((for order #{order}|for my {item}|please))"],
    "returns": ["((Return|Refund|Exchange)) ((request|query|issue)) ((- {item}|for order #{order}|re ${amount}))",
                "((Returning|Sending back|Exchanging)) ((my|the|a)) {item}"],
    "technical": ["((App|Website|Login|Export|Sync|API|Dashboard)) ((error|issue|problem|not working|down))[[ on {device}]]",
                  "((Error|Bug|Crash)) ((in|on|with)) ((the app|the dashboard|checkout|reports|the API))[[ ({version})]]",
                  "((Can't|Cannot|Unable to)) ((log in|export|upload|sync|load the dashboard))[[ - {browser}]]"],
    "account": ["((Account|Login|Password|Email|2FA)) ((issue|problem|help|question|access))[[ - {email}]]",
                "((Help with|Problem with|Question about)) my ((account|login|password|email address|two-factor))",
                "((Locked out|Can't log in|No access)) ((of|to)) ((my|our)) account"],
}
_SUBJECT_SUFFIXES = [" (order #{order})", " - ref {ref}", " - {weekday}", " ({fname})", " - {plan} plan",
                     " - since {date}", " [#{ticket}]", " - {city}", " [{fname} {lname}]", " - {date}",
                     " (request #{n})", " - please help", " - {company}", " - urgent?", " ?", " - account {last4}"]

_GREETINGS = ["Hi,", "Hello,", "Hi there,", "Hello team,", "Hey,", "Good morning,", "Dear support,",
              "Hi support,", "Hello there,", "Good afternoon,", "To whom it may concern,", "Hiya,"]
_LEADS = ["", "", "", "", "", "", "", "", "", "", "So, ", "Quick one: ", "((For the second time|Again|Once more)), ",
          "((Hoping|Hope)) you can help. ", "((Not sure who to ask|Not sure where to send this)), but ",
          "Following up on my ((chat|call|last email)): ", "As the ((title|subject)) says, ", "((Sorry to bother you|Apologies for the hassle)), but ",
          "((I hope this is the right place|Hope this is the right inbox)). ", "((Second|Third)) ((email|message)) about this. ",
          "((Writing again|Messaging again|Back again)) because ", "((Just a heads up|FYI|Heads up)), ", "((Bit of a|Slight|Big)) problem: ",
          "Help please. ", "Hi again. ", "Urgent: ", "((Long story short|In short|Basically)), ", "((Right|OK|Okay)), so "]
_CONTEXT_LINES = {
    "any": ["((This|It)) ((started|began)) {when}.", "I first ((noticed|spotted)) it {when}.", "I'm on the {plan} plan.",
            "My account email is ((the one on this ticket|the one I'm writing from|{fname}'s work address)).",
            "I've been a customer for {n} years.", "I've waited {mins} minutes on chat already.",
            "This is my ((second|third|fourth)) time asking.", "I'm based in {city}.",
            "((Reference|Case|Ticket)) number from last time was #{order}.", "Happy to jump on a call ((on {weekday}|any time|this week)).",
            "((You can|Feel free to)) ((reach|call|ring)) me on {phone}((.| any time.| after {time}.))",
            "((My|The account)) email is {email}.", "((Order|Account)) is under {fname} {lname}."],
    "technical": ["I'm using {browser} on a {device}.", "Same thing on my {device}.",
                  "It started after the {version} update.", "Screenshot attached.",
                  "Our whole team on the {plan} plan sees it.", "Happens every time, not just once."],
    "account": ["I'm on a {device}.", "I tried from {browser} as well.",
                "I'm travelling, so I can't get to my usual laptop."],
    "billing": ["The charge was ${amount}.", "My order number is #{order}.",
                "Statement screenshot attached.", "I'm on the {plan} plan."],
    "shipping": ["My order number is #{order}.", "I paid ${amount} for it.",
                 "The tracking link just says 'in transit'.", "It was a gift, so timing matters."],
    "returns": ["Order #{order}.", "It cost ${amount}.", "I still have the original packaging.",
                "I sent it back {when}."],
    "product": ["We're on the {plan} plan.", "I'd happily pay more for this.",
                "Using it on a {device} mostly."],
}
_TRIED = ["I've ((tried|already tried)) ((logging out and back in|restarting|reinstalling|a different browser|clearing the cache)).",
          "I've already cleared my ((cache|cookies|cache and cookies|browser history)).",
          "((Tried|I tried)) ((a different browser|another device|my phone|incognito mode)) ((with the same result|and same thing|no luck)).",
          "((Restarting|Rebooting|Turning it off and on)) ((didn't help|made no difference|did nothing)).",
          "I ((checked|searched|read)) the help ((centre|center|articles)) but ((couldn't find an answer|nothing matched|it didn't cover this)).",
          "I contacted you on chat ((but the conversation dropped|and was told to email|yesterday but nothing happened))."]
_IMPACT = {
    0: ["((No rush|No hurry|Not urgent)), ((just wanted to flag it|just letting you know|whenever suits)).",
        "((No hurry|No rush)) on this ((one|at all|really)).",
        "((Whenever you get a chance|When you get a chance|Whenever you have a minute|In your own time)).",
        "((Low priority|Not a big deal|Minor thing)) ((for us|really|honestly)), ((but|though)) ((worth fixing|thought you should know|it's a bit annoying)).",
        ""],
    1: ["((Could|Can|Would)) you ((look into|check|have a look at)) this((?| please?| when you can?))",
        "Please let me know ((what to do|how to fix it|what you need from me|the next steps)).",
        "((Thanks|Thank you)) ((for your help|in advance|for looking))((.|!))",
        "((Would|I'd)) ((appreciate|be grateful for)) ((a reply|an update|some help)) ((this week|soon|when possible)).",
        ""],
    2: ["This is affecting ((my work|our team|my business|my orders)), ((please help|please prioritise it|can you speed this up)).",
        "I need this ((sorted|fixed|resolved|sorted out)) ((this week|by {weekday}|before the weekend|in the next day or two)).",
        "Please look into this as soon as ((possible|you can|you're able)).",
        "((It's|This is)) ((holding up|delaying|blocking)) ((our launch|a client project|month-end|my order for {occasion})).",
        "((We've|I've)) ((lost|wasted)) ((a whole morning|two days|hours)) on this ((already|so far|now))."],
    3: ["((This is|It's)) urgent, we ((can't operate|can't take orders|can't work|are completely stuck)).",
        "Please escalate, this is blocking ((our whole team|everyone|all {n}0 of our users|the entire office)).",
        "We need this ((fixed|sorted|resolved)) ((today|right now|within the hour|by end of day)).",
        "((Every hour this is down|Every minute this is down|Each hour of downtime|Right now this)) ((costs us money|loses us customers|is a disaster)).",
        "((Escalating as critical|Flagging as critical|Marking this critical|Calling this a P1)): ((nobody|no one|none of us)) can ((log in|work|check out))."],
}
_INTROS = ["My name is {fname} and I've been a customer ((for {n} years|since {month}|for a while)).",
           "((Hi, it's|This is)) {fname}((.| again.| from {company}.))",
           "((I'm|We're)) ((writing|getting in touch)) ((from {company}|about my account|about an order)).",
           "((Long-time|Regular|New)) customer here."]
_ASKS = {
    "any": ["Can you ((help|look into this|sort this out)) ((please|asap|today|this week))?",
            "((How do I|Can you tell me how to)) ((fix this|sort this|get this sorted))?",
            "Please ((advise|let me know|get back to me)) ((asap|soon|when you can)).",
            "((Could|Can)) someone ((call|email|message)) me ((back|about this))?",
            "((Let me know|Tell me)) ((if you need|what else you need|if there's anything else)) ((from me|to sort this|))((.|?))",
            "((Really|Very|Would be)) ((grateful|thankful|appreciative)) for ((a quick reply|any help|a fix))((.|!))"],
    "billing": ["((Please|Can you)) refund ((the extra charge|the duplicate charge|me the ${amount}|the difference)).",
                "((I'd like|I want|Please arrange)) ((a refund|my money back|a credit)) ((asap|today|this week))."],
    "shipping": ["((Can you|Please)) ((send a replacement|chase the courier|tell me where it is|refund me)).",
                 "((When|By when)) will it ((arrive|be delivered|get here))?"],
    "returns": ["((Please|Can you)) ((send me a return label|process my refund|arrange a collection)).",
                "((How long|When)) will the refund ((take|come through|show up))?"],
    "technical": ["((Is there|Do you have)) ((a fix|a workaround|an ETA)) for this?",
                  "((Please|Can you)) ((escalate|look into|fix)) this ((asap|urgently|today))."],
    "account": ["((Can you|Please)) ((reset|unlock|update)) ((it|my account|this)) for me?",
                "((What|Which)) ((details|ID|information)) do you need from me?"],
    "product": ["((Any|Is there an)) ((ETA|timeline|update)) on this?", "((Would|Will)) this be ((possible|added|considered))?"],
}
_SIGNOFFS = ["Thanks", "Thanks,", "Thank you", "Cheers", "Regards", "Best", "Many thanks"]
_PREFACES = ["((Spoke to|Called|Rang)) the customer ((by phone|this morning|on {weekday})). ",
             "Per ((chat|email|phone call)) with the customer: ", "((Checked|Reviewed|Pulled)) the ((logs|order history|payment logs|account notes)). ",
             "Escalated to ((tier 2|engineering|the billing team|a supervisor)). ", "((Reproduced|Confirmed)) the issue((| on {device}| in staging)). ",
             "((Verified|Checked)) the account((| and ID| and order)). ", "Investigated with ((engineering|the warehouse|the courier|billing)). ",
             "Customer ((called back|replied|chased)) ((on {weekday}|today|after {n} days)). ", "((Followed up|Replied)) by ((email|chat|phone)). ",
             "((Looked into|Picked up)) this ((with the warehouse|from the queue|after the handover)). "]
# What customers write, by family: a second symptom or a concrete detail,
# full of the order numbers, amounts, dates and devices real tickets carry.
_FAMILY_SYMPTOMS = {
    "billing": ["((I've been|I was|We've been)) ((charged|billed|debited)) ${amount} ((twice|for something I didn't order|after cancelling|more than the price shown)) ((on {date}|this month|on my card ending {last4})).",
                "((There's|I see|My bank shows)) ((a charge|a payment|a debit)) of ${amount} ((I don't recognise|that shouldn't be there|from {date})) ((on my statement|on card {last4}|from you)).",
                "((Your|The)) ((renewal|subscription|monthly charge)) ((jumped|went up|changed)) from ((${amount}|the usual price)) ((without warning|on {date}|this month)) ((on my account|for the {plan} plan)).",
                "((Just|I've just|I have just)) ((noticed|seen|spotted)) ((two|duplicate|extra)) ((payments|charges|debits)) ((totalling|of|adding up to)) ${amount} ((from {date}|this {weekday}|for order #{order})).",
                "((Got|Received)) ((an email|a receipt|a notification)) ((saying|that says)) I paid ${amount} ((on {date}|at {time}|today)) but ((I never ordered|that's wrong|my plan is cheaper)).",
                "((Was|I was|We were)) ((promised|told|quoted)) ${amount} ((on chat|by your sales team|on {date})) but ((charged more|billed the full price|invoiced differently)) ((on card {last4}|this month|for the {plan} plan))."],
    "shipping": ["((My|Our)) {item} ((was due|should have arrived|was promised)) ((on {date}|by {weekday}|last {weekday})) and ((still isn't here|hasn't turned up|there's no sign of it)).",
                 "Order #{order} ((says delivered|shows as delivered|was marked delivered)) at {time} on {date} but ((nobody|no one|nothing)) ((was left|came|turned up)).",
                "((Tracking|The courier)) ((has shown|says|keeps saying)) (('out for delivery'|'delayed'|'exception')) ((since {date}|for {n} days|every day this week)) for order #{order}.",
                "((Ordered|Bought|Paid for)) ((a|the|my)) {item} ((on {date}|{n} weeks ago|last {weekday})) ((with next-day delivery|with express shipping|for ${amount})) and ((it's not here|nothing yet|still waiting)).",
                "((Driver|Courier|The delivery app)) ((says|claims|shows)) ((they tried to deliver|nobody was in|it was left in a safe place)) ((at {time}|on {date})) but ((I was home|that's not true|there's nothing here)).",
                "((Parcel|Package|My {item})) ((was meant to come|was booked for|was scheduled for)) {date} ((between|from)) ((8 and 12|1 and 5|9 and 6)) and ((nothing came|no-one showed|it was rescheduled without asking)).",
                "((Only|Just)) ((half|part|one box)) of order #{order} ((arrived|turned up|was delivered)) ((on {date}|today|this {weekday})), the {item} is ((missing|not there|nowhere))."],
    "returns": ["((I|We)) ((sent back|returned|posted back)) the {item} ((on {date}|{n} weeks ago|last {weekday})) and ((the refund of ${amount} hasn't appeared|still no refund|heard nothing since)).",
                "The {item} ((doesn't fit|is the wrong colour|isn't as described|arrived faulty)) and I want to ((return|exchange|swap)) it ((before {date}|this week|asap)).",
                "((Need|Want|I'd like)) to ((return|send back|exchange)) ((the|my)) {item} from order #{order} ((bought on {date}|that arrived {weekday}|which cost ${amount}))."],
    "technical": ["((Since|From)) {date} ((the app|the dashboard|your site|the export)) ((keeps crashing|won't load|throws an error|logs me out)) ((on my {device}|in {browser}|for everyone on our {plan} plan)).",
                  "((Every time|Whenever|Each time)) I ((open|try|tap)) ((reports|checkout|settings|the dashboard)) ((on {device}|in {browser})) it ((freezes|crashes|spins forever|shows a blank page)).",
                "((Our|My)) ((sync|integration|export|report)) ((failed|stopped|broke)) ((at {time} on {date}|overnight on {date}|after {version})) ((with error {n}0{n}|without any error|and hasn't recovered)).",
                "((Getting|Seeing|Hitting)) ((error|code)) {n}0{n} ((when|whenever|every time)) I ((upload|export|log in|save)) ((on {device}|in {browser}|since {date})).",
                "((The|Our)) {plan} ((workspace|account|dashboard)) ((went down|stopped loading|became really slow)) ((at {time} on {date}|this morning around {time}|after the {version} release)).",
                "((Can't|Cannot|Unable to)) ((save|upload|export|sync|print)) ((anything|my {month} report|files over {n}MB|invoices)) ((since {date}|from {browser}|on the {plan} plan)), ((it just|the page|the app)) ((times out|errors|goes blank)).",
                "((Notifications|Emails|Alerts|Webhooks)) ((stopped|aren't|haven't been)) ((arriving|sending|coming through)) ((since {date}|after {time} yesterday|for {n} days)) ((for our team|on {device}|in {city})).",
                "((Two|Several|All)) of our ((users|staff|team members)) ((got logged out|lost their data|see a blank screen)) ((at {time}|this morning|on {date})) ((using|on|in)) ((Chrome|Safari|the app|{device}))."],
    "account": ["((I can't|I'm unable to|I cannot)) ((log in|get into my account|reset my password|get the code)) ((on my {device}|since {date}|from {city}|after changing phones)).",
                "((My|The)) ((login|account|password reset|two-factor code)) ((stopped working|is broken|never arrives)) ((on {date}|since {weekday}|after the {version} update)).",
                "((Locked out|Can't sign in|Blocked)) ((after|since)) (({n} wrong attempts|changing my email|a password reset on {date}))((.|, please help.))",
                "((Trying|I'm trying|Been trying)) to ((update|change|recover)) ((my email|my password|my phone number|my login)) ((since {date}|for {n} days|all morning)) and ((it won't save|nothing works|the link expires))."],
    "product": ["((Could you|Can you|Would you)) ((add|build|support)) ((dark mode|bulk editing|PDF export|a {device} app|more integrations)) ((for the {plan} plan|soon|this year))?"],
}

_FAMILY_DETAILS = {
    "billing": ["((The charge|It|The payment)) ((shows as|is listed as|appears as)) ${amount} on ((my card ending {last4}|my statement|my banking app)) ((dated {date}|from {date}|on {date})).",
                "((My|Our)) ((invoice|receipt|account page)) says ((one thing|${amount}|the {plan} plan)) but ((my bank says another|I was charged more|I'm on a different plan)).",
                "((I've|We've)) been a {plan} customer since {month} and ((this has never happened|never had an issue|always paid on time)).",
                "((Order|Invoice|Transaction)) ((number|ref|ID)) is ((#{order}|{ref})), ((paid|charged)) on {date}.",
                "((I|We)) ((only|just)) ((ordered|bought|signed up for)) ((the {item}|one {item}|the {plan} plan)) ((on {date}|in {month}|last {weekday})), nothing else.",
                "((Can you|Please)) ((check|look at)) ((transaction|payment|invoice)) {ref} ((from {date}|for ${amount}|on card {last4}))?"],
    "shipping": ["((Tracking|The tracking page|The courier app)) ((last updated|has said 'in transit' since|shows nothing after)) {date} ((at {time}|in {city}|at the depot)).",
                 "((I'm|We're)) in {city} and the ((estimated|promised|quoted)) date was {date}.",
                 "Order #{order} ((for the {item}|placed on {date}|paid ${amount})) ((still hasn't moved|is stuck|shows as delivered)).",
                 "((I've|We've)) ((called|emailed|messaged)) the courier ((twice|three times|already)) and they ((say to contact you|have no record|keep saying tomorrow)).",
                "((The|My)) ((neighbour|concierge|building manager)) ((hasn't seen it|says nothing came|checked the CCTV)) ((on {date}|that day|at {time})).",
                "((I|We)) ((need|wanted)) the {item} for {occasion} ((on {date}|this {weekday}|next week)), ((so this is a problem|so I'm worried|so please hurry))."],
    "returns": ["((I|We)) ((dropped it off|sent it back|posted it)) at ((the post office|a locker|the shop in {city})) on {date}, ((receipt attached|tracking {ref}|still have the slip)).",
                "((The|My)) {item} ((cost|was)) ${amount} and ((the refund should go|I paid with|it was charged to)) ((card ending {last4}|my original card|PayPal)).",
                "((It's|That's)) been {n} ((weeks|working days|days)) since ((your warehouse|you|the depot)) ((got it|signed for it|received it)).",
                "((Return|Drop-off)) ((reference|code|label number)) ((is|was)) {ref}((.|, from {city}.| if that helps.))",
                "((Your|The)) ((website|returns page|app)) ((still says|shows|says)) (('awaiting return'|'in transit'|nothing)) ((for order #{order}|since {date}))."],
    "technical": ["((I'm|We're)) on {browser} ((on a|using a|with a)) {device}, ((app|version)) {version}.",
                  "((It|The error)) ((started|first appeared|kicked in)) on {date} around {time}.",
                  "((Error|The message)) says ((\"something went wrong\"|code {n}0{n}|'request failed'|'session expired')) ((every time|after a few seconds|at random)).",
                  "((About|Roughly|At least)) {n}0 ((people|users|of our staff)) on the {plan} plan ((are affected|see the same thing|can't work)).",
                "((Screenshot|Screen recording|Console log)) ((attached|is attached|below)), ((taken at|from|captured)) {time} on {date}.",
                "((Same|It's the same)) on ((my|our)) ((laptop|work PC|second account|colleague {fname}'s machine)) ((in {city}|at home|in the office))."],
    "account": ["((I'm|I am)) trying on ((my|a)) {device} ((with|in|using)) {browser}((.|, if that helps.))",
                "((The|My)) account email ((is|should be)) ((my work one at {company}|the one I signed up with in {month}|{fname}'s address)).",
                "((Last|The last time I)) logged in[[ successfully]] ((on {date}|in {month}|a few weeks ago)).",
                "((My|The)) ((phone number|mobile|backup email)) ((ends in|is the one ending)) {last4}((.|, still the same.))",
                "((I signed up|I opened the account|I joined)) ((in {month}|on {date}|years ago)) ((with|through|using)) ((Google|Apple|my email|{company} SSO))."],
    "product": ["((We|I)) ((use|rely on)) ((this|the app|your tool)) ((every day|daily|for {company})) ((on the {plan} plan|across {n}0 seats|on {device}))."],
}

_FAMILY_CAUSES = {
    "billing": ["((The payment gateway|Our card processor|The billing system|The renewal job)) ((retried|double-posted|failed to void|mis-applied)) the ((authorisation|charge|renewal|discount)) ((on {date}|at {time} on {date}|during the {date} incident)).",
                "((Invoice|Billing)) ((details|address|plan)) on the account ((were out of date|didn't match the card|were never updated)) ((since {month}|after the plan change|after migration)).",
                "((Customer|Account holder)) was on the ((legacy|annual|monthly)) {plan} plan and the ((price change|proration|tax update)) on {date} ((wasn't applied|was applied twice|missed them)).",
                "((Duplicate|Extra|Unexpected)) ((charge|debit|payment)) of ${amount} ((traced to|came from|was caused by)) ((a retry at {time}|order #{ticket} being submitted twice|a stale saved card ending {last4})).",
                "((Discount|Promo|Coupon)) {code} ((expired|was excluded|didn't stack)) ((on {date}|for sale items|on the {plan} plan)), so full price was charged.",
                "((Bank|Card issuer|Payment provider)) ((held|flagged|declined)) the ((first|original|earlier)) attempt ((at {time}|on {date})), ((then|and later)) ((both settled|the retry also went through|we charged again)).",
                "((Annual|Monthly)) ((renewal|invoice)) ((ran|was generated)) ((a day early|before the downgrade|after cancellation)) because the ((change|request|downgrade)) ((was queued|hadn't synced|was saved on {date})).",
                "((Tax|VAT|Currency conversion)) ((was|got)) ((applied twice|calculated on the wrong country|rounded up)) for {city} ((on invoice {ref}|this cycle|since {month}))."],
    "shipping": ["((The courier|Our carrier|The depot)) ((mis-scanned|misrouted|held|lost)) the parcel ((at the {city} hub|on {date}|between depots)).",
                 "((Warehouse|Fulfilment)) ((missed|delayed|split)) the ((dispatch|pick|shipment)) ((on {date}|because of a stock shortage|after a system outage)).",
                "((Address|Postcode|Flat number)) on order #{ticket} ((was incomplete|had a typo|failed validation)), so the ((courier|driver)) ((returned it to depot|couldn't deliver|left a card)).",
                "((Label|Address|Routing)) ((printed|was set|defaulted)) to ((an old address|the billing address|the wrong depot)) ((on {date}|for order #{ticket}|after checkout)).",
                "((Severe weather|A vehicle breakdown|Staff shortages|A depot backlog)) in {city} ((delayed|held up|stalled)) ((all parcels|this route|deliveries)) ((from {date}|for {n} days|this week)).",
                "((Parcel|Package)) ((was|got)) ((sent to the {city} depot by mistake|stuck in customs|returned to sender)) ((on {date}|after {n} attempts|because nobody signed)).",
                "((Driver|Courier)) ((scanned|marked)) it delivered ((at {time}|on {date})) ((at the wrong door|from the van|before arriving)), ((GPS shows|photo shows|logs show)) ((another street|the depot|nothing)).",
                "((Item|Stock)) ((was out of stock|was mis-picked|failed quality check)) at the ((warehouse|fulfilment centre|{city} site)) ((on {date}|so the order sat|until {weekday}))."],
    "returns": ["((Return|Parcel)) ((arrived|was received)) on {date} but ((wasn't scanned|sat in quarantine|was logged to the wrong order #{ticket})).",
                "((Refund|Return)) ((stalled|failed|bounced)) because the ((original card|card ending {last4}|payment method)) had ((expired|been replaced|been cancelled)).",
                "((Return|Parcel)) was ((logged|received|scanned)) at the {city} ((warehouse|returns centre|hub)) on {date} ((but not matched to the order|under the wrong customer|without the RMA)).",
                "((Refund|Credit)) ((was|had been)) ((issued to store credit|sent to an old card|held for inspection)) ((by mistake|automatically|on {date})) ((instead of the original payment|per the default rule|for {n} days)).",
                "((Return|Exchange)) ((label|request|RMA)) {ref} ((expired|was never used|was cancelled)) ((on {date}|before drop-off|after 14 days))."],
    "technical": ["((Release|Build|Deploy)) {version} ((introduced|caused|exposed)) a ((regression|bug|timeout)) ((in the {plan} tier|for {device} users|on accounts created before {month})).",
                  "((A config change|An expired token|A rate limit|A failed migration)) ((on {date}|at {time}|last {weekday})) ((broke|disabled|throttled)) the ((sync|export|login|webhook)).",
                "((Logs|Traces)) from {date} {time} show ((repeated 500s|timeouts|a null response)) from the ((auth|export|billing|sync)) service ((for this account|for {n}% of {plan} users|on {device})).",
                "((Rate limiting|A cache bug|A database lock|A third-party outage)) ((between|from)) {time} ((and|to)) ((the evening|midnight|the next morning)) on {date} ((affected|hit|slowed)) ((this workspace|{n}% of requests|the {plan} tier)).",
                "((Customer's|Their)) ((browser|app|device)) ((was on|was running|had)) ((an old version|{version}|a blocked cookie setting)) ((and|so)) ((the session kept dropping|uploads failed|pages cached stale data)).",
                "((Our|The)) ((status page|monitoring|alerting)) ((missed|didn't catch|under-reported)) ((a partial outage|elevated errors|slow queries)) ((from {time} on {date}|in the {city} region|for {plan} accounts))."],
    "account": ["((Account|Login)) ((was locked|was flagged|was suspended)) ((after {n} failed attempts|by the fraud rules|on {date})).",
                "((Email|Phone|Two-factor)) ((details|settings|device)) ((were stale|didn't match|had changed)) ((since {month}|after a phone upgrade|after migration)).",
                "((Customer|User)) ((changed phones|switched email providers|left {company})) ((in {month}|recently|on {date})) and ((lost access|never updated the account|missed the verification email)).",
                "((Too many|Repeated|Multiple)) ((reset requests|login attempts|code requests)) ((from|in)) {city} ((triggered|tripped)) ((the security lock|rate limiting|a fraud hold)) ((at {time}|on {date})).",
                "((Customer|User)) was ((using|trying)) ((an old password|the wrong email|a personal address)) ((from before {month}|instead of {company}'s|on {device})).",
                "((Account|Profile)) ((merge|migration|update)) on {date} ((left|created|moved)) ((a duplicate login|two profiles|the orders on the old account))."],
    "product": ["Not a defect; ((feature|request|behaviour)) is ((working as designed|on the roadmap|not supported yet)) ((as of {version}|for the {plan} plan|for now))."],
}

_FAMILY_ACTIONS = {
    "billing": ["((Refunded|Reversed|Credited back|Voided)) ((the duplicate charge|the second payment|the overcharge|the renewal charge|the difference)) ((of ${amount}|)) ((and emailed the reference|; reference sent to the customer|, should clear in 3-5 working days|, confirmed in the payment dashboard|, customer notified)).",
                "((Updated|Corrected|Fixed)) the ((billing address|card details|VAT number|company name|plan)) on the account and ((reissued the invoice|re-ran the payment|confirmed with the customer|sent a new receipt)).",
                "((Applied|Added)) a ((goodwill|service|one-off)) credit of ${amount} ((to the account|to the next invoice|for the trouble)).",
                "((Raised|Logged)) ((a billing correction|an adjustment|a credit note)) ((CN-{ticket}|ref {ref})) for ${amount} ((and emailed {fname}|; posts to card ending {last4}|, visible on the next statement)).",
                "((Waived|Cancelled|Refunded)) ((the late fee|this month's charge|the renewal)) [[of ${amount} ]]and ((moved the account to monthly billing|set the plan to cancel at term end|updated the card on file to {last4})).",
                "((Corrected|Reissued|Re-raised)) invoice {ref} ((with the right VAT|in the right currency|with {company} details)) ((and emailed it to {email}|; old one voided|, PDF attached to the ticket)).",
                "((Moved|Switched|Changed)) the customer ((to monthly billing|to the {plan} plan|off auto-renew)) ((from {date}|effective today|at their request)) ((and confirmed by email|; prorated credit ${amount}|, no further charges)).",
                "((Contacted|Called|Emailed)) the ((payment provider|card issuer|bank)) ((about|re:|regarding)) ((transaction {ref}|the ${amount} charge|card ending {last4})) ((and they released the hold|; reversal pending|, released in 2 days))."],
    "shipping": ["((Reshipped|Sent out|Dispatched)) a ((replacement|new unit|second parcel)) ((by express|next day|with tracking|signed for)) ((at no charge|free of charge|and refunded the postage)).",
                 "((Opened|Raised|Filed)) a ((claim|trace|investigation)) with the ((courier|carrier|depot)) ((and refunded in full|and sent a replacement|; customer updated)).",
                 "((Chased|Called|Escalated with)) the ((warehouse|courier|depot)); new ((dispatch|delivery)) date ((is {weekday}|confirmed for {weekday}|within {n} days)).",
                "((Updated|Corrected)) the delivery details and ((rebooked|requested)) ((redelivery|a new slot)) for {weekday} ((before {time}|in the morning|with a safe-place note)).",
                "((Booked|Sent)) a ((free|priority|tracked)) ((replacement|resend|re-delivery)) ((ref {ref}|via express|for {weekday})) and ((cancelled the original|told the customer to refuse the late parcel|kept the original claim open)).",
                "((Refunded|Credited|Returned)) the ((shipping fee|delivery charge|express upgrade)) [[of ${amount} ]]((as goodwill|for the delay|and apologised)).",
                "((Asked|Instructed|Told)) the ((courier|depot|driver)) to ((hold it for collection|redeliver on {weekday}|leave it with a neighbour)) ((ref {ref}|per the customer|and texted {phone})).",
                "((Cancelled|Stopped|Recalled)) the ((original|late|lost)) shipment and ((issued a full refund|sent a replacement|offered store credit)) ((of ${amount}|to card {last4}|same day))."],
    "returns": ["((Sent|Emailed|Issued)) a ((prepaid|free|QR-code)) return label ((by email|to the customer|for drop-off)); refund ((on receipt|once scanned|within {n} days of arrival)).",
                "((Processed|Pushed through|Approved)) the refund of ${amount} ((manually|early|as an exception)) ((and sent confirmation|; customer notified|to the original card)).",
                "((Arranged|Booked)) a ((courier collection|home pickup|exchange)) for {weekday}.",
                "((Matched|Linked|Assigned)) the return to order #{order} ((manually|in the system|by hand)) and ((released|issued|pushed)) the refund ((of ${amount}|to card {last4}|same day)).",
                "((Converted|Switched|Moved)) the ((store credit|voucher|refund)) ((to a card refund|back to the original card|to PayPal)) [[of ${amount} ]]((at the customer's request|and confirmed|; ref {ref})).",
                "((Extended|Reopened|Reissued)) the return ((window|label|RMA)) ((to {date}|for 14 days|as {ref})) and ((emailed|sent|texted)) ((the new label|instructions|a QR code))."],
    "technical": ["((Pushed|Shipped|Deployed)) a ((fix|patch|hotfix)) in ((version {version}|release {version}|this morning's deploy)); ((confirmed with the customer|customer verified|monitoring)).",
                  "((Cleared|Reset|Rebuilt)) the ((cache|session|sync job|index)) for the account ((and the issue stopped|; working again|, confirmed fixed)).",
                  "((Shared|Sent)) a ((workaround|temporary fix|step-by-step guide)) ((while engineering fixes the root cause|and linked the bug|; permanent fix due in {version})).",
                "((Rolled back|Reverted|Disabled)) the ((change|flag|config)) from {date}[[ at {time}]] ((and confirmed recovery|; error rate back to normal|, customer can log in again)).",
                "((Raised|Opened|Filed)) ((incident|bug|ticket)) {ref} ((with engineering|for the platform team|as a P2)); ((workaround shared|customer kept updated|fix expected in {version})).",
                "((Asked|Helped|Walked)) the customer ((to update|through updating|to reinstall)) ((to {version}|the app|their browser)) ((and it worked|; confirmed fixed at {time}|, problem gone)).",
                "((Replayed|Re-sent|Backfilled)) ((the missed events|failed exports|the sync)) ((from {date}|for the last {n} days|since {time})) ((and confirmed counts match|; {n}0 records restored|, customer verified))."],
    "account": ["((Verified|Confirmed)) the customer's identity ((by email|with ID|via security questions)) and ((reset|unlocked|updated)) the ((account|password|two-factor|email address)).",
                "((Merged|Closed|Updated)) the ((duplicate account|old account|account details)) ((and kept the order history|; customer confirmed|as requested)).",
                "((Removed|Unsubscribed)) the customer from ((all marketing|the newsletter|promotional)) emails; ((order updates still on|confirmed by email)).",
                "((Sent|Issued)) a ((reset link|verification code|new invite)) to ((the backup email|{fname}'s new address|the verified phone)) ((at {time}|on {date})) ((and confirmed access|; customer logged in|, all good)).",
                "((Lifted|Cleared|Removed)) the ((lock|hold|flag)) ((after verifying|once we confirmed|having checked)) ((ID|the card ending {last4}|the billing postcode)) ((at {time}|on {date}|on the call)).",
                "((Walked|Talked)) the customer through ((resetting|recovering|updating)) ((the password|two-factor|their email)) ((on the phone|over chat|by email)) ((at {time}|on {date}|in about {mins} minutes)).",
                "((Moved|Transferred|Linked)) ((the orders|order history|the subscription)) ((to|onto)) ((the main account|{email}|the correct profile)) ((and closed the duplicate|; customer confirmed|as asked))."],
    "product": ["((Logged|Recorded|Added)) the ((request|suggestion|feedback)) ((with the product team|on the roadmap board|to the feature tracker)) ((and thanked the customer|; shared the public roadmap|, {n} similar votes))."],
}

_RESOLUTION_REFS = [
    "Re: {item}, order #{order}.", "((Item|Product)): {item}.", "((Customer|Cx|Account)): {fname} {lname}, {city}.",
    "((Company|Org)): {company}.", "((Contact|Callback)) number {phone}.", "Email on file {email}.",
    "{item} ((x1|x2|qty 1|qty 2)), ${amount}.", "Order #{order} ({date}, {city}).",
]
_RESOLUTION_NOTES_EXTRA = [
    "Card ending {last4}.", "Ref {ref}.", "((Logged|Updated)) {date} {time}.", "Related ticket #{ticket}.",
    "((Refund|Credit|Return)) ref {ref} ((sent|issued|shared)) to the customer.", "Customer called at {time} on {date}.",
    "Customer is on the {plan} plan.", "((Handled|Resolved|Closed)) in {mins} minutes.", "Order #{order}.",
    "Amount involved: ${amount}.", "((Reported|Seen)) on {device}.", "First reported {when}.",
    "((Second|Third|Fourth)) contact ((about this|on this issue|this month)) ((- see #{ticket}|since {date}|)).", "Customer was ((polite and patient|understanding|very calm|frustrated but fair)).",
    "Customer was frustrated; offered a {n}0% voucher.", "No further action ((needed|required|on our side))((.| unless the customer replies.))",
    "Checked for similar tickets: {n} others this week.", "((Added|Left)) ((an internal|a)) note ((on|to)) the account ((for the next agent|re: {plan} plan|on {date})).",
    "Customer based in {city}.", "((Linked|Merged)) with ticket #{order}.", "((Refund|Credit)) reference sent to {fname}.",
    "((Also|Additionally)) ((updated|corrected)) the ((billing address|phone number|marketing preferences)).",
    "((Raised|Logged)) a bug ((for|with)) the ((app|web|payments)) team.",
]
_FOLLOWUPS = ["", "", "", "Customer confirmed ((it's|the issue is|everything is)) ((resolved|working|sorted)) ((on {date}|at {time}|by email|)).",
              "Customer ((thanked us|was happy|said thanks)); marking solved.",
              "Will monitor ((for a week|for a few days|for 48 hours|until {date})).", "Macro ((sent|applied)): ((refund-confirmation|shipping-update|password-reset|apology-voucher)).",
              "((Linked|Attached)) ((to|the)) known-issue article ((KB-{n}{n}0|#{ticket}|)).", "Tagged ((for the weekly review|#{plan}|vip|repeat-contact|billing-error)).",
              "Closing; customer can reply to reopen.", "((Sent|Queued)) a ((follow-up|satisfaction|CSAT)) survey.",
              "No reply from customer after ((48 hours|two days|a week)); closing.", "((Set|Scheduled)) a check-in for {weekday} {time}.",
              "((Closing|Resolved)) - {fname}", "- {fname}", "({initials})", "-- {initials}, {date}", "Ref {ref}.",
              "((Next|Follow-up)) step: ((check back|confirm the refund landed|chase the courier|verify the fix)) on {date}.",
              "((Escalation|Handover)) note left for ((the night shift|tier 2|{fname}|the {city} team)).",
              "((CSAT|Survey|Feedback request)) ((queued|sent|scheduled)) for ((tomorrow|{date}|after closure)).",
              "((Time spent|Handle time|Work time)): {mins} min.", "((Status|State)) -> ((solved|pending customer|closed)) at {time}.",
              "((Reopened|Re-opened)) ((once|twice)) before; ((now stable|watching|should hold))."]


# Issues the family-level symptom would misdescribe (a feature request is not
# "charged twice"), so they always use their own.
_SPECIFIC_ONLY = {"invoice_request", "change_address", "merge_accounts", "delete_account",
                  "unsubscribe", "change_email", "dark_mode", "bulk_edit", "pdf_export",
                  "product_question", "price_dispute", "wrong_item", "damaged"}


def render_ticket_descriptions(rng: np.random.Generator, frame: TicketFrame) -> np.ndarray:
    size = len(frame.issue)
    out = np.empty(size, dtype=object)
    for i in range(size):
        iss, sl, u = frame.issue[i], frame.slots[i], frame.urgency[i]
        parts = []
        greeting = str(_pick(rng, _GREETINGS)) if rng.random() < 0.3 else ""
        if rng.random() < 0.65 and iss.family in _FAMILY_SYMPTOMS and iss.key not in _SPECIFIC_ONLY:
            sym = _fill(str(_pick(rng, _FAMILY_SYMPTOMS[iss.family])), rng, sl)
        else:
            sym = _fill(str(_pick(rng, iss.symptoms)), rng, sl)
        lead = _fill(str(_pick(rng, _LEADS)), rng, sl)
        if lead and not lead.endswith(". ") and not lead.endswith(": "):
            sym = sym[0].lower() + sym[1:] if not sym.startswith("I ") and not sym.startswith("I'") else sym
        parts.append(lead + sym)
        if rng.random() < 0.35:
            parts.append(_fill(str(_pick(rng, iss.details)), rng, sl))
        if iss.family in _FAMILY_DETAILS:
            fd = _FAMILY_DETAILS[iss.family]
            picks = _distinct(rng, fd, 2 if rng.random() < 0.4 else 1) if rng.random() < 0.8 else []
            parts.extend(_fill(str(x), rng, sl) for x in picks)
        if rng.random() < 0.4:
            pool = _CONTEXT_LINES.get(iss.family, []) + _CONTEXT_LINES["any"]
            parts.append(_fill(str(_pick(rng, pool)), rng, sl))
        if rng.random() < 0.35:
            parts.append(_fill(str(_pick(rng, _ASKS.get(iss.family, _ASKS["any"]))), rng, sl))
        if iss.family in ("technical", "account") and rng.random() < 0.5:
            parts.append(_fill(str(_pick(rng, _TRIED)), rng, sl))
        impact = _fill(str(_pick(rng, _IMPACT[u])), rng, sl) if rng.random() < (0.85 if u >= 2 else 0.5) else ""
        if impact:
            parts.append(impact)
        text = " ".join(parts)
        if greeting:
            text = f"{greeting}\n\n{text}"
        if rng.random() < 0.15:
            text = _fill(str(_pick(rng, _INTROS)), rng, sl) + " " + text
        if greeting:
            pass
        if rng.random() < 0.35:
            so = _pick(rng, _SIGNOFFS)
            sig = (f"\n{sl['fname']} {sl['lname']}" if rng.random() < 0.4 else f"\n{sl['fname']}") if rng.random() < 0.7 else ""
            text += f"\n\n{so}{sig}"
        out[i] = text
    from misata.paraphrase import vary
    return np.array(vary(list(out), rng, "casual"), dtype=object)


def render_ticket_resolutions(rng: np.random.Generator, frame: TicketFrame) -> np.ndarray:
    """What was wrong and what was done; None while the ticket is still open."""
    size = len(frame.issue)
    out = np.empty(size, dtype=object)
    for i in range(size):
        if frame.open_[i]:
            out[i] = None
            continue
        iss, sl = frame.issue[i], frame.slots[i]
        # Causes and fixes are written in pairs: the fix answers the cause.
        k = int(rng.integers(len(iss.fixes)))
        fix = _fill(iss.fixes[k], rng, sl)
        cause = _fill(iss.causes[k % len(iss.causes)], rng, sl)
        if rng.random() < 0.85 and iss.family in _FAMILY_ACTIONS:
            # The family-level cause and action go together, as the issue's own pair does.
            fix = _fill(_pick(rng, _FAMILY_ACTIONS[iss.family]), rng, sl)
            cause = _fill(_pick(rng, _FAMILY_CAUSES[iss.family]), rng, sl)
        r = rng.random()
        if r < 0.45:
            text = f"{cause} {fix}"
        elif r < 0.6:
            text = f"Root cause: {cause[0].lower() + cause[1:]}".rstrip(".") + f". {fix}"
        else:
            text = fix
        if rng.random() < 0.55:
            ref_line = _fill(str(_pick(rng, _RESOLUTION_REFS)), rng, sl)
            text = f"{ref_line} {text}" if rng.random() < 0.5 else f"{text} {ref_line}"
        for prob in (0.75, 0.4):
            if rng.random() < prob:
                text = f"{text} {_fill(str(_pick(rng, _RESOLUTION_NOTES_EXTRA)), rng, sl)}"
        follow = _fill(str(_pick(rng, _FOLLOWUPS)), rng, sl)
        pre = _fill(str(_pick(rng, _PREFACES)), rng, sl) if rng.random() < 0.3 else ""
        if pre and r >= 0.45:
            text = text[0].lower() + text[1:] if pre.endswith(": ") else text
        out[i] = f"{pre}{text} {follow}".strip()
    from misata.paraphrase import vary
    return np.array(vary(list(out), rng, "business"), dtype=object)


# ── short labels and profiles ────────────────────────────────────────────────

_JOB_FUNCTIONS = [
    "Software Engineer", "Product Manager", "Data Analyst", "Account Executive",
    "Marketing Manager", "Operations Manager", "Customer Success Manager", "Accountant",
    "UX Designer", "Project Manager", "Sales Representative", "Business Analyst",
    "HR Business Partner", "Registered Nurse", "Teacher", "Financial Analyst",
    "Data Scientist", "DevOps Engineer", "Graphic Designer", "Content Strategist",
    "Recruiter", "Office Manager", "Mechanical Engineer", "Civil Engineer",
    "Pharmacist", "Paralegal", "Solicitor", "Consultant", "Store Manager",
    "Logistics Coordinator", "Supply Chain Analyst", "Electrician", "Architect",
    "Copywriter", "Customer Service Representative", "Executive Assistant",
    "Research Scientist", "Security Analyst", "QA Engineer", "Social Media Manager",
    "Procurement Specialist", "Payroll Specialist", "Physiotherapist", "Chef",
    "Event Coordinator", "Real Estate Agent", "Insurance Underwriter", "Lab Technician",
    "Frontend Developer", "Backend Developer", "Solutions Architect", "Brand Manager",
    "Technical Writer", "Site Reliability Engineer", "Bookkeeper", "Teaching Assistant",
]
_SENIORITY = [("", 0.58), ("Senior ", 0.2), ("Junior ", 0.06), ("Lead ", 0.06),
              ("Principal ", 0.03), ("Associate ", 0.05), ("Head of ", 0.02)]
_HEAD_OF_OK = {"Marketing", "Operations", "Product", "Sales", "Design", "Engineering"}


def job_titles(rng: np.random.Generator, size: int, key: str = "job_title") -> np.ndarray:
    """Job titles with a realistic skew and seniority mix (several hundred
    distinct titles, a few common ones), not 22 titles in equal shares."""
    base = zipf_choice(rng, _JOB_FUNCTIONS, size, s=0.9, q=3, key=key)
    prefixes, w = zip(*_SENIORITY)
    pre = rng.choice(len(prefixes), size=size, p=np.array(w) / sum(w))
    out = np.empty(size, dtype=object)
    for i in range(size):
        p = prefixes[pre[i]]
        b = base[i]
        if p == "Head of ":
            fn = b.split()[0]
            out[i] = f"Head of {fn}" if fn in _HEAD_OF_OK else b
        elif p and b.split()[0] in ("Registered", "Executive", "Teaching"):
            out[i] = b
        else:
            out[i] = f"{p}{b}"
    return out


_INTERESTS = ["trail running", "sourdough", "film photography", "board games", "cycling",
              "jazz", "climbing", "gardening", "chess", "travel", "podcasts", "yoga",
              "cooking", "reading sci-fi", "football", "open source", "wild swimming",
              "pottery", "birdwatching", "live music", "baking", "hiking", "coffee",
              "vintage cars", "running", "tennis", "DIY", "knitting", "surfing", "writing"]
_FIELDS = ["product", "design", "data", "marketing", "operations", "finance", "healthcare",
           "education", "retail", "engineering", "logistics", "sales", "consulting",
           "customer success", "hospitality", "research"]


def bios(rng: np.random.Generator, size: int, *, jobs: Optional[Sequence] = None,
         cities: Optional[Sequence] = None, companies: Optional[Sequence] = None) -> np.ndarray:
    """Short profile bios in several structures, using the row's own job,
    city and employer when the table has them."""
    jobs = _clean_values(jobs, size)
    cities = _clean_values(cities, size)
    companies = _clean_values(companies, size)
    out = np.empty(size, dtype=object)
    for i in range(size):
        job = (jobs[i] if jobs and jobs[i] else None)
        city = (cities[i] if cities and cities[i] else None)
        comp = (companies[i] if companies and companies[i] else None)
        a, b = _distinct(rng, _INTERESTS, 2)
        field = str(_pick(rng, _FIELDS))
        opts = [(2, f"{a.capitalize()} and {b}.")]
        if job:
            opts += [(3, f"{job}{f' at {comp}' if comp else ''}. Into {a} and {b}."),
                     (2, f"{job} | {a} | {b}"),
                     (2, f"{job}{f' based in {city}' if city else ''}."),
                     (1, f"{job} by day, {a} by night.")]
        if city:
            opts += [(2, f"{city}-based. {a.capitalize()}, {b} and good coffee."),
                     (1, f"Living in {city}. Big on {a}.")]
        opts += [(2, f"{int(rng.integers(2, 25))} years in {field}. Weekends are for {a}."),
                 (1, f"I work in {field} and spend my free time on {a}."),
                 (1, f"Curious about {field}, {a} and {b}."),
                 (1, f"{field.capitalize()} person. {a.capitalize()} fan.")]
        text = _weighted(rng, opts)
        if rng.random() < 0.08:
            text += " " + str(_pick(rng, ["🌍", "☕", "🚴", "📚", "🎧", "🌱", "📷"]))
        out[i] = text
    return out


# Street address formats by country: the street line only; city and postcode
# live in their own columns when the table has them.
_STREETS_EN = ["Main", "High", "Church", "Station", "Park", "Mill", "Victoria", "King",
               "Queen", "Oak", "Maple", "Cedar", "Elm", "Pine", "Lake", "Hill", "River",
               "Spring", "Market", "Bridge", "North", "South", "Washington", "Lincoln",
               "Franklin", "Highland", "Sunset", "Grove", "Meadow", "Chestnut"]
_SUFFIX_US = ["St", "Ave", "Rd", "Blvd", "Dr", "Ln", "Way", "Ct", "Pl"]
_SUFFIX_UK = ["Street", "Road", "Lane", "Avenue", "Close", "Gardens", "Way", "Crescent", "Terrace"]
_STREETS_DE = ["Haupt", "Bahnhof", "Schul", "Garten", "Berg", "Wald", "Linden", "Kirch",
               "Dorf", "Ring", "Wiesen", "Birken"]
_SUFFIX_DE = ["straße", "weg", "allee", "gasse", "platz"]
_STREETS_FR = ["de la République", "Victor Hugo", "de la Paix", "Jean Jaurès", "du Moulin",
               "des Écoles", "de la Gare", "Pasteur", "du Château", "des Lilas"]
_TYPE_FR = ["rue", "avenue", "boulevard", "place", "impasse", "chemin"]
_STREETS_NL = ["Kerk", "Dorps", "Molen", "School", "Linden", "Prins Hendrik", "Wilhelmina",
               "Beatrix", "Juliana", "Stations"]
_SUFFIX_NL = ["straat", "weg", "laan", "plein", "gracht"]
_STREETS_BR = ["das Flores", "Sete de Setembro", "São João", "XV de Novembro", "da Paz",
               "Santos Dumont", "Tiradentes", "Brasil", "Getúlio Vargas"]
_TYPE_BR = ["Rua", "Avenida", "Travessa", "Alameda"]
_STREETS_IN = ["MG Road", "Station Road", "Gandhi Nagar", "Nehru Street", "Park Street",
               "Civil Lines", "Laxmi Nagar", "Sector 14", "Brigade Road", "Anna Salai"]
_JP_WARDS = ["Chuo", "Minato", "Shibuya", "Shinjuku", "Kita", "Naka", "Higashi", "Nishi"]


def street_lines(rng: np.random.Generator, size: int,
                 countries: Optional[Sequence] = None) -> np.ndarray:
    """Street lines in each row's country's own format."""
    cs = _clean_values(countries, size) or ["United States"] * size
    out = np.empty(size, dtype=object)
    for i in range(size):
        c = cs[i].lower()
        num = 1 + int(rng.exponential(1800 if c in ("united states", "usa", "us") else 60))
        if c in ("united kingdom", "uk", "great britain", "england", "australia", "ireland",
                 "new zealand"):
            line = f"{num} {_pick(rng, _STREETS_EN)} {_pick(rng, _SUFFIX_UK)}"
            if rng.random() < 0.15:
                line = f"Flat {int(rng.integers(1, 30))}, {line}"
        elif c in ("germany", "deutschland", "austria", "switzerland"):
            line = f"{_pick(rng, _STREETS_DE)}{_pick(rng, _SUFFIX_DE)} {num}"
        elif c in ("france", "belgium"):
            line = f"{num} {_pick(rng, _TYPE_FR)} {_pick(rng, _STREETS_FR)}"
        elif c in ("netherlands", "holland"):
            line = f"{_pick(rng, _STREETS_NL)}{_pick(rng, _SUFFIX_NL)} {num}"
        elif c in ("brazil", "brasil", "portugal"):
            line = f"{_pick(rng, _TYPE_BR)} {_pick(rng, _STREETS_BR)}, {num}"
        elif c == "india":
            line = f"{num}, {_pick(rng, _STREETS_IN)}"
        elif c == "japan":
            line = (f"{int(rng.integers(1, 9))}-{int(rng.integers(1, 30))}-"
                    f"{int(rng.integers(1, 20))} {_pick(rng, _JP_WARDS)}")
        else:
            line = f"{num} {_pick(rng, _STREETS_EN)} {_pick(rng, _SUFFIX_US)}"
            if rng.random() < 0.25:
                line += str(rng.choice([f", Apt {int(rng.integers(1, 40))}{rng.choice(list('ABCDEF'))}",
                                        f", Unit {int(rng.integers(1, 300))}",
                                        f", Suite {int(rng.integers(1, 9)) * 100}"]))
        out[i] = line
    return out


def brands(rng: np.random.Generator, size: int, families: Optional[Sequence] = None,
           key: str = "brand") -> np.ndarray:
    """Brand names, concentrated the way real catalogues are."""
    if families is None:
        pool = sorted({b for f in PRODUCT_FAMILIES.values() for b in f.brands})
        return zipf_choice(rng, pool, size, s=1.05, key=key)
    fam = np.array([f or "generic" for f in families], dtype=object)
    out = np.empty(size, dtype=object)
    for f in sorted(set(fam)):
        idx = np.flatnonzero(fam == f)
        out[idx] = zipf_choice(rng, PRODUCT_FAMILIES[f].brands, len(idx), s=1.1,
                               key=f"{key}|{f}")
    return out


def subject_from_name(name: str) -> str:
    """How a review refers to a product: the type, not the full listing title
    ("Northfold Relaxed Rain Jacket - Navy" is "rain jacket")."""
    return _noun_from_name(name)

# Noun-specific features for the large families, so most features in a
# description are written for that exact product type.
_NOUN_FEATURES = {
    "electronics": [
        "{n:30-60} hours of playback@Headphones|Earbuds|Speaker|Headset", "active noise cancelling@Headphones|Earbuds|Headset",
        "a fold-flat design@Headphones|Stand", "((IPX4|IPX5|IPX7)) water resistance@Speaker|Earbuds|Tracker|Smartwatch|Camera",
        "a party-pairing mode@Speaker", "{n:6-10} height settings@Laptop Stand", "hot-swappable switches@Keyboard",
        "per-key RGB lighting@Keyboard|Mouse", "a ((8,000|16,000|26,000)) DPI sensor@Mouse", "{n:5-8} programmable buttons@Mouse",
        "a ((27|32))-inch IPS panel@Monitor", "a ((120|144|165)) Hz refresh rate@Monitor", "USB-C with {n:65-96} W charging@Monitor|Hub",
        "1080p at 60 fps@Webcam", "a privacy shutter@Webcam", "auto light correction@Webcam|Ring Light",
        "a ((5,000|10,000|20,000|26,800)) mAh battery@Power Bank", "{n:2-3} USB-C ports@Power Bank|Hub|Charger", "pass-through charging@Power Bank",
        "a wireless charging case@Earbuds", "energy monitoring@Smart Plug", "scheduling from the app@Smart Plug|Bulb|Thermostat",
        "4K at ((30|60)) fps@Action Camera|Drone|Dash Cam", "electronic image stabilisation@Action Camera|Drone|Mirrorless",
        "a {n:10-13}-inch display@Tablet", "stylus support@Tablet|E-Ink", "{n:5-14} days of battery@Smartwatch|Tracker",
        "heart-rate and sleep tracking@Smartwatch|Tracker", "a glare-free {n:6-8}-inch screen@E-Reader", "adjustable warm light@E-Reader|Lamp|Bulb",
        "a parking mode@Dash Cam", "a G-sensor that saves incident clips@Dash Cam", "read speeds up to ((1,050|2,000)) MB/s@SSD",
        "a drop-tested aluminium shell@SSD", "Wi-Fi 6 with {n:4-8} streams@Router|Mesh", "parental controls in the app@Router|Mesh",
        "{n:6-10} ports in one@Hub", "Dolby Atmos@Soundbar", "a wireless subwoofer@Soundbar", "GaN fast charging@Charger",
        "learning schedules@Thermostat", "geofencing@Thermostat|Doorbell", "two-way talk@Doorbell|Security Camera",
        "colour night vision@Doorbell|Security Camera", "a cardioid capsule@Microphone", "a zero-latency headphone jack@Microphone",
        "8,192 pressure levels@Graphics Tablet", "((1,000|2,000|3,000)) ANSI lumens@Projector", "keystone correction@Projector",
        "local storage on a microSD card@Security Camera|Dash Cam", "a built-in voice assistant@Smart Speaker|Soundbar",
        "a belt-driven platter@Turntable", "Bluetooth out to your speakers@Turntable", "a {n:20-26} MP sensor@Mirrorless",
        "interchangeable lenses@Mirrorless", "{n:30-45} minutes of flight time@Drone", "return-to-home GPS@Drone",
        "{n:20-30} soundscapes@Noise Machine", "16 million colours@Bulb", "three colour temperatures@Ring Light|Lamp",
        "a phone holder@Ring Light", "a detachable boom mic@Headset", "Dolby Vision@Streaming Stick", "a voice remote@Streaming Stick",
        "MagSafe alignment@Wireless Charger", "thermal printing, no ink@Label Printer", "PM2.5 and CO2 sensing@Air Quality",
        "a {n:25-40} km range@Scooter", "a folding stem@Scooter"],
    "clothing": [
        "a packable hood@Rain Jacket|Puffer|Gilet", "taped seams and a ((10,000|15,000|20,000)) mm waterproof rating@Rain Jacket",
        "a button-down collar@Oxford Shirt|Linen Shirt", "a chest pocket@Shirt|Overshirt|Shacket", "a tapered leg@Chino|Joggers|Jeans",
        "a soft merino blend@Sweater|Cardigan|Turtleneck|Vest", "a high waistband@Leggings|Skirt|Trousers", "a hidden phone pocket@Leggings|Shorts|Joggers",
        "squat-proof fabric@Leggings", "a tie waist@Summer Dress|Wrap Dress|Shirt Dress", "adjustable straps@Dress|Tank",
        "a built-in brief@Running Shorts|Swim Shorts", "reflective trims@Running Shorts|Jacket|Joggers", "recycled down fill@Puffer|Gilet",
        "a two-way zip@Puffer|Hoodie|Jacket", "a screen-printed design@Graphic Tee", "a relaxed boxy fit@Tee|Shirt|Hoodie",
        "a mid rise@Jeans|Chino|Trousers", "((12|13|14)) oz denim@Jeans|Denim Jacket", "a side split@Midi Skirt|Dress",
        "a brushed-back fleece@Hoodie|Joggers|Sweatpants|Pullover", "a kangaroo pocket@Hoodie", "half-canvas construction@Blazer",
        "notch lapels@Blazer", "six utility pockets@Cargo Shorts|Utility Jacket", "fringed ends@Scarf", "a fold-over cuff@Beanie",
        "a pique knit@Polo", "horn-effect buttons@Cardigan|Coat|Blazer", "elasticated cuffs@Joggers|Sweatpants|Bomber",
        "a contrast collar@Rugby Shirt|Polo", "a storm flap@Trench Coat", "a removable belt@Trench Coat|Wool Coat",
        "diamond quilting@Quilted Gilet", "a slubby linen weave@Linen Shirt", "a pressed front crease@Wide-Leg Trousers",
        "a cable-knit front@Knitted Vest|Sweater", "box pleats@Pleated Skirt", "a roll neck@Turtleneck", "a mesh lining@Swim Shorts",
        "a ribbed hem and cuffs@Bomber|Sweater|Cardigan", "((8|11|14))-wale cord@Corduroy", "a matching top and bottom@Lounge Set",
        "a wool-cashmere blend@Wool Coat|Scarf|Beanie"],
    "home": [
        "a waffle weave@Throw Blanket|Towel|Bath Mat", "deep pockets for mattresses up to {n:30-40} cm@Sheet Set|Topper",
        "an adjustable loft@Pillow", "a cooling gel layer@Pillow|Topper", "{n:4-12} hours of mist@Diffuser",
        "a true HEPA filter@Purifier|Vacuum", "coverage up to {n:20-60} m²@Purifier", "{n:40-60} minutes of run time@Vacuum",
        "a dimmable warm bulb@Table Lamp", "((500|600|700)) gsm cotton@Towel", "hidden button closures@Duvet Cover|Cushion Cover",
        "a bevelled edge@Mirror", "rope handles@Storage Basket|Hamper", "a cotton wick@Candle", "{n:40-60} hours of burn time@Candle",
        "a thermal lining@Blackout Curtains|Draught Excluder", "eyelet tops@Curtains|Shower Curtain", "a low pile@Area Rug|Jute Rug",
        "a non-shed weave@Rug", "a mount for {n:4-7} prints@Photo Frame", "a lift-out liner@Laundry Hamper", "a coir surface@Doormat",
        "weighted hems@Shower Curtain|Curtains", "a silent sweep movement@Wall Clock", "hemstitched edges@Napkins",
        "a self-watering reservoir@Plant Pot|Planter", "a quick-dry finish@Bath Mat|Towel", "a quilted top@Bedspread",
        "a tufted top@Floor Cushion", "archival inks@Art Print", "a narrow neck for single stems@Bud Vase", "a feather insert@Throw Pillow",
        "{n:3-6} brass hooks@Coat Hooks", "a {n:150-300} ml bottle@Room Spray", "a weight of {n:4-10} kg@Weighted Blanket",
        "glass-bead fill@Weighted Blanket", "{n:5-10} cm of memory foam@Topper", "a macramé hanger@Hanging Planter"],
    "beauty": [
        "{n:10-20}% vitamin C@Vitamin C", "an airless pump@Serum|Moisturiser|Eye Cream|Foundation", "a gel-cream texture@Moisturiser|Eye Cream",
        "peptides@Night Cream|Eye Cream|Serum", "broad-spectrum SPF 50 with UVA {n:4-5} stars@Sunscreen", "no white cast@Sunscreen|Tinted",
        "micellar technology@Cleansing Water", "kaolin and bentonite clays@Clay Mask", "argan oil@Hair Oil|Hair Mask|Conditioner",
        "a sulphate-free formula@Shampoo|Conditioner", "a creamy satin finish@Lipstick", "{n:9-18} pans@Eyeshadow",
        "a curved brush@Mascara", "a smudge-proof formula@Mascara|Eyeliner|Brow", "a finely milled powder@Setting Powder|Bronzer",
        "a spoolie on the end@Brow Pencil", "a serum-soaked sheet@Sheet Masks", "a non-sticky feel@Body Lotion|Hand Cream",
        "a pocket-size tube@Hand Cream|Lip Balm", "caffeine@Eye Cream", "a gentle gel texture@Face Cleanser",
        "{n:2-7}% glycolic acid@Toner|Exfoliating", "SPF {n:15-30}@Lip Balm", "a soft-focus finish@Bronzer|Primer",
        "full coverage@Concealer|Foundation", "squalane and rosehip@Face Oil", "sugar crystals@Body Scrub",
        "an invisible spray@Dry Shampoo", "a chip-resistant finish@Nail Polish", "{n:24-48} shades@Foundation|Concealer",
        "a felt-tip nib@Eyeliner", "a melting balm texture@Cleansing Balm", "keratin@Hair Mask", "aluminium-free protection@Deodorant",
        "a blurring finish@Primer", "((0.3|0.5|1))% retinol@Retinol"],
    "sports": [
        "{n:4-6} resistance levels@Bands", "quick-change dials@Dumbbells", "a {n:4-8} mm cushioned surface@Yoga Mat",
        "alignment lines@Yoga Mat", "no-screw door fitting@Pull-Up Bar", "ball-bearing handles@Jump Rope|Skipping Rope",
        "a textured surface@Foam Roller|Balance Board", "MIPS protection@Helmet", "{n:12-20} vents@Helmet",
        "a {n:270-300} g frame@Tennis Racket", "a composite cover@Basketball|Football", "size {n:4-5}@Football",
        "anti-fog lenses@Swim Goggles|Ski Goggles", "a shoe compartment@Gym Bag", "a powder-coated grip@Kettlebell",
        "a {n:2-4} person capacity@Camping Tent", "a ((3,000|4,000|5,000)) mm hydrostatic head@Camping Tent",
        "a comfort rating of ((-5|-2|0|2|5))°C@Sleeping Bag", "a {n:30-50} L capacity@Backpack|Gym Bag", "a rain cover@Backpack",
        "flip-lock adjustment@Trekking Poles", "double-wall insulation@Water Bottle", "((400|800|1,200)) lumens@Bike Light|Head Torch",
        "a drawstring closure@Chalk Bag", "{n:5-12} L of storage@Running Vest|Hydration Pack", "a downturned toe@Climbing Shoes",
        "an inflatable {n:10-12} ft board@Paddle Board", "{n:8-32} magnetic resistance levels@Exercise Bike",
        "{n:10-16} oz padding@Boxing Gloves", "a ((1.5|2|3)) L bladder@Hydration Pack", "a red night mode@Head Torch",
        "{n:3-5} mm neoprene@Wetsuit", "{n:2-4} rackets and shuttles@Badminton", "adjustable tension@Grip Trainer",
        "removable weight pockets@Weighted Vest", "gel palms@Cycling Gloves"],
    "toys": [
        "((120|250|500)) bricks@Building Blocks", "a figure-of-eight track@Train", "embroidered eyes@Plush Bear",
        "a poster of the finished picture@Jigsaw", "{n:2-6} players@Board Game|Card Game", "{n:15-30} minutes of run time@Remote Control",
        "{n:3-5} rooms of furniture@Doll House", "{n:50-150} pieces@Art Kit|Craft Box", "{n:10-30} experiments@Science Kit",
        "chunky rings for small hands@Stacking Rings", "a {n:20-50} m line@Kite", "clicking hob knobs@Play Kitchen|Toy Kitchen",
        "{n:6-12} balls@Marble Run", "a light-up front wheel@Scooter", "{n:60-120} tiles@Magnetic Tiles",
        "{n:4-6} puppets@Puppet Theatre", "a kids' drum stool@Drum Set", "a folding frame@Pram", "{n:10-17} pieces@Tea Set",
        "{n:100-200} balls@Ball Pit", "{n:6-12} shapes@Shape Sorter", "an app with coding challenges@Robot Kit",
        "{n:8-12} dinosaurs@Dinosaur", "{n:25-37} keys@Musical Keyboard", "an adjustable seat@Balance Bike",
        "((300|500|1,000)) stickers@Sticker Book", "a working lift and ramp@Garage", "a pop-up frame@Play Tent",
        "{n:2-4} water levels@Water Table", "squirt-free sealed toys@Bath Toys"],
    "kitchen": [
        "a pre-seasoned surface@Skillet|Dutch Oven|Wok", "a helper handle@Skillet|Dutch Oven", "{n:5-15} knives and a block@Knife Set",
        "full-tang German steel@Knife", "induction-ready bases@Cookware|Skillet|Wok|Dutch", "juice grooves@Cutting Board|Chopping",
        "a stainless double filter@French Press", "a gooseneck spout@Kettle", "temperature hold@Kettle",
        "{n:12-24} pieces@Dinnerware", "airtight snap lids@Containers", "a non-stick silicone surface@Baking Mat",
        "a tare function@Scale", "a {n:4-6} L bowl@Mixer|Mixing", "((1,000|1,200|1,500)) W of power@Blender|Air Fryer",
        "a {n:4-6} L basket@Air Fryer", "{n:6-7} browning levels@Toaster", "{n:15-40} grind settings@Grinder",
        "{n:12-20} jars@Spice Rack", "a {n:4-6} L capacity@Dutch Oven", "a leak-proof lid@Travel Mug|Water Bottle",
        "a one-hand pump@Salad Spinner", "{n:3-5} colour-coded boards@Chopping Board Set", "{n:6-9} thickness settings@Pasta",
        "a cleaning tool@Garlic Press", "{n:4-6} nesting cups@Measuring", "cordierite stone@Pizza Stone",
        "hot and cold froth@Frother", "a built-in strainer@Shaker", "a bamboo lid@Bread Bin", "{n:6-10} tools@Utensil Set",
        "a carbon-steel bowl@Wok", "a fine-mesh basket@Infuser", "silicone grips@Oven Gloves", "a tapered French design@Rolling Pin",
        "{n:3-5} blades@Spiraliser"],
}
for _k, _feat in _NOUN_FEATURES.items():
    _f = PRODUCT_FAMILIES[_k]
    PRODUCT_FAMILIES[_k] = replace(_f, features=list(_f.features) + _feat)

_MORE_USES = {
    "electronics": ["video calls", "the home office", "late-night gaming", "the daily commute", "travel", "streaming films",
                    "the smart home", "content creation", "a dorm room", "the bedside table", "road trips", "podcast recording"],
    "clothing": ["the school run", "weekends away", "the office", "summer evenings", "long walks", "travel days",
                 "date night", "the gym", "festivals", "cold mornings", "layering", "lazy Sundays"],
    "home": ["small flats", "the guest room", "slow Sunday mornings", "a reading nook", "rented homes", "the nursery",
             "the hallway", "family movie nights", "the bathroom", "winter evenings", "the home office", "first homes"],
    "beauty": ["sensitive skin", "oily skin", "combination skin", "a night routine", "a gym bag", "travel",
               "a five-minute routine", "winter skin", "mature skin", "after the sun", "special occasions", "long days"],
    "sports": ["home workouts", "marathon training", "weekend hikes", "the climbing wall", "cold-weather runs", "yoga classes",
               "park sessions", "five-a-side", "wild swimming", "commuting by bike", "camping trips", "recovery days"],
    "toys": ["toddlers", "rainy days", "long car journeys", "the garden", "bath time", "family game night",
             "curious minds", "party bags", "screen-free afternoons", "grandparents' house", "the playroom", "first birthdays"],
    "kitchen": ["weeknight dinners", "batch cooking", "Sunday roasts", "small kitchens", "baking days", "dinner parties",
                "lunch prep", "camping", "the morning coffee", "students", "family meals", "slow cooking"],
}
for _k, _uses in _MORE_USES.items():
    _f = PRODUCT_FAMILIES[_k]
    PRODUCT_FAMILIES[_k] = replace(_f, uses=list(_f.uses) + _uses)
