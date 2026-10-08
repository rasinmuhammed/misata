"""
Rich vocabulary seed pools for realistic string generation.

These pools are the foundation of Misata's text realism layer.  They are:
  - Large enough that repetition is not obvious at typical dataset sizes
  - Diverse across gender, ethnicity, and geography
  - Organised by domain so a SaaS schema gets SaaS company names, not retail ones
  - Structured for conditional sampling (e.g. category → products)

How values were chosen
----------------------
Pools are assembled from:
  1. Public-domain datasets on Kaggle (CC0 / US-Gov-Works licensed)
  2. US Census Bureau name frequency tables (public domain)
  3. Manual curation for domain authenticity and diversity

Conditional pools
-----------------
Some pools are dicts keyed by a parent category so the simulator can do:
    product_name = CONDITIONAL["product_by_category"][row["category"]]

This eliminates the main source of "obviously synthetic" text: a product
named "Electronics Product 1" appearing in a clothing row.
"""

from __future__ import annotations

from typing import Dict, List

# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------

FIRST_NAMES: List[str] = [
    # English / Western
    "James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph",
    "Thomas", "Charles", "Christopher", "Daniel", "Matthew", "Anthony", "Donald",
    "Mark", "Paul", "Steven", "Andrew", "Kenneth", "George", "Joshua", "Kevin",
    "Brian", "Edward", "Ronald", "Timothy", "Jason", "Jeffrey", "Ryan",
    "Mary", "Patricia", "Jennifer", "Linda", "Barbara", "Elizabeth", "Susan",
    "Jessica", "Sarah", "Karen", "Lisa", "Nancy", "Betty", "Margaret", "Sandra",
    "Ashley", "Dorothy", "Kimberly", "Emily", "Donna", "Michelle", "Carol",
    "Amanda", "Melissa", "Deborah", "Stephanie", "Rebecca", "Sharon", "Laura",
    # South Asian
    "Priya", "Arjun", "Ananya", "Rahul", "Kavya", "Vikram", "Deepa", "Rohan",
    "Sneha", "Aditya", "Pooja", "Sanjay", "Neha", "Amit", "Divya", "Ravi",
    "Nisha", "Suresh", "Meera", "Kiran",
    # East Asian
    "Wei", "Fang", "Jing", "Ming", "Xiao", "Ying", "Chen", "Li", "Hui", "Yan",
    "Yuki", "Hana", "Kenji", "Sakura", "Takeshi", "Aiko", "Ryo", "Nao",
    "Ji-woo", "Min-jun", "Seo-yeon", "Ha-eun",
    # Hispanic / Latin
    "Sofia", "Valentina", "Camila", "Isabella", "Lucia", "Gabriela", "Mariana",
    "Santiago", "Mateo", "Sebastian", "Diego", "Alejandro", "Andres", "Carlos",
    "Luis", "Miguel", "Pablo", "Ricardo",
    # African / African-American
    "Aisha", "Fatima", "Amara", "Zara", "Imani", "Nia", "Simone", "Aaliyah",
    "Kwame", "Kofi", "Jabari", "Darius", "Malik", "Tyrone", "DeShawn",
    # Middle Eastern
    "Layla", "Yasmin", "Nour", "Hana", "Rania", "Omar", "Khalid", "Hassan",
    "Ibrahim", "Yousef", "Tariq", "Zaid",
    # Modern / Gen-Z
    "Liam", "Noah", "Oliver", "Elijah", "Ethan", "Mason", "Aiden", "Lucas",
    "Emma", "Olivia", "Ava", "Isabella", "Sophia", "Mia", "Charlotte", "Amelia",
]

LAST_NAMES: List[str] = [
    # Common US surnames
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Wilson", "Anderson", "Taylor", "Thomas", "Jackson", "White", "Harris",
    "Martin", "Thompson", "Young", "Robinson", "Lewis", "Walker", "Hall", "Allen",
    "Wright", "Scott", "Green", "Adams", "Baker", "Nelson", "Carter", "Mitchell",
    "Perez", "Roberts", "Turner", "Phillips", "Campbell", "Parker", "Evans",
    "Collins", "Edwards", "Stewart", "Morris", "Rogers", "Reed", "Cook", "Morgan",
    # South Asian
    "Patel", "Singh", "Kumar", "Sharma", "Gupta", "Shah", "Mehta", "Joshi",
    "Desai", "Chopra", "Nair", "Iyer", "Reddy", "Rao", "Verma",
    # East Asian
    "Chen", "Wang", "Li", "Zhang", "Liu", "Yang", "Huang", "Wu", "Zhao", "Sun",
    "Kim", "Lee", "Park", "Choi", "Jung",
    "Tanaka", "Suzuki", "Sato", "Yamamoto", "Kobayashi",
    # Hispanic
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Sanchez",
    "Ramirez", "Torres", "Flores", "Rivera", "Gomez", "Diaz", "Reyes", "Cruz",
    # African / Arabic
    "Okafor", "Mensah", "Diallo", "Traore", "Ibrahim", "Hassan", "Ali", "Omar",
    # European
    "Müller", "Schmidt", "Weber", "Fischer", "Becker", "Hoffmann", "Koch",
    "Dubois", "Leroy", "Martin", "Bernard", "Petit",
    "Rossi", "Ferrari", "Esposito", "Romano", "Russo",
]

# ---------------------------------------------------------------------------
# Companies — by domain
# ---------------------------------------------------------------------------

COMPANY_NAMES: Dict[str, List[str]] = {
    "saas": [
        "Axiom Labs", "Basecamp Analytics", "CloudPeak Systems", "DataBridge Pro",
        "EdgeFlow Technologies", "FunnelSoft", "GridLogic", "HubStack",
        "InfraPoint", "JetMetrics", "Keystroke AI", "LaunchPad HQ",
        "MeshWorks", "NodeSync", "Omnisend", "PipelineIO",
        "QueryForge", "Relay Systems", "StackBase", "TriggerPoint",
        "Unified Ops", "VaultStream", "WorksiteOS", "Xenon Analytics",
        "YieldMetrics", "ZeroFriction", "Amplitude Corp", "Beacon Software",
        "Catalyst CRM", "Deployly", "Envoy Platforms", "FlowState",
        "Gradient Labs", "HorizonSaaS", "Inline Systems", "Junction Cloud",
        "Kinetic AI", "Lattice HQ", "Momentum Tools", "NexusOne",
    ],
    "ecommerce": [
        "Ashford Retail", "BlueLine Store", "CrestShop", "DeltaMart",
        "Evergreen Goods", "FreshCart", "Gable & Stone", "Harbor Finds",
        "IndigoShop", "Juniper Market", "Kelp Bay Commerce", "Lantern Goods",
        "Maple Retail", "NorthShore Store", "Opal Market", "Pinnacle Shop",
        "QuarterDeck Goods", "Ridgeline Retail", "Summit Store", "Tidal Goods",
        "Uplift Commerce", "Verdant Market", "Willow & Oak", "Xpedite Retail",
        "Yellow Pine Goods", "Zenith Commerce", "Arbor Market", "Birch Retail",
    ],
    "fintech": [
        "Apex Capital", "BlueSky Finance", "Cedar Bank", "Dune Financial",
        "Ember Capital", "Fidelity Edge", "Granite Finance", "Horizon Bank",
        "Ironclad Capital", "Junction Finance", "Keystone Bank", "Ledger One",
        "Meridian Capital", "Northpoint Finance", "Oak Street Bank", "Prism Capital",
        "Quantum Finance", "Riverstone Bank", "Summit Capital", "Torrent Finance",
        "Union Ledger", "Vertex Capital", "Westbank Financial", "Xenith Capital",
    ],
    "healthcare": [
        "Apex Medical Group", "Bright Health Systems", "CarePoint Clinic",
        "Delta Health Partners", "Ember Wellness", "Fortis Medical",
        "Harmony Health", "Integrated Care Solutions", "Junction Medical",
        "Keystone Clinic", "Landmark Health", "Meridian Medical",
        "Novus Health Systems", "Oakwood Clinic", "Pinnacle Care",
        "Quantum Health", "Riverside Medical", "Summit Health Partners",
    ],
    "generic": [
        "Atlas Systems", "Blue Peak Labs", "Cedar Ridge Group", "Dune Analytics",
        "Ember Technologies", "Fortis Solutions", "Granite Works", "Harbor Group",
        "Indigo Partners", "Juniper Solutions", "Keystone Labs", "Lantern Tech",
        "Maple Systems", "Northern Reach", "Opal Group", "Pinnacle Partners",
        "Quartz Solutions", "Ridge Analytics", "Summit Group", "Tidal Systems",
        "Uplift Partners", "Verdant Solutions", "Willow Group", "Xen Labs",
        "Yellow Stone Corp", "Zenith Partners", "Arbor Systems", "Birch Analytics",
        "Canyon Solutions", "Dawn Technologies",
    ],
}

# ---------------------------------------------------------------------------
# Job titles — by domain
# ---------------------------------------------------------------------------

JOB_TITLES: Dict[str, List[str]] = {
    "saas": [
        "Software Engineer", "Senior Software Engineer", "Staff Engineer",
        "Principal Engineer", "Engineering Manager", "VP of Engineering",
        "CTO", "Product Manager", "Senior Product Manager", "Director of Product",
        "VP of Product", "CPO", "Data Analyst", "Data Scientist", "ML Engineer",
        "DevOps Engineer", "Site Reliability Engineer", "Solutions Architect",
        "Customer Success Manager", "Account Executive", "Sales Development Rep",
        "VP of Sales", "Marketing Manager", "Growth Marketer", "Head of Design",
        "UX Designer", "Frontend Engineer", "Backend Engineer", "Full Stack Engineer",
        "Security Engineer", "Platform Engineer", "Technical Program Manager",
        "Head of Customer Success", "Revenue Operations Manager", "CEO", "COO", "CFO",
    ],
    "ecommerce": [
        "Store Manager", "Assistant Store Manager", "Inventory Specialist",
        "Logistics Coordinator", "Supply Chain Manager", "Warehouse Associate",
        "Category Manager", "Merchandising Analyst", "E-commerce Manager",
        "Digital Marketing Specialist", "SEO Analyst", "PPC Manager",
        "Customer Service Rep", "Customer Service Manager", "Returns Specialist",
        "Fulfillment Manager", "Buyer", "Senior Buyer", "Brand Manager",
        "Visual Merchandiser", "Operations Manager", "VP of Operations",
    ],
    "fintech": [
        "Financial Analyst", "Senior Financial Analyst", "Risk Analyst",
        "Risk Manager", "Compliance Officer", "Credit Analyst",
        "Investment Analyst", "Portfolio Manager", "Quantitative Analyst",
        "Chief Risk Officer", "CFO", "Controller", "Treasury Analyst",
        "Fraud Analyst", "AML Analyst", "KYC Specialist", "Account Manager",
        "Relationship Manager", "VP of Finance", "Director of Finance",
        "Actuarial Analyst", "Underwriter", "Loan Officer",
    ],
    "healthcare": [
        "Physician", "Registered Nurse", "Nurse Practitioner", "Physician Assistant",
        "Medical Assistant", "Pharmacist", "Physical Therapist", "Radiologist",
        "Surgeon", "Cardiologist", "Neurologist", "Oncologist", "Pediatrician",
        "Psychiatrist", "Clinical Coordinator", "Medical Records Specialist",
        "Health Information Manager", "Hospital Administrator",
        "Chief Medical Officer", "Director of Nursing", "Lab Technician",
    ],
    "generic": [
        "Software Engineer", "Product Manager", "Marketing Manager",
        "Sales Representative", "Operations Manager", "Data Analyst",
        "Business Analyst", "Project Manager", "HR Manager",
        "Finance Manager", "Customer Support Specialist", "UX Designer",
        "Content Writer", "Account Manager", "Team Lead",
        "Director of Operations", "VP of Marketing", "Chief Executive Officer",
        "Chief Operating Officer", "Chief Financial Officer",
    ],
}

