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
        "Acme Retail", "BlueLine Store", "CrestShop", "DeltaMart",
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
}

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