# ---------------------------------------------------------------------------
# Products — conditional on category
# ---------------------------------------------------------------------------

PRODUCT_BY_CATEGORY: Dict[str, List[str]] = {
    "electronics": [
        "Wireless Noise-Cancelling Headphones", "4K OLED Smart TV 55\"",
        "Portable Bluetooth Speaker", "USB-C Laptop Stand", "Mechanical Keyboard",
        "Ergonomic Gaming Mouse", "27\" Monitor 144Hz", "Webcam 1080p",
        "Smart LED Desk Lamp", "Portable Charger 20000mAh",
        "Wireless Earbuds Pro", "Smart Home Hub", "Action Camera 4K",
        "Tablet 10.5\" WiFi", "Smartwatch Series 5", "E-Reader Paperwhite",
        "Dash Cam Front & Rear", "Portable SSD 1TB", "WiFi 6 Router",
        "Smart Plug 4-Pack", "Electric Toothbrush Smart", "Robot Vacuum Pro",
    ],
    "clothing": [
        "Classic Oxford Button-Down Shirt", "Slim-Fit Chino Trousers",
        "Merino Wool V-Neck Sweater", "Waterproof Rain Jacket",
        "High-Waist Yoga Leggings", "Linen Summer Dress",
        "Lightweight Running Shorts", "Puffer Down Jacket",
        "Casual Canvas Sneakers", "Leather Chelsea Boots",
        "Crew-Neck Graphic Tee", "Denim Straight-Leg Jeans",
        "Floral Midi Skirt", "Oversized Hoodie", "Athletic Compression Socks",
        "Formal Blazer Slim", "Cargo Shorts", "Cashmere Scarf",
        "Ankle Strap Sandals", "Knit Beanie Hat",
    ],
    "home": [
        "Cast Iron Skillet 12\"", "Bamboo Cutting Board Set",
        "Stainless Steel Knife Set", "Non-Stick Cookware Set 10-Piece",
        "Cotton Percale Sheet Set Queen", "Memory Foam Pillow",
        "Aromatherapy Diffuser", "Air Purifier HEPA", "Cordless Vacuum",
        "Steam Mop", "Dish Rack Stainless Steel", "Instant Pot 6Qt",
        "French Press Coffee Maker", "Pour-Over Coffee Set",
        "Ceramic Dinnerware Set 12-Piece", "Glass Food Storage Containers",
        "Silicone Baking Mat Set", "Digital Kitchen Scale",
        "Under-Cabinet LED Lights", "Shower Curtain Liner",
    ],
    "books": [
        "Designing Data-Intensive Applications", "Clean Code",
        "The Pragmatic Programmer", "Atomic Habits", "Deep Work",
        "Zero to One", "The Lean Startup", "Good to Great",
        "Thinking, Fast and Slow", "Sapiens", "The Innovators",
        "Educated: A Memoir", "Becoming", "The Power of Habit",
        "Man's Search for Meaning", "12 Rules for Life",
        "The Art of War", "Meditations by Marcus Aurelius",
        "Python Crash Course", "Hands-On Machine Learning",
    ],
    "sports": [
        "Resistance Bands Set 5-Pack", "Adjustable Dumbbells 50lb",
        "Yoga Mat 6mm Non-Slip", "Pull-Up Bar Doorframe",
        "Jump Rope Speed", "Foam Roller Deep Tissue",
        "Running Shoes Trail", "Cycling Helmet", "Tennis Racket Pro",
        "Basketball Official Size", "Soccer Ball Size 5",
        "Swimming Goggles Anti-Fog", "Gym Bag Large", "Weight Belt",
        "Protein Shaker Bottle", "Knee Sleeves Compression",
        "Battle Ropes 40ft", "Agility Ladder", "Medicine Ball 15lb",
        "Ab Wheel Roller",
    ],
    "beauty": [
        "Vitamin C Serum 20%", "Hyaluronic Acid Moisturizer",
        "Retinol Night Cream", "SPF 50 Sunscreen Lightweight",
        "Micellar Cleansing Water", "Charcoal Face Mask",
        "Argan Oil Hair Treatment", "Keratin Smoothing Shampoo",
        "Matte Lipstick Long-Wear", "Eyeshadow Palette 18 Shades",
        "Waterproof Mascara", "Setting Powder Translucent",
        "Tinted Moisturizer SPF 30", "Eyebrow Pencil Micro",
        "Contour Palette 3 Shades", "Sheet Mask Brightening 10-Pack",
        "Jade Roller Face Massager", "Electric Face Cleanser Brush",
    ],
    "food": [
        "Organic Quinoa 2lb", "Extra Virgin Olive Oil 500ml",
        "Almond Butter Crunchy", "Dark Roast Ground Coffee 12oz",
        "Matcha Green Tea Powder", "Coconut Aminos Sauce",
        "Grass-Fed Whey Protein", "Oat Milk Barista Edition",
        "Raw Honey Local 32oz", "Himalayan Pink Salt Grinder",
        "Organic Apple Cider Vinegar", "Probiotic Supplement 30B CFU",
        "Electrolyte Powder Packs", "Collagen Peptides Unflavored",
        "Turmeric Gummies", "Ashwagandha Capsules",
    ],
}

# ---------------------------------------------------------------------------
# Geography — conditional on country
# ---------------------------------------------------------------------------

CITIES_BY_COUNTRY: Dict[str, List[str]] = {
    "United States": [
        "New York", "Los Angeles", "Chicago", "Houston", "Phoenix",
        "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose",
        "Austin", "Jacksonville", "Columbus", "Charlotte", "Indianapolis",
        "Seattle", "Denver", "Washington", "Boston", "El Paso",
        "Nashville", "Portland", "Las Vegas", "Memphis", "Louisville",
        "Baltimore", "Milwaukee", "Albuquerque", "Tucson", "Atlanta",
    ],
    "United Kingdom": [
        "London", "Birmingham", "Leeds", "Glasgow", "Sheffield", "Bradford",
        "Edinburgh", "Liverpool", "Manchester", "Bristol", "Cardiff",
        "Coventry", "Nottingham", "Leicester", "Sunderland", "Belfast",
        "Newcastle", "Brighton", "Plymouth", "Wolverhampton",
    ],
    "Canada": [
        "Toronto", "Montreal", "Vancouver", "Calgary", "Edmonton",
        "Ottawa", "Winnipeg", "Quebec City", "Hamilton", "Kitchener",
        "London", "Victoria", "Halifax", "Oshawa", "Windsor",
        "Saskatoon", "Regina", "Sherbrooke", "St. John's", "Barrie",
    ],
    "Germany": [
        "Berlin", "Hamburg", "Munich", "Cologne", "Frankfurt",
        "Stuttgart", "Düsseldorf", "Leipzig", "Dortmund", "Essen",
        "Bremen", "Dresden", "Hanover", "Nuremberg", "Duisburg",
        "Bochum", "Wuppertal", "Bielefeld", "Bonn", "Münster",
    ],
    "India": [
        "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai",
        "Kolkata", "Ahmedabad", "Pune", "Surat", "Jaipur",
        "Lucknow", "Kanpur", "Nagpur", "Indore", "Thane",
        "Bhopal", "Visakhapatnam", "Patna", "Vadodara", "Ghaziabad",
    ],
    "Australia": [
        "Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide",
        "Gold Coast", "Canberra", "Newcastle", "Wollongong", "Hobart",
        "Geelong", "Townsville", "Cairns", "Darwin", "Ballarat",
    ],
    "France": [
        "Paris", "Marseille", "Lyon", "Toulouse", "Nice",
        "Nantes", "Strasbourg", "Montpellier", "Bordeaux", "Lille",
        "Rennes", "Reims", "Saint-Étienne", "Toulon", "Grenoble",
    ],
    "Brazil": [
        "São Paulo", "Rio de Janeiro", "Brasília", "Salvador", "Fortaleza",
        "Belo Horizonte", "Manaus", "Curitiba", "Recife", "Porto Alegre",
        "Belém", "Goiânia", "Guarulhos", "Campinas", "São Luís",
    ],
    "Japan": [
        "Tokyo", "Osaka", "Nagoya", "Sapporo", "Fukuoka",
        "Kawasaki", "Kobe", "Kyoto", "Saitama", "Hiroshima",
        "Sendai", "Kitakyushu", "Chiba", "Sakai", "Kumamoto",
    ],
    "Netherlands": [
        "Amsterdam", "Rotterdam", "The Hague", "Utrecht", "Eindhoven",
        "Tilburg", "Groningen", "Almere", "Breda", "Nijmegen",
    ],
}

STATES_BY_COUNTRY: Dict[str, List[str]] = {
    "United States": [
        "California", "Texas", "Florida", "New York", "Pennsylvania",
        "Illinois", "Ohio", "Georgia", "North Carolina", "Michigan",
        "New Jersey", "Virginia", "Washington", "Arizona", "Massachusetts",
        "Tennessee", "Indiana", "Missouri", "Maryland", "Wisconsin",
        "Colorado", "Minnesota", "South Carolina", "Alabama", "Louisiana",
        "Kentucky", "Oregon", "Oklahoma", "Connecticut", "Utah",
    ],
    "United Kingdom": ["England", "Scotland", "Wales", "Northern Ireland"],
    "Canada": [
        "Ontario", "Quebec", "British Columbia", "Alberta", "Manitoba",
        "Saskatchewan", "Nova Scotia", "New Brunswick", "Newfoundland",
    ],
    "Germany": [
        "Bavaria", "North Rhine-Westphalia", "Baden-Württemberg",
        "Lower Saxony", "Hesse", "Saxony", "Berlin", "Rhineland-Palatinate",
        "Brandenburg", "Hamburg",
    ],
    "India": [
        "Maharashtra", "Uttar Pradesh", "Karnataka", "Gujarat", "Tamil Nadu",
        "Rajasthan", "West Bengal", "Madhya Pradesh", "Telangana", "Bihar",
        "Andhra Pradesh", "Kerala", "Haryana", "Delhi", "Punjab",
    ],
    "Australia": [
        "New South Wales", "Victoria", "Queensland", "Western Australia",
        "South Australia", "Tasmania", "Australian Capital Territory",
        "Northern Territory",
    ],
    "Brazil": [
        "São Paulo", "Rio de Janeiro", "Minas Gerais", "Bahia", "Paraná",
        "Rio Grande do Sul", "Pernambuco", "Ceará", "Pará", "Santa Catarina",
        "Goiás", "Amazonas", "Espírito Santo", "Distrito Federal", "Mato Grosso",
    ],
    "France": [
        "Île-de-France", "Auvergne-Rhône-Alpes", "Provence-Alpes-Côte d'Azur",
        "Nouvelle-Aquitaine", "Occitanie", "Hauts-de-France", "Grand Est",
        "Pays de la Loire", "Normandie", "Bretagne", "Bourgogne-Franche-Comté",
        "Centre-Val de Loire",
    ],
    "Japan": [
        "Tokyo", "Osaka", "Kanagawa", "Aichi", "Saitama", "Chiba", "Hyogo",
        "Hokkaido", "Fukuoka", "Shizuoka", "Kyoto", "Hiroshima", "Miyagi",
        "Nagano", "Okinawa",
    ],
    "Netherlands": [
        "North Holland", "South Holland", "Utrecht", "North Brabant",
        "Gelderland", "Overijssel", "Limburg", "Groningen", "Friesland",
        "Drenthe", "Flevoland", "Zeeland",
    ],
}

# US cities as atomic address tuples: (state name, state code, ZIP3 prefix).
# The three values are drawn AS ONE UNIT — a city determines its state and its
# zip range, they are facts, not distributions. Every ZIP3 prefix here is real
# and unique to its city, so "one state per city" and "one city per zip" both
# hold by construction in any table built from this map.
US_CITY_GEO: Dict[str, tuple] = {
    "New York":       ("New York", "NY", "100"),
    "Los Angeles":    ("California", "CA", "900"),
    "Chicago":        ("Illinois", "IL", "606"),
    "Houston":        ("Texas", "TX", "770"),
    "Phoenix":        ("Arizona", "AZ", "850"),
    "Philadelphia":   ("Pennsylvania", "PA", "191"),
    "San Antonio":    ("Texas", "TX", "782"),
    "San Diego":      ("California", "CA", "921"),
    "Dallas":         ("Texas", "TX", "752"),
    "San Jose":       ("California", "CA", "951"),
    "Austin":         ("Texas", "TX", "787"),
    "Jacksonville":   ("Florida", "FL", "322"),
    "Fort Worth":     ("Texas", "TX", "761"),
    "Columbus":       ("Ohio", "OH", "432"),
    "Charlotte":      ("North Carolina", "NC", "282"),
    "San Francisco":  ("California", "CA", "941"),
    "Indianapolis":   ("Indiana", "IN", "462"),
    "Seattle":        ("Washington", "WA", "981"),
    "Denver":         ("Colorado", "CO", "802"),
    "Boston":         ("Massachusetts", "MA", "021"),
    "El Paso":        ("Texas", "TX", "799"),
    "Nashville":      ("Tennessee", "TN", "372"),
    "Detroit":        ("Michigan", "MI", "482"),
    "Oklahoma City":  ("Oklahoma", "OK", "731"),
    "Portland":       ("Oregon", "OR", "972"),
    "Las Vegas":      ("Nevada", "NV", "891"),
    "Memphis":        ("Tennessee", "TN", "381"),
    "Louisville":     ("Kentucky", "KY", "402"),
    "Baltimore":      ("Maryland", "MD", "212"),
    "Milwaukee":      ("Wisconsin", "WI", "532"),
    "Albuquerque":    ("New Mexico", "NM", "871"),
    "Tucson":         ("Arizona", "AZ", "857"),
    "Fresno":         ("California", "CA", "937"),
    "Sacramento":     ("California", "CA", "958"),
    "Kansas City":    ("Missouri", "MO", "641"),
    "Atlanta":        ("Georgia", "GA", "303"),
    "Miami":          ("Florida", "FL", "331"),
    "Omaha":          ("Nebraska", "NE", "681"),
    "Raleigh":        ("North Carolina", "NC", "276"),
    "Minneapolis":    ("Minnesota", "MN", "554"),
    "Tampa":          ("Florida", "FL", "336"),
    "New Orleans":    ("Louisiana", "LA", "701"),
    "Cleveland":      ("Ohio", "OH", "441"),
    "Pittsburgh":     ("Pennsylvania", "PA", "152"),
    "St. Louis":      ("Missouri", "MO", "631"),
    "Cincinnati":     ("Ohio", "OH", "452"),
    "Orlando":        ("Florida", "FL", "328"),
    "Salt Lake City": ("Utah", "UT", "841"),
    "Washington":     ("District of Columbia", "DC", "200"),
    "Richmond":       ("Virginia", "VA", "232"),
}

assert len({v[2] for v in US_CITY_GEO.values()}) == len(US_CITY_GEO), \
    "US_CITY_GEO ZIP3 prefixes must be unique per city"


# City -> its actual state/province/region. Keeps a row's full address chain
# consistent: São Paulo belongs in São Paulo state, not a random Brazilian one.
CITY_STATE: Dict[str, str] = {
    "New York": "New York", "Los Angeles": "California", "Chicago": "Illinois",
    "Houston": "Texas", "Phoenix": "Arizona", "Philadelphia": "Pennsylvania",
    "San Antonio": "Texas", "San Diego": "California", "Dallas": "Texas",
    "San Jose": "California", "Austin": "Texas", "Seattle": "Washington",
    "Denver": "Colorado", "Boston": "Massachusetts", "Atlanta": "Georgia",
    "Miami": "Florida", "Minneapolis": "Minnesota", "Portland": "Oregon",
    "London": "England", "Manchester": "England", "Birmingham": "England",
    "Edinburgh": "Scotland", "Bristol": "England", "Leeds": "England",
    "Toronto": "Ontario", "Vancouver": "British Columbia",
    "Montreal": "Quebec", "Calgary": "Alberta",
    "Berlin": "Berlin", "Munich": "Bavaria", "Hamburg": "Hamburg",
    "Frankfurt": "Hesse",
    "Mumbai": "Maharashtra", "Delhi": "Delhi", "Bangalore": "Karnataka",
    "Hyderabad": "Telangana", "Chennai": "Tamil Nadu",
    "Sydney": "New South Wales", "Melbourne": "Victoria",
    "Brisbane": "Queensland", "Perth": "Western Australia",
    "Paris": "Île-de-France", "Lyon": "Auvergne-Rhône-Alpes",
    "Marseille": "Provence-Alpes-Côte d'Azur",
    "Tokyo": "Tokyo", "Osaka": "Osaka", "Kyoto": "Kyoto",
    "São Paulo": "São Paulo", "Rio de Janeiro": "Rio de Janeiro",
    "Amsterdam": "North Holland", "Rotterdam": "South Holland",
    "Dubai": "Dubai", "Abu Dhabi": "Abu Dhabi",
    "Seoul": "Seoul", "Busan": "Busan",
    "Mexico City": "Mexico City", "Guadalajara": "Jalisco",
}

# ---------------------------------------------------------------------------
# Geospatial — city coordinates + postal code patterns
# ---------------------------------------------------------------------------

# (city, lat, lng, postal_prefix, country_code)
CITY_GEODATA: List[tuple] = [
    # United States
    ("New York",       40.7128,  -74.0060,  "10",  "US"),
    ("Los Angeles",    34.0522, -118.2437,  "90",  "US"),
    ("Chicago",        41.8781,  -87.6298,  "60",  "US"),
    ("Houston",        29.7604,  -95.3698,  "77",  "US"),
    ("Phoenix",        33.4484, -112.0740,  "85",  "US"),
    ("Philadelphia",   39.9526,  -75.1652,  "19",  "US"),
    ("San Antonio",    29.4241,  -98.4936,  "78",  "US"),
    ("San Diego",      32.7157, -117.1611,  "92",  "US"),
    ("Dallas",         32.7767,  -96.7970,  "75",  "US"),
    ("San Jose",       37.3382, -121.8863,  "95",  "US"),
    ("Austin",         30.2672,  -97.7431,  "78",  "US"),
    ("Seattle",        47.6062, -122.3321,  "98",  "US"),
    ("Denver",         39.7392, -104.9903,  "80",  "US"),
    ("Boston",         42.3601,  -71.0589,  "02",  "US"),
    ("Atlanta",        33.7490,  -84.3880,  "30",  "US"),
    ("Miami",          25.7617,  -80.1918,  "33",  "US"),
    ("Minneapolis",    44.9778,  -93.2650,  "55",  "US"),
    ("Portland",       45.5051, -122.6750,  "97",  "US"),
    # United Kingdom
    ("London",         51.5074,   -0.1278,  "EC",  "GB"),
    ("Manchester",     53.4808,   -2.2426,  "M",   "GB"),
    ("Birmingham",     52.4862,   -1.8904,  "B",   "GB"),
    ("Edinburgh",      55.9533,   -3.1883,  "EH",  "GB"),
    ("Bristol",        51.4545,   -2.5879,  "BS",  "GB"),
    ("Leeds",          53.8008,   -1.5491,  "LS",  "GB"),
    # Canada
    ("Toronto",        43.6532,  -79.3832,  "M",   "CA"),
    ("Vancouver",      49.2827, -123.1207,  "V",   "CA"),
    ("Montreal",       45.5017,  -73.5673,  "H",   "CA"),
    ("Calgary",        51.0447, -114.0719,  "T",   "CA"),
    # Germany
    ("Berlin",         52.5200,   13.4050,  "10",  "DE"),
    ("Munich",         48.1351,   11.5820,  "80",  "DE"),
    ("Hamburg",        53.5753,    9.9950,  "20",  "DE"),
    ("Frankfurt",      50.1109,    8.6821,  "60",  "DE"),
    # India
    ("Mumbai",         19.0760,   72.8777,  "400", "IN"),
    ("Delhi",          28.6139,   77.2090,  "110", "IN"),
    ("Bangalore",      12.9716,   77.5946,  "560", "IN"),
    ("Hyderabad",      17.3850,   78.4867,  "500", "IN"),
    ("Chennai",        13.0827,   80.2707,  "600", "IN"),
    # Australia
    ("Sydney",        -33.8688,  151.2093,  "2",   "AU"),
    ("Melbourne",     -37.8136,  144.9631,  "3",   "AU"),
    ("Brisbane",      -27.4698,  153.0251,  "4",   "AU"),
    ("Perth",         -31.9505,  115.8605,  "6",   "AU"),
    # France
    ("Paris",          48.8566,    2.3522,  "75",  "FR"),
    ("Lyon",           45.7640,    4.8357,  "69",  "FR"),
    ("Marseille",      43.2965,    5.3698,  "13",  "FR"),
    # Japan
    ("Tokyo",          35.6762,  139.6503,  "100", "JP"),
    ("Osaka",          34.6937,  135.5023,  "530", "JP"),
    ("Kyoto",          35.0116,  135.7681,  "600", "JP"),
    # Brazil
    ("São Paulo",     -23.5505,  -46.6333,  "01",  "BR"),
    ("Rio de Janeiro",-22.9068,  -43.1729,  "20",  "BR"),
    # Singapore
    ("Singapore",       1.3521,  103.8198,  "01",  "SG"),
    # Netherlands
    ("Amsterdam",      52.3676,    4.9041,  "10",  "NL"),
    ("Rotterdam",      51.9244,    4.4777,  "30",  "NL"),
    # UAE
    ("Dubai",          25.2048,   55.2708,  "000", "AE"),
    ("Abu Dhabi",      24.4539,   54.3773,  "000", "AE"),
    # South Korea
    ("Seoul",          37.5665,  126.9780,  "03",  "KR"),
    ("Busan",          35.1796,  129.0756,  "46",  "KR"),
    # Mexico
    ("Mexico City",    19.4326,  -99.1332,  "06",  "MX"),
    ("Guadalajara",    20.6597, -103.3496,  "44",  "MX"),
]

# ---------------------------------------------------------------------------
# SaaS-specific vocabulary
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Food delivery — restaurants and menu items
# ---------------------------------------------------------------------------

RESTAURANT_NAMES: List[str] = [
    # American / Casual
    "The Rusty Fork", "Ember & Ash", "Corner Table", "The Griddle House",
    "Blue Smoke Kitchen", "Oak & Barrel", "The Smokehouse", "Copper Pot",
    "The Kitchen Sink", "Pinewood Grill", "Salt & Cedar", "The Foundry",
    # Italian
    "Trattoria Bella", "Pasta Roma", "La Cucina", "Olive & Vine",
    "Piedmont Kitchen", "Casa Napoli", "Al Forno", "Nonna's Table",
    # Asian
    "Golden Wok", "Sakura Garden", "Pho & Co.", "Dragon Palace",
    "Umami House", "Lantern Kitchen", "Jade Spoon", "Bamboo Bistro",
    "Ramen Republic", "Lotus Bowl", "Seoul Kitchen", "Miso & More",
    # Mexican / Latin
    "La Cantina", "Taqueria El Sol", "Casa Fuego", "Verde Kitchen",
    "Señor Cactus", "Aztec Grill", "Barrio Eats", "El Patio",
    # Middle Eastern / Mediterranean
    "The Olive Branch", "Mezze House", "Falafel & Friends", "Cedar Grill",
    "Saffron Kitchen", "The Levant", "Byblos Bistro", "Anatolia",
    # Indian
    "Spice Route", "The Curry Leaf", "Mumbai Masala", "Tandoor House",
    "Saffron Palace", "Chai & Spice", "Delhi Darbar", "The Maharaja",
    # Burgers / Fast Casual
    "Stack'd", "The Patty Lab", "Bun & Done", "Smash Bros. Burgers",
    "Burnside Burgers", "The Melt Factory", "Juicy Lucy's", "Stack House",
    # Pizza
    "Fire & Dough", "Slice of Heaven", "The Pizza Lab", "Crust & Craft",
    "Stone Deck Pizza", "Woodfire & Co.", "Circle Pie", "The Pie Hole",
    # Healthy / Bowls
    "Greens & Grains", "The Nourish Bowl", "Clean Plate", "Harvest Table",
    "Roots Kitchen", "The Green Fork", "Vitality Bowls", "Fresh Assembly",
    # Breakfast / Brunch
    "Sunrise Plate", "The Crack of Dawn", "Morning Glory Café", "Yolk & Folk",
    "The Brunch Club", "Sunny Side Up", "Maple & Butter", "The Early Bird",
]

MENU_ITEMS_BY_CATEGORY: Dict[str, List[str]] = {
    "main": [
        "Grilled Chicken Sandwich", "BBQ Beef Burger", "Margherita Pizza 12\"",
        "Butter Chicken with Naan", "Pad Thai with Shrimp", "Beef Tacos (3-pack)",
        "Spaghetti Bolognese", "Salmon Teriyaki Bowl", "Veggie Burrito Bowl",
        "Crispy Fish & Chips", "Pulled Pork Sandwich", "Chicken Tikka Masala",
        "Pho Bo (Beef Noodle Soup)", "Bibimbap with Tofu", "Lamb Shawarma Wrap",
        "Mushroom Risotto", "Pepperoni Calzone", "General Tso's Chicken",
        "Falafel Plate with Hummus", "Club Sandwich", "Ramen Tonkotsu",
        "Shrimp Tacos (2-pack)", "Eggplant Parmesan", "Beef Banh Mi",
        "Chicken Caesar Wrap", "Steak Burrito", "Paneer Tikka",
    ],
    "side": [
        "Seasoned French Fries", "Sweet Potato Fries", "Garlic Bread (4-piece)",
        "Side Salad", "Coleslaw", "Onion Rings", "Mashed Potatoes",
        "Steamed Broccoli", "Mac & Cheese", "Roasted Vegetables",
        "Corn on the Cob", "Rice (Steamed)", "Naan Bread (2-piece)",
        "Edamame", "Spring Rolls (2-piece)", "Soup of the Day",
        "Kimchi", "Pita Bread with Tzatziki", "Chips & Guacamole",
    ],
    "drink": [
        "Coca-Cola (16oz)", "Diet Coke (16oz)", "Lemonade (16oz)",
        "Iced Tea (16oz)", "Orange Juice", "Sparkling Water",
        "Mango Lassi", "Thai Iced Tea", "Horchata",
        "Strawberry Lemonade", "Apple Juice", "Green Smoothie",
        "Chai Latte", "Watermelon Juice", "Coconut Water",
        "Kombucha Original", "Root Beer (16oz)", "Passion Fruit Drink",
    ],
    "dessert": [
        "Chocolate Lava Cake", "Tiramisu", "Mango Sorbet",
        "New York Cheesecake", "Crème Brûlée", "Gulab Jamun (2-piece)",
        "Churros with Dipping Sauce", "Mochi Ice Cream (3-piece)",
        "Apple Pie Slice", "Brownie Sundae", "Tres Leches Cake",
        "Cannoli (2-piece)", "Baklava", "Panna Cotta",
        "Matcha Cheesecake", "Fried Plantains with Ice Cream",
    ],
    "starter": [
        "Buffalo Wings (6-piece)", "Soup & Salad Combo",
        "Spinach Artichoke Dip", "Bruschetta (3-piece)", "Samosa (2-piece)",
        "Dumplings (6-piece)", "Nachos Supreme", "Hummus with Pita",
        "Calamari Fritti", "Charcuterie Board (small)", "Edamame (salted)",
        "Chicken Satay (4-piece)", "Ceviche Cup", "Stuffed Mushrooms",
    ],
    "combo": [
        "Burger + Fries + Drink", "2 Tacos + Rice + Drink",
        "Pizza Slice + Side Salad + Drink", "Pasta + Garlic Bread + Drink",
        "Wrap + Fries + Drink", "Bowl + Side + Drink",
        "Family Meal (4 mains + 2 sides)", "Lunch Special (main + drink)",
        "Date Night Set (2 mains + dessert)", "Kids Meal + Drink + Dessert",
    ],
}

# ---------------------------------------------------------------------------
# Research / pharma project names
# ---------------------------------------------------------------------------

RESEARCH_PROJECT_NAMES: List[str] = [
    "Project Aurora", "Initiative Helix", "Study Olympus", "Trial Meridian",
    "Protocol Vanguard", "Program Apex", "Study Horizon", "Initiative Sigma",
    "Project Catalyst", "Protocol Zenith", "Trial Vertex", "Program Solstice",
    "Project Lynx", "Study Polaris", "Initiative Titan", "Protocol Atlas",
    "Program Orion", "Trial Phoenix", "Project Crest", "Study Prism",
    "Initiative Forge", "Protocol Strata", "Program Nexus", "Project Delta-7",
    "Study GEN-402", "Trial RX-09", "Protocol CL-21", "Initiative MED-5",
]

# ---------------------------------------------------------------------------
# Social / comment short text
# ---------------------------------------------------------------------------

COMMENT_BODIES: List[str] = [
    "This is amazing!", "Love this so much 🔥", "Totally agree!",
    "Can't stop laughing 😂", "This made my day", "Omg yes!",
    "So true", "Incredible work", "Goals 🙌", "Need this in my life",
    "How did you do that?", "Obsessed with this", "Tag your bestie!",
    "Saving this for later", "The best content on here",
    "This deserves more likes", "I'm crying 😭", "Literally me every day",
    "Where is this??", "You never miss 🎯", "Legend",
    "Not me watching this 10 times", "Okay but this is fire 🔥",
    "Why does this have so few views?", "This hits different",
    "Living for this energy ✨", "Can you do a tutorial?",
    "Sending this to everyone I know", "Underrated post right here",
    "This should be trending", "Valid 💯", "Period.",
]

# ---------------------------------------------------------------------------
# SaaS-specific vocabulary
# ---------------------------------------------------------------------------

PLAN_NAMES: List[str] = [
    "Free", "Starter", "Basic", "Growth", "Pro", "Professional",
    "Business", "Team", "Scale", "Enterprise", "Ultimate", "Premium",
    "Plus", "Advanced", "Elite",
]

FEATURE_NAMES: List[str] = [
    "Single Sign-On", "API Access", "Audit Logs", "Custom Domains",
    "Priority Support", "99.9% SLA", "Advanced Analytics", "Data Export",
    "Role-Based Access", "Two-Factor Authentication", "Webhooks",
    "Custom Integrations", "White Labelling", "Dedicated Account Manager",
    "SAML Authentication", "IP Whitelisting", "Custom Reporting",
    "Unlimited Storage", "Team Collaboration", "Version History",
]

# ---------------------------------------------------------------------------
# Media, food, and creative-work vocabularies (0.8.1.15)
# ---------------------------------------------------------------------------

FILM_GENRES = [
    "Drama", "Comedy", "Thriller", "Action", "Horror", "Romance",
    "Science Fiction", "Documentary", "Animation", "Crime", "Mystery",
    "Fantasy", "Adventure", "Biography", "Family", "War", "Western",
    "Musical", "Film Noir", "Romantic Comedy",
]

MUSIC_GENRES = [
    "Pop", "Rock", "Hip Hop", "R&B", "Jazz", "Classical", "Electronic",
    "Country", "Folk", "Indie Rock", "Metal", "Blues", "Reggae", "Soul",
    "Punk", "Ambient", "House", "Techno", "Latin", "Gospel", "K-Pop",
    "Afrobeats", "Lo-fi",
]

BOOK_GENRES = [
    "Literary Fiction", "Mystery", "Thriller", "Romance", "Science Fiction",
    "Fantasy", "Historical Fiction", "Biography", "Memoir", "Self-Help",
    "Young Adult", "Horror", "Poetry", "True Crime", "Business",
]

CUISINES = [
    "Italian", "Mexican", "Chinese", "Japanese", "Indian", "Thai", "French",
    "Greek", "Spanish", "Korean", "Vietnamese", "Turkish", "Lebanese",
    "Moroccan", "Ethiopian", "Brazilian", "Peruvian", "American",
    "Mediterranean", "Middle Eastern", "Caribbean", "German", "British",
    "Filipino", "Malaysian", "Indonesian", "Portuguese", "Polish",
    "Argentinian", "Cajun",
]

INGREDIENTS = [
    "olive oil", "garlic", "onion", "tomato", "basil", "chicken breast",
    "ground beef", "salmon", "shrimp", "tofu", "rice", "pasta", "flour",
    "butter", "eggs", "milk", "parmesan", "mozzarella", "cheddar", "lemon",
    "lime", "ginger", "soy sauce", "chili flakes", "black pepper", "sea salt",
    "cumin", "paprika", "oregano", "thyme", "rosemary", "cilantro", "parsley",
    "spinach", "mushrooms", "bell pepper", "zucchini", "eggplant", "potatoes",
    "carrots", "celery", "avocado", "black beans", "chickpeas", "lentils",
    "coconut milk", "honey", "brown sugar", "cinnamon", "vanilla extract",
]

# Compositional creative-work titles: patterns x nouns x adjectives gives
# thousands of distinct, plausible titles without an LLM.
WORK_TITLE_NOUNS = [
    "Garden", "River", "Shadow", "Horizon", "Echo", "Winter", "Summer",
    "Harbor", "Mountain", "Letter", "Promise", "Silence", "Storm", "Mirror",
    "Journey", "Kingdom", "Daughter", "Son", "Stranger", "House", "City",
    "Ocean", "Night", "Morning", "Memory", "Secret", "Bridge", "Fire",
    "Crown", "Compass", "Lighthouse", "Orchard", "Sparrow", "Wolf", "Tide",
]

WORK_TITLE_ADJECTIVES = [
    "Last", "Silent", "Hidden", "Broken", "Golden", "Distant", "Forgotten",
    "Endless", "Quiet", "Burning", "Lost", "Crimson", "Hollow", "Bright",
    "Restless", "Wandering", "Frozen", "Midnight", "Paper", "Glass",
]

WORK_TITLE_PATTERNS = [
    "The {adj} {noun}",
    "{adj} {noun}",
    "The {noun} of {noun2}",
    "A {noun} in the {noun2}",
    "{noun} and {noun2}",
    "The {noun}'s {noun2}",
    "Beyond the {noun}",
    "After the {noun}",
    "{adj} {noun}s",
]

# Plot-summary grammar: sentence frames x pools ≈ 10^4 combinations.
PLOT_PROTAGONISTS = [
    "a retired detective", "a young cartographer", "an ambitious chef",
    "a grieving architect", "a small-town librarian", "a fading pop star",
    "a war photographer", "an exiled prince", "a marine biologist",
    "a reluctant heir", "a night-shift nurse", "a chess prodigy",
    "a lighthouse keeper", "an undercover journalist", "a jazz pianist",
]

PLOT_INCIDENTS = [
    "a letter from a stranger arrives", "an old friend disappears",
    "a storm cuts the town off", "a family secret surfaces",
    "a rival returns home", "an inheritance comes with conditions",
    "a wrongful conviction is reopened", "a mysterious map is found",
    "the family business collapses", "a decades-old photograph resurfaces",
]

PLOT_GOALS = [
    "uncover the truth", "win back what was lost", "clear an innocent name",
    "finish what their mentor started", "protect the only home they know",
    "outrun their past", "solve a case everyone abandoned",
    "reunite a scattered family", "expose a quiet conspiracy",
    "keep an impossible promise",
]

PLOT_STAKES = [
    "before the past catches up", "before the town votes to sell",
    "as winter closes in", "while everyone watches",
    "at the cost of everything familiar", "before the trial ends",
    "with time running out", "against their own family",
    "as old loyalties unravel", "before the secret destroys them",
]

# ---------------------------------------------------------------------------
# Reference-table label pools (0.8.1.16)
# A `<head>_types` / `<head>_statuses` lookup table's label column should hold
# labels for THAT head noun, not generic tier words.
# ---------------------------------------------------------------------------

REFERENCE_TYPE_POOLS: Dict[str, List[str]] = {
    "property": ["House", "Apartment", "Condo", "Townhouse", "Villa",
                 "Studio", "Duplex", "Penthouse", "Cottage", "Land"],
    "listing": ["Standard", "Featured", "Premium", "Open House", "Auction",
                "Short Sale", "Foreclosure", "New Construction"],
    "room": ["Single", "Double", "Twin", "Suite", "Deluxe", "Studio",
             "Family", "Penthouse", "Accessible", "Connecting"],
    "vehicle": ["Sedan", "SUV", "Hatchback", "Pickup Truck", "Coupe",
                "Minivan", "Convertible", "Wagon", "Crossover", "Van"],
    "employment": ["Full-time", "Part-time", "Contract", "Temporary",
                   "Internship", "Freelance", "Seasonal", "Apprenticeship"],
    "payment": ["Credit Card", "Debit Card", "Bank Transfer", "PayPal",
                "Cash", "Check", "Wire Transfer", "Digital Wallet"],
    "account": ["Checking", "Savings", "Business", "Joint", "Student",
                "Money Market", "Trust", "Retirement"],
    "subscription": ["Free", "Basic", "Standard", "Premium", "Enterprise",
                     "Trial", "Student", "Family"],
    "membership": ["Basic", "Silver", "Gold", "Platinum", "Student",
                   "Corporate", "Family", "Lifetime"],
    "contract": ["Fixed-term", "Permanent", "Zero-hours", "Freelance",
                 "Retainer", "Project-based", "Consulting"],
    "event": ["Conference", "Concert", "Festival", "Sporting Event",
              "Workshop", "Meetup", "Launch", "Networking", "Training"],
    "ticket": ["General Admission", "VIP", "Early Bird", "Student",
               "Group", "Season Pass", "Day Pass", "Backstage"],
    "insurance": ["Auto", "Home", "Life", "Health", "Travel", "Renters",
                  "Pet", "Disability", "Umbrella"],
    "policy": ["Auto", "Home", "Life", "Health", "Travel", "Renters",
               "Commercial", "Liability"],
    "loan": ["Personal", "Mortgage", "Auto", "Student", "Business",
             "Home Equity", "Payday", "Consolidation"],
    "shipping": ["Standard", "Express", "Overnight", "Two-Day",
                 "International", "Freight", "Same-Day", "Economy"],
    "product": ["Electronics", "Clothing", "Home & Garden", "Books",
                "Sports", "Beauty", "Toys", "Groceries", "Automotive"],
    "surge_event": ["High Demand", "Concert", "Sporting Event", "Bad Weather",
                    "Rush Hour", "Airport Peak", "Holiday", "Festival"],
    "surge_pricing_event": ["High Demand", "Concert", "Sporting Event",
                            "Bad Weather", "Rush Hour", "Airport Peak",
                            "Holiday", "Festival"],
    "ride": ["Economy", "Comfort", "XL", "Premium", "Shared", "Luxury",
             "Pet-Friendly", "Wheelchair Accessible"],
    "trip": ["Economy", "Comfort", "XL", "Premium", "Shared", "Luxury",
             "Airport", "Scheduled"],
    "delivery": ["Standard", "Express", "Same-Day", "Scheduled",
                 "Contactless", "Grocery", "Pharmacy", "Oversized"],
    "driver": ["Full-time", "Part-time", "Weekend", "Night Shift",
               "Fleet", "Owner-Operator", "Courier", "Chauffeur"],
    "merchant": ["Grocery", "Restaurants & Dining", "Fuel & Convenience",
                 "Travel & Airlines", "Electronics", "Pharmacy & Health",
                 "Entertainment", "Apparel & Accessories",
                 "Utilities & Telecom", "Digital Goods"],
}

SURGE_REASONS = [
    "High demand", "Bad weather", "Rush hour", "Concert nearby",
    "Sporting event", "Airport peak", "Holiday traffic", "Driver shortage",
]

CANCELLATION_REASONS = [
    "Changed plans", "Wait too long", "Booked by mistake", "Found alternative",
    "Driver too far", "Price too high", "Emergency", "No longer needed",
]

# Lifecycle labels for `<head>_statuses` lookup tables. Domain-specific pools
# first; the generic pool covers everything else. All are sampled distinct.
REFERENCE_STATUS_POOLS: Dict[str, List[str]] = {
    "listing": ["Active", "Pending", "Sold", "Under Offer", "Withdrawn",
                "Expired", "Coming Soon", "Off Market"],
    "order": ["Pending", "Confirmed", "Processing", "Shipped", "Delivered",
              "Cancelled", "Returned", "Refunded"],
    "payment": ["Pending", "Authorized", "Paid", "Failed", "Refunded",
                "Disputed", "Cancelled", "Expired"],
    "invoice": ["Draft", "Sent", "Viewed", "Paid", "Overdue", "Disputed",
                "Cancelled", "Written Off"],
    "application": ["Submitted", "Under Review", "Interview", "Offer",
                    "Accepted", "Rejected", "Withdrawn", "On Hold"],
    "ticket": ["Open", "In Progress", "Waiting on Customer", "Escalated",
               "Resolved", "Closed", "Reopened"],
    "shipment": ["Label Created", "Picked Up", "In Transit",
                 "Out for Delivery", "Delivered", "Delayed", "Returned"],
    "subscription": ["Trial", "Active", "Past Due", "Paused", "Cancelled",
                     "Expired", "Churned"],
    "supplier": ["Verified", "Active", "Pending Review", "Onboarding",
                 "Suspended", "Inactive", "Churned"],
    "trip": ["Requested", "Accepted", "Driver En Route", "In Progress",
             "Completed", "Cancelled", "No Show"],
    "ride": ["Requested", "Accepted", "Driver En Route", "In Progress",
             "Completed", "Cancelled", "No Show"],
    "vendor": ["Verified", "Active", "Pending Review", "Onboarding",
               "Suspended", "Inactive"],
    "driver": ["Online", "Offline", "On Trip", "Available", "On Break",
               "Pending Approval", "Suspended", "Deactivated"],
    "delivery": ["Order Placed", "Preparing", "Ready for Pickup",
                 "Courier Assigned", "Picked Up", "In Transit",
                 "Delivered", "Cancelled"],
    "vehicle": ["Active", "In Maintenance", "Pending Inspection",
                "Approved", "Retired", "Deactivated"],
    "transaction": ["Approved", "Declined", "Pending", "Settled",
                    "Reversed", "Refunded", "Flagged for Review"],
}

# `<head>_channels` lookup tables. Transaction channels are payment rails;
# the generic pool covers sales/marketing-ish channel tables.
REFERENCE_CHANNEL_POOLS: Dict[str, List[str]] = {
    "transaction": ["Online", "In-store", "Contactless", "Phone Order",
                    "Recurring", "ATM", "Mobile Wallet"],
    "payment": ["Online", "In-store", "Contactless", "Phone Order",
                "Recurring", "ATM", "Mobile Wallet"],
    "sales": ["Online", "Retail", "Partner", "Direct", "Wholesale",
              "Marketplace", "Field Sales"],
}

GENERIC_CHANNELS = [
    "Online", "In-store", "Mobile", "Phone", "Partner", "Direct", "Email",
]

GENERIC_STATUSES = [
    "Active", "Pending", "Completed", "Cancelled", "Expired", "Draft",
    "Archived", "On Hold", "Suspended", "Closed", "Failed", "Approved",
]

# `<head>_segments` lookup tables (buyer_segments must never hold person names).
REFERENCE_SEGMENT_POOLS: Dict[str, List[str]] = {
    "buyer": ["Enterprise", "Mid-Market", "SMB", "Startup", "Individual",
              "Government", "Non-Profit", "Education"],
    "customer": ["Enterprise", "Mid-Market", "SMB", "Startup", "Individual",
                 "VIP", "At-Risk", "New"],
    "market": ["Enterprise", "Mid-Market", "Small Business", "Consumer",
               "Public Sector", "Education", "Healthcare"],
    "user": ["Power User", "Regular", "Casual", "Trial", "Dormant",
             "Champion", "New"],
}

GENERIC_SEGMENTS = [
    "Enterprise", "Mid-Market", "SMB", "Startup", "Individual",
    "Premium", "Standard", "Budget",
]

# `<head>_sizes` lookup tables (supplier_sizes must never hold company names).
REFERENCE_SIZE_POOLS: Dict[str, List[str]] = {
    "supplier": ["Micro", "Small", "Medium", "Large", "Enterprise"],
    "company": ["Micro (1-9)", "Small (10-49)", "Medium (50-249)",
                "Large (250-999)", "Enterprise (1000+)"],
    "business": ["Micro", "Small", "Medium", "Large", "Enterprise"],
    "team": ["Solo", "Small (2-5)", "Medium (6-15)", "Large (16-50)",
             "Department (50+)"],
}

GENERIC_SIZES = [
    "Extra Small", "Small", "Medium", "Large", "Extra Large",
]

# `<head>_tiers` / `<head>_levels` / grades / bands / brackets.
REFERENCE_TIER_POOLS: Dict[str, List[str]] = {
    "plan": ["Free", "Basic", "Pro", "Business", "Enterprise"],
    "subscription": ["Free", "Basic", "Standard", "Premium", "Enterprise"],
    "pricing": ["Free", "Starter", "Growth", "Scale", "Enterprise"],
    "membership": ["Basic", "Silver", "Gold", "Platinum", "Diamond"],
    "loyalty": ["Bronze", "Silver", "Gold", "Platinum", "Diamond"],
    "risk": ["Very Low", "Low", "Moderate", "High", "Very High"],
    "income": ["Low", "Lower-Middle", "Middle", "Upper-Middle", "High"],
    "seniority": ["Junior", "Mid-Level", "Senior", "Staff", "Principal"],
}

GENERIC_TIERS = [
    "Bronze", "Silver", "Gold", "Platinum", "Diamond", "Elite",
]


# Vehicle make → real model names, so a vehicles table never pairs
# "Toyota" with a marketing sentence. Keys are lowercase makes.
VEHICLE_MODELS_BY_MAKE: Dict[str, List[str]] = {
    "toyota": ["Camry", "Corolla", "RAV4", "Highlander", "Prius", "Tacoma", "Sienna"],
    "honda": ["Civic", "Accord", "CR-V", "Pilot", "Odyssey", "HR-V", "Fit"],
    "ford": ["F-150", "Escape", "Explorer", "Fusion", "Mustang", "Edge", "Transit"],
    "chevrolet": ["Silverado", "Equinox", "Malibu", "Tahoe", "Traverse", "Bolt", "Impala"],
    "nissan": ["Altima", "Sentra", "Rogue", "Pathfinder", "Versa", "Murano", "Leaf"],
    "hyundai": ["Elantra", "Sonata", "Tucson", "Santa Fe", "Kona", "Palisade", "Ioniq 5"],
    "kia": ["K5", "Sorento", "Sportage", "Soul", "Telluride", "Forte", "Niro"],
    "volkswagen": ["Jetta", "Passat", "Tiguan", "Atlas", "Golf", "Taos", "ID.4"],
    "bmw": ["3 Series", "5 Series", "X3", "X5", "X1", "4 Series", "i4"],
    "mercedes-benz": ["C-Class", "E-Class", "GLC", "GLE", "A-Class", "S-Class", "EQE"],
    "audi": ["A4", "A6", "Q5", "Q7", "Q3", "A3", "e-tron"],
    "tesla": ["Model 3", "Model Y", "Model S", "Model X"],
    "subaru": ["Outback", "Forester", "Crosstrek", "Impreza", "Ascent", "Legacy"],
    "mazda": ["CX-5", "Mazda3", "CX-30", "CX-9", "Mazda6", "MX-5 Miata"],
    "jeep": ["Grand Cherokee", "Wrangler", "Cherokee", "Compass", "Renegade", "Gladiator"],
    "lexus": ["RX", "ES", "NX", "GX", "IS", "UX"],
    "dodge": ["Charger", "Challenger", "Durango", "Journey"],
    "gmc": ["Sierra", "Terrain", "Acadia", "Yukon", "Canyon"],
}


# Departments beyond the generic list — used when a column asks for one.
OFFICE_DEPARTMENTS = [
    "Engineering", "Sales", "Marketing", "Finance", "Human Resources",
    "Operations", "Customer Success", "Legal", "Product", "Design",
    "Data & Analytics", "IT", "Procurement", "Research & Development",
    "Quality Assurance", "Facilities", "Communications", "Security",
]


# ---------------------------------------------------------------------------
# Conditional sampling helpers
# ---------------------------------------------------------------------------


def sample_conditional(
    rng,
    parent_values,
    mapping: Dict[str, List[str]],
    fallback_key: str = "generic",
) -> list:
    """Vectorised conditional sample: for each parent value, pick from the matching pool.

    Parameters
    ----------
    rng:
        A ``numpy.random.Generator`` instance.
    parent_values:
        Iterable of parent column values (e.g. category names).
    mapping:
        Dict from parent value → list of child values to sample from.
    fallback_key:
        Key to use when parent value is not in mapping.
    """
    result = []
    fallback_pool = mapping.get(fallback_key, next(iter(mapping.values())))
    for val in parent_values:
        key = str(val).lower()
        pool = next(
            (v for k, v in mapping.items() if k.lower() in key or key in k.lower()),
            fallback_pool,
        )
        result.append(rng.choice(pool))
    return result


# ---------------------------------------------------------------------------
# Medical vocabularies (0.8.1.18) — clinical columns must never fall through
# to business filler (hospital field report: blood_type held sentences).
# ---------------------------------------------------------------------------

MEDICAL_DEPARTMENTS = [
    "Cardiology", "Oncology", "Neurology", "Pediatrics", "Orthopedics",
    "Emergency Medicine", "Radiology", "Obstetrics & Gynecology",
    "Internal Medicine", "Surgery", "Psychiatry", "Dermatology",
    "Urology", "Gastroenterology", "Pulmonology", "Nephrology",
    "Anesthesiology", "Intensive Care", "Pathology", "Ophthalmology",
]

MEDICAL_SPECIALTIES = [
    "Cardiologist", "Oncologist", "Neurologist", "Pediatrician",
    "Orthopedic Surgeon", "Emergency Physician", "Radiologist",
    "General Surgeon", "Psychiatrist", "Dermatologist", "Anesthesiologist",
    "Internist", "Family Medicine", "Gastroenterologist", "Pulmonologist",
    "Nephrologist", "Endocrinologist", "Urologist", "Obstetrician",
]

BLOOD_TYPES = ["O+", "A+", "B+", "AB+", "O-", "A-", "B-", "AB-"]
# Real-world US distribution (Stanford Blood Center).
BLOOD_TYPE_WEIGHTS = [0.374, 0.357, 0.085, 0.034, 0.066, 0.063, 0.015, 0.006]

ADMISSION_TYPES = [
    "Emergency", "Elective", "Urgent", "Transfer", "Observation",
    "Newborn", "Trauma", "Readmission",
]

DISCHARGE_STATUSES = [
    "Discharged Home", "Transferred", "Discharged to Rehab",
    "Left Against Medical Advice", "Deceased", "Still Admitted",
    "Discharged to Skilled Nursing",
]

COMMON_DIAGNOSES = [
    "Hypertension", "Type 2 Diabetes", "Pneumonia", "Acute Appendicitis",
    "Congestive Heart Failure", "COPD Exacerbation", "Urinary Tract Infection",
    "Atrial Fibrillation", "Acute Myocardial Infarction", "Sepsis",
    "Cellulitis", "Gastroenteritis", "Asthma Exacerbation", "Stroke",
    "Fracture of Femur", "Deep Vein Thrombosis", "Chronic Kidney Disease",
    "Migraine", "Anemia", "Hyperlipidemia",
]

LAB_TESTS = [
    "Complete Blood Count", "Basic Metabolic Panel", "Lipid Panel",
    "Hemoglobin A1c", "Thyroid Stimulating Hormone", "Liver Function Panel",
    "Urinalysis", "C-Reactive Protein", "Troponin I", "D-Dimer",
    "Blood Glucose", "Creatinine", "Potassium", "Vitamin D", "PT/INR",
]

LAB_UNITS = [
    "mg/dL", "mmol/L", "g/dL", "IU/L", "ng/mL", "mcg/dL", "mEq/L",
    "cells/mcL", "%", "U/L",
]

MEDICATIONS = [
    "Lisinopril", "Metformin", "Atorvastatin", "Amlodipine", "Omeprazole",
    "Levothyroxine", "Amoxicillin", "Azithromycin", "Metoprolol",
    "Losartan", "Gabapentin", "Hydrochlorothiazide", "Sertraline",
    "Albuterol", "Prednisone", "Insulin Glargine", "Warfarin",
    "Furosemide", "Pantoprazole", "Ceftriaxone",
]

DOSAGE_AMOUNTS = ["5 mg", "10 mg", "20 mg", "25 mg", "40 mg", "50 mg",
                  "100 mg", "250 mg", "500 mg", "850 mg", "1000 mg", "2.5 mg"]

MED_FREQUENCIES = [
    "Once daily", "Twice daily", "Three times daily", "Every 6 hours",
    "Every 8 hours", "Every 12 hours", "As needed", "At bedtime",
    "With meals", "Weekly",
]

# ---------------------------------------------------------------------------
# Enriched Textual Realism Pools (2026 Expansion)
# ---------------------------------------------------------------------------

RETURN_REASONS: List[str] = [
    "Defective or does not power on",
    "Item does not match website pictures or description",
    "Wrong size / fit too small",
    "Wrong size / fit too large",
    "Arrived damaged or broken in transit",
    "Missing key parts or accessories",
    "Arrived later than estimated delivery date",
    "Found better price from another merchant",
    "Ordered incorrect model or variant by mistake",
    "Changed mind / item no longer needed",
    "Poor build quality / materials felt cheap",
    "Incompatible with existing equipment",
]

CHURN_REASONS: List[str] = [
    "Switched to alternative competitor platform",
    "Budget cuts and company-wide software consolidation",
    "Missing critical integrations with internal tech stack",
    "Product complexity and steep learning curve for team",
    "Low internal user adoption and seat utilization",
    "Missing advanced reporting and audit export features",
    "Pricing tier too expensive for current volume",
    "Company acquired or undergoing operational restructuring",
    "Underlying project cancelled or business pivoted",
    "Dissatisfied with customer support response times",
    "Lack of custom API endpoints and webhook reliability",
    "Downsized team headcount; reduced licensing needs",
]

AUDIT_REASONS: List[str] = [
    "Quarterly SOC2 Type II compliance sampling",
    "Automated anomaly detection triggered security review",
    "Manual approval threshold override by department head",
    "Identity KYC verification mismatch on submitted documents",
    "High-value transaction flagged for AML review",
    "Role privilege escalation to superadmin verified",
    "Customer personal data erasure request under GDPR/CCPA",
    "Annual external financial statement reconciliation audit",
    "Multiple failed authentication attempts from untrusted IP",
    "Production database schema change authorization check",
    "Vendor risk assessment renewal and vendor compliance audit",
    "Routine credential rotation and inactive account deprovisioning",
]

TICKET_SUBJECTS: List[str] = [
    "Unable to authenticate via Okta SAML SSO",
    "Password reset email link expired immediately",
    "Session terminates unexpectedly after 5 minutes of inactivity",
    "MFA push notification not delivering to authenticator app",
    "Duplicate charge observed on monthly subscription invoice",
    "Need updated VAT invoice with corporate tax ID",
    "Credit card renewal payment failed with code 204",
    "Requesting credit memo for unused enterprise seats",
    "Webhook delivery failure returning HTTP 500 error",
    "Rate limit 429 errors encountered on /v2/orders endpoint",
    "Malformed JSON payload returned from batch export API",
    "API key regeneration caused temporary authorization outage",
    "CSV export generates empty file for selected date range",
    "Search filter parameters reset when navigating to page 2",
    "File upload fails silently for documents larger than 10MB",
    "Analytics dashboard charts fail to render in Safari",
    "Slow database query timeouts on customer overview table",
    "Scheduled email reports taking over 15 minutes to generate",
    "Intermittent 504 Gateway Timeout on checkout page",
    "Mobile app crashes during push notification tap",
    "Deleted team member still appearing in permission groups",
    "Discount promo code not applying discount at final step",
    "Need custom domain SSL certificate re-provisioned",
    "Slack integration bot stopped posting incident alerts",
    "Unable to edit shipping address after order confirmation",
]

RESOLUTION_NOTES: List[str] = [
    "Investigated root cause to an expired OAuth refresh token. Regenerated client credentials, verified successful sync, and confirmed resolution with customer.",
    "Identified database lock contention on invoice ledger table. Applied migration index and reprocessed stuck batch records successfully.",
    "Processed full refund of charge to customer's original payment method (AuthRef #83921). Updated billing cycle to prevent recurrence.",
    "Fixed CSS flexbox layout bug affecting Safari browser rendering. Tested across desktop and mobile, deployed hotfix to production.",
    "Flushed stale Redis cache cluster on proxy nodes. Verified p95 latency returned to baseline (<120ms) and closed incident.",
    "Customer updated billing address on file. Re-attempted payment authorization and transaction succeeded without further error.",
    "Updated role permissions in organization admin panel to grant analyst read access. Confirmed access restored.",
    "Re-queued 18 failed webhook events from dead-letter queue. Upstream receiver confirmed receipt of all payloads.",
    "Re-issued TLS certificate on custom edge domain. Validated SSL handshake across global edge locations.",
    "Identified malformed UTF-8 character in CSV ingestion stream. Added sanitizer pass to parser pipeline.",
    "Walked user through clearing browser session storage and re-authenticating with MFA hardware key.",
    "Adjusted rate limit tier from 60 req/min to 300 req/min for enterprise tier customer. Verified no further 429 errors.",
    "Escalated bug to mobile engineering team (ticket MOB-4912). Temporary workaround provided to customer.",
    "Replaced damaged hardware unit under standard warranty. Tracking number provided to customer.",
    "Restored accidentally archived project from point-in-time snapshot. Customer verified all records intact.",
]

TRANSACTION_MEMOS: List[str] = [
    "SQ *BLUE BOTTLE COFFEE SAN FRANCISCO CA",
    "AMZN MKTP US*8K9J21 AMZN.COM/BILL WA",
    "UBER *TRIP HELP.UBER.COM CA",
    "TARGET T-2418 MINNEAPOLIS MN",
    "STRIPE *GITHUB INC SAN FRANCISCO CA",
    "WHOLEFDS MKT 10294 AUSTIN TX",
    "APPLE.COM/BILL 866-712-7753 CA",
    "NETFLIX.COM 866-579-7172 CA",
    "SHELL OIL 574492019 DALLAS TX",
    "TRADER JOE'S #542 PASADENA CA",
    "STARBUCKS STORE 08492 SEATTLE WA",
    "DELTA AIR 00628391024 ATLANTA GA",
    "ACH DIRECT DEP ACME CORP PAYROLL",
    "WIRE OUT REF: 849201 ESCROW HOLDINGS",
    "BILL PAY UTILITIES ELECTRIC & GAS",
    "IRS TREAS 310 TAX REFUND",
    "ATM WITHDRAWAL #4820 1ST NATIONAL BANK",
    "ZELLE TRANSFER FROM J SMITH",
    "INTEREST PAYMENT - CHECKING ACCT",
    "WAL-MART #1582 BENTONVILLE AR",
    "CVS PHARMACY #0492 BOSTON MA",
    "LYFT *RIDE 09-24 SAN FRANCISCO CA",
    "AWS EMEA AWS.AMAZON.CO LU",
    "GOOGLE *CLOUD_01824 MOUNTAIN VIEW CA",
    "COSTCO WHSE #0482 ISSAQUAH WA",
    "HOME DEPOT #6812 ATLANTA GA",
    "FEDEX 794820198421 MEMPHIS TN",
    "USPS POST OFFICE 02138 CAMBRIDGE MA",
]

SYSTEM_ERROR_MESSAGES: List[str] = [
    "ConnectionRefusedError: Connection to db-primary.internal:5432 timed out after 30000ms",
    "HTTP 401 Unauthorized: Authorization header missing or bearer token expired",
    "HTTP 403 Forbidden: Insufficient permissions to access resource 'organizations/org_4921/billing'",
    "HTTP 404 Not Found: Resource '/api/v1/workspaces/ws_9812/members' does not exist",
    "HTTP 429 Too Many Requests: Rate limit exceeded (limit: 120 req/min, current: 168)",
    "HTTP 502 Bad Gateway: Upstream service 'auth-worker-02' unreachable or unhealthy",
    "HTTP 504 Gateway Timeout: Upstream server took longer than 60.0s to respond",
    "PayloadTooLargeError: Request body size 15.4MB exceeds maximum allowed size of 10.0MB",
    "IntegrityError: Duplicate key value violates unique constraint 'idx_accounts_subdomain'",
    "InvalidSignature: HMAC-SHA256 signature verification failed for incoming webhook payload",
    "StripeCardError: Your card was declined due to insufficient funds (code: card_declined)",
    "S3StorageError: AccessDenied on bucket 'prod-analytics-exports' for key 'export_491.csv'",
    "DeadlockDetected: Transaction (Process 4921) was deadlocked on lock resources with process 4928",
    "ValidationError: Field 'shipping_postal_code' failed regex format '^\\d{5}(-\\d{4})?$' for country 'US'",
    "JSONDecodeError: Expecting ',' delimiter: line 14 column 28 (char 412)",
    "CircuitBreakerOpenException: Service 'payment-gateway-eu' circuit breaker open due to high failure rate",
    "OutOfMemoryError: Java heap space during batch transformation in SparkExecutor-04",
    "KafkaProduceError: RecordBatch expired before acknowledgment from broker 10.0.12.4:9092",
    "DNSTimeoutException: Failed to resolve hostname 'api.partner-vendor.com' within 5000ms",
]

CHIEF_COMPLAINTS: List[str] = [
    "Patient presents with persistent cough, mild wheezing, and low-grade fever for 4 days.",
    "Complains of sharp lower right quadrant abdominal pain starting 12 hours ago, rated 7/10.",
    "Follow-up consultation for type 2 diabetes management and blood glucose log review.",
    "Severe throbbing unilateral headache with photophobia and nausea lasting 36 hours.",
    "Routine annual physical examination and preventative lipid panel screening.",
    "Complains of gradual bilateral knee stiffness and pain aggravated by climbing stairs.",
    "Post-operative check following laparoscopic cholecystectomy 10 days ago. Incisions healing well.",
    "Presents with acute lower back pain radiating down left leg following heavy lifting.",
    "Complains of progressive fatigue, shortness of breath on mild exertion, and dizziness.",
    "Follow-up for essential hypertension with recent home blood pressure readings averaging 148/92.",
    "Presents with pruritic erythematous rash across bilateral forearms following outdoor gardening.",
    "Complains of sore throat, difficulty swallowing, and cervical lymphadenopathy for 3 days.",
]

DISCHARGE_INSTRUCTIONS: List[str] = [
    "Continue prescribed antibiotic course for full 7 days even if symptoms resolve completely. Take with food.",
    "Avoid vigorous physical activity, heavy lifting (>10 lbs), and strenuous exercise for the next 2 weeks.",
    "Follow low-sodium, heart-healthy dietary guidelines and log daily morning blood pressure readings.",
    "Schedule follow-up visit with primary care physician in 14 days for incision check and lab review.",
    "Seek immediate emergency medical attention if temperature exceeds 101.5F, severe shortness of breath, or chest pain occurs.",
    "Keep dressing clean and dry. May shower after 48 hours; do not submerge wound in bath or pool.",
    "Resume regular home medications tomorrow morning. Discontinue temporary anticoagulant as previously directed.",
    "Elevate affected extremity above heart level when resting to reduce peripheral edema.",
    "Drink plenty of oral fluids (at least 2 liters daily) and maintain light walking as tolerated.",
    "Return to clinic immediately if redness, increased swelling, or purulent drainage develops around wound site.",
]

CLINICAL_NOTES: List[str] = [
    "Patient alert and oriented x3. Vital signs stable within normal limits. Lungs clear to auscultation bilaterally. Heart regular rate and rhythm without murmurs. Plan: continue current medical regimen, repeat labs in 3 months.",
    "Physical exam reveals mild tenderness in right upper quadrant without rebound or guarding. Bowel sounds present. Laboratory evaluation unremarkable. Patient advised on dietary modifications and symptom monitoring.",
    "Neurological examination intact. Cranial nerves II-XII grossly normal. Deep tendon reflexes 2+ symmetrical. Gait steady. Prescribed triptan therapy for acute migraine episodes and counseled on trigger avoidance.",
    "Bilateral breath sounds clear. No wheezes, rales, or rhonchi. Oxygen saturation 98% on room air. Peak flow improved post-nebulizer treatment. Inhaler technique reviewed and reinforced.",
    "Surgical incision sites clean, intact, with no erythema, warmth, or purulent exudate. Sutures removed without complication. Healing appropriately for postoperative day 10.",
    "Cardiovascular exam: S1 and S2 audible, no S3/S4. Peripheral pulses 2+ bilaterally, no lower extremity edema. EKG demonstrates normal sinus rhythm. Adjusted antihypertensive dosing with 4-week follow-up.",
    "Skin exam reveals well-demarcated maculopapular rash on bilateral arms. No mucosal involvement. Topical corticosteroid prescribed with instructions for twice daily application for 7 days.",
    "Musculoskeletal exam shows restricted range of motion of lumbar spine with paraspinal muscle spasm. Straight leg raise negative bilaterally. Initiated physical therapy referral and short course of NSAIDs.",
]

DELIVERY_INSTRUCTIONS: List[str] = [
    "Please leave the package on the front porch behind the decorative planter.",
    "Building gate code is #4921. Take elevator to 3rd floor and leave outside unit 304.",
    "Please ring doorbell upon delivery. Do not leave unattended in the lobby.",
    "Deliver to front reception desk between 9:00 AM and 5:00 PM on weekdays only.",
    "Side door entrance near driveway. Please do not block the garage door.",
    "Beware of friendly dog in the fenced yard. Gate latch is on the inside.",
    "Leave package inside the screened porch. No signature required.",
    "Package contains fragile items; please handle with care and keep upright.",
    "Drop off at package locker room in building basement; notify resident via app.",
    "If no one answers, please leave behind the pillar next to the entryway.",
    "Security guard at main entrance will accept packages and sign on resident's behalf.",
    "Please knock firmly on front door before leaving package on doormat.",
]

CUSTOMER_FEEDBACK: List[str] = [
    "The user interface is remarkably clean and intuitive. Onboarding our 15-person team took under an hour.",
    "Customer support resolved my billing issue within 20 minutes on live chat. Truly impressive service.",
    "Solid core functionality, though the mobile web experience has noticeable performance lag on larger datasets.",
    "The automated reporting saves our analytics team roughly 4 hours every Monday morning. Worth every penny.",
    "Documentation could use more real-world code examples for custom webhook payload handling.",
    "A great value compared to enterprise competitors that charge 3x more for nearly identical features.",
    "Very pleased with the speed of data exports and the accuracy of the underlying analytics models.",
    "Setup was smooth, but configuring fine-grained permissions for guest users felt slightly unintuitive.",
    "Reliable platform that has maintained 100% uptime for our team throughout the last two quarters.",
    "Would love to see direct integrations with Slack and Notion on the upcoming product roadmap.",
    "The product exceeded our expectations during our 14-day trial period; upgrading to enterprise was an easy decision.",
    "Clean design, responsive customer care, and thoughtful feature updates rolled out every two weeks.",
]

PRODUCT_DESCRIPTIONS_BY_CATEGORY: Dict[str, List[str]] = {
    "electronics": [
        "Features high-performance active noise cancellation with up to 30 hours of battery life on a single charge. Engineered with aerospace-grade aluminum and sweat-resistant nanocoating for premium daily use.",
        "Equipped with ultra-low latency wireless connectivity, rapid USB-C fast charging, and custom-tuned neodymium acoustic drivers for immersive high-fidelity audio.",
        "Compact and lightweight design with high-resolution OLED display, intuitive touch controls, and seamless multi-device Bluetooth 5.3 pairing across phone, tablet, and laptop.",
        "Engineered for creators and power users with dual thunderbolt ports, efficient thermal cooling architecture, and an anodized aluminum chassis built to endure heavy workloads.",
        "Smart intelligent sensors automatically adjust settings in real time, delivering optimal energy efficiency and effortless everyday convenience.",
    ],
    "clothing": [
        "Crafted from 100% certified organic combed cotton with reinforced double-needle stitching for lasting durability. Features a tailored athletic fit with breathable all-day comfort.",
        "Engineered with 4-way stretch moisture-wicking fabric and an anti-chafing flatlock seam construction. Designed for peak athletic performance and everyday casual wear.",
        "Timeless relaxed silhouette cut from premium heavyweight French terry. Pre-shrunk fabric ensures shape retention through repeated machine washes.",
        "Weatherproof outer shell with breathable micro-porous membrane and lightweight thermal insulation. Keeps you dry and comfortable across changing seasons.",
        "Versatile modern wardrobe staple tailored for effortless layering from workday commutes to casual weekend outings.",
    ],
    "home": [
        "Manufactured from professional-grade 18/10 stainless steel with an encapsulated aluminum core for rapid, even heat distribution. Ergonomic stay-cool handles ensure secure handling.",
        "Space-saving modular design with durable BPA-free silicone components. Dishwasher safe, microwave safe, and engineered for effortless everyday food prep.",
        "Crafted from sustainable solid acacia wood with a food-safe mineral oil finish. Naturally antimicrobial and gentle on fine cutlery edges.",
        "Energy-efficient modern design that blends seamlessly into any contemporary living space while providing quiet, dependable performance.",
        "Heavy-duty construction engineered to withstand daily family use, backed by a comprehensive 5-year manufacturer warranty.",
    ],
    "beauty": [
        "Formulated with pure botanical hyaluronic acid, vitamin C, and organic cold-pressed jojoba oil. Delivers deep, non-greasy hydration suitable for all skin types.",
        "Dermatologist-tested, fragrance-free formula clinically proven to restore moisture barrier resilience within 48 hours. 100% cruelty-free and vegan.",
        "Nourishing antioxidant-rich botanical complex that revitalizes dull skin, promoting a healthy radiant glow without clogging pores.",
        "Gentle everyday cleanser that effectively removes impurities and makeup while maintaining the skin's natural pH and lipid balance.",
    ],
    "industrial": [
        "Heavy-duty alloy steel construction with rust-resistant powder-coat finish, rated for loads up to 500 lbs. Includes precision hardware and clear step-by-step assembly guide.",
        "Commercial-grade ergonomic design with adjustable lumbar support, 3D armrests, and breathable high-tensile mesh backrest for all-day seated comfort.",
        "Precision-machined tolerances with corrosion-resistant zinc plating, engineered to meet strict industrial safety and performance standards.",
    ],
    "software": [
        "Enterprise-grade cloud platform featuring automated role-based access control, SOC2 compliance, and sub-second query latency across distributed datasets.",
        "Developer-friendly REST and GraphQL APIs with comprehensive webhook event streaming, automated schema migrations, and 99.99% guaranteed uptime SLA.",
        "Intuitive collaborative workspace designed to streamline cross-functional workflows, automate repetitive tasks, and provide actionable real-time insights.",
    ],
    "generic": [
        "Designed for everyday reliability with premium materials, thoughtful ergonomics, and long-term durability.",
        "Engineered to deliver exceptional performance and lasting value, backed by a comprehensive satisfaction guarantee.",
        "Combines modern aesthetics with practical versatility, crafted to integrate effortlessly into your daily routine.",
        "Built to rigorous quality standards with customer-tested functionality and dependable day-in, day-out reliability.",
    ],
}

STREET_NAMES: List[str] = [
    "Main", "Oak", "Maple", "Cedar", "Sunset", "Lake", "Peachtree", "Lexington",
    "Michigan", "Market", "Oak Ridge", "Pinecrest", "Grand", "Broadway", "Elmwood",
    "Montgomery", "Washington", "Jefferson", "Lincoln", "Madison", "Park", "Highland",
    "Fairview", "Maplewood", "Willow", "Spring", "Valley", "River", "Chestnut",
    "Walnut", "Pine", "Beacon", "Commonwealth", "Mission", "Folsom", "Kearny",
    "Piedmont", "Canal", "Hudson", "Greenwich", "Bleecker", "Houston", "Crosby",
    "Mercer", "Franklin", "Lafayette", "Vanderbilt", "Madison", "Park Avenue",
    "Columbus", "Amsterdam", "Claremont", "Riverside", "West End", "Central",
    "Industrial", "Commerce", "Technology", "Innovation", "Enterprise", "Corporate",
]

SECONDARY_UNITS: List[str] = [
    "Apt 2B", "Apt 4F", "Apt 101", "Apt 304", "Apt 512",
    "Suite 100", "Suite 200", "Suite 350", "Suite 400", "Suite 520",
    "Unit 12", "Unit 24", "Unit 108", "Unit 205", "Unit 310",
    "Floor 2", "Floor 3", "Floor 4", "Floor 5",
    "Bldg A", "Bldg B", "Bldg 3", "Ste 150", "Ste 250",
]

