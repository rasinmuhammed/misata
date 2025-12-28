"""
Pure Python text generators for Misata.

Replaces Mimesis with lightweight, built-in generators using curated data pools.
No external dependencies required.
"""

import random
import string
from typing import Dict, List, Optional

# ============================================
# DATA POOLS
# ============================================

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Christopher", "Karen", "Charles", "Lisa", "Daniel", "Nancy",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle",
    "Kenneth", "Dorothy", "Kevin", "Carol", "Brian", "Amanda", "George", "Melissa",
    "Timothy", "Deborah", "Ronald", "Stephanie", "Edward", "Rebecca", "Jason", "Sharon",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill",
    "Flores", "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell",
]

EMAIL_DOMAINS = [
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com",
    "protonmail.com", "mail.com", "aol.com", "zoho.com", "fastmail.com",
]

COMPANY_NAMES = [
    "Acme Corp", "Globex", "Initech", "Umbrella Corp", "Stark Industries",
    "Wayne Enterprises", "Cyberdyne Systems", "Soylent Corp", "Massive Dynamic",
    "Aperture Science", "InGen", "Tyrell Corporation", "Weyland-Yutani", "OsCorp",
    "LexCorp", "Oscorp Industries", "Dharma Initiative", "Dunder Mifflin",
    "Sterling Cooper", "Wonka Industries", "Prestige Worldwide", "Vandelay Industries",
]

STREET_NAMES = [
    "Main", "Oak", "Maple", "Cedar", "Elm", "Pine", "Washington", "Lake",
    "Hill", "Park", "River", "Sunset", "Highland", "Valley", "Forest", "Spring",
]

STREET_SUFFIXES = ["St", "Ave", "Blvd", "Dr", "Ln", "Rd", "Way", "Ct", "Pl", "Cir"]

CITIES = [
    "New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia",
    "San Antonio", "San Diego", "Dallas", "San Jose", "Austin", "Jacksonville",
    "Fort Worth", "Columbus", "Charlotte", "Seattle", "Denver", "Boston",
]

STATES = [
    "NY", "CA", "TX", "FL", "IL", "PA", "OH", "GA", "NC", "MI",
    "NJ", "VA", "WA", "AZ", "MA", "CO", "TN", "IN", "MO", "MD",
]

LOREM_WORDS = [
    "lorem", "ipsum", "dolor", "sit", "amet", "consectetur", "adipiscing", "elit",
    "sed", "do", "eiusmod", "tempor", "incididunt", "ut", "labore", "et", "dolore",
    "magna", "aliqua", "enim", "ad", "minim", "veniam", "quis", "nostrud",
    "exercitation", "ullamco", "laboris", "nisi", "aliquip", "ex", "ea", "commodo",
]

URLS = [
    "https://example.com", "https://test.org", "https://demo.io", "https://sample.net",
]


# ============================================
# GENERATOR CLASS
# ============================================

class TextGenerator:
    """
    Pure Python text generator for synthetic data.

    Drop-in replacement for Mimesis functionality.
    Supports expandable data pools that can grow over time.
    """

    # Class-level pools (shared across instances, can be extended)
    _pools = {
        "first_names": list(FIRST_NAMES),
        "last_names": list(LAST_NAMES),
        "email_domains": list(EMAIL_DOMAINS),
        "company_names": list(COMPANY_NAMES),
        "street_names": list(STREET_NAMES),
        "cities": list(CITIES),
        "states": list(STATES),
        "lorem_words": list(LOREM_WORDS),
    }

    def __init__(self, seed: Optional[int] = None):
        """Initialize with optional random seed."""
        self.rng = random.Random(seed)

    @classmethod
    def extend_pool(cls, pool_name: str, values: List[str]) -> int:
        """
        Extend a data pool with new values.

        Args:
            pool_name: Name of pool (first_names, last_names, etc.)
            values: List of new values to add

        Returns:
            New pool size
        """
        if pool_name not in cls._pools:
            cls._pools[pool_name] = []

        # Add only unique values
        existing = set(cls._pools[pool_name])
        new_values = [v for v in values if v not in existing]
        cls._pools[pool_name].extend(new_values)

        return len(cls._pools[pool_name])

    @classmethod
    def load_pools_from_file(cls, filepath: str) -> Dict[str, int]:
        """
        Load and extend pools from a JSON file.

        Args:
            filepath: Path to JSON file with pool data

        Returns:
            Dict of pool names to their new sizes
        """
        import json
        with open(filepath, 'r') as f:
            data = json.load(f)

        sizes = {}
        for pool_name, values in data.items():
            if isinstance(values, list):
                sizes[pool_name] = cls.extend_pool(pool_name, values)

        return sizes

    @classmethod
    def save_pools_to_file(cls, filepath: str) -> None:
        """
        Save current pools to a JSON file.

        Args:
            filepath: Path to save JSON file
        """
        import json
        with open(filepath, 'w') as f:
            json.dump(cls._pools, f, indent=2)

    @classmethod
    def get_pool_sizes(cls) -> Dict[str, int]:
        """Get sizes of all pools."""
        return {name: len(values) for name, values in cls._pools.items()}

    def name(self) -> str:
        """Generate a full name."""
        first = self.rng.choice(self._pools["first_names"])
        last = self.rng.choice(self._pools["last_names"])
        return f"{first} {last}"

    def first_name(self) -> str:
        """Generate a first name."""
        return self.rng.choice(self._pools["first_names"])

    def last_name(self) -> str:
        """Generate a last name."""
        return self.rng.choice(self._pools["last_names"])

    def email(self) -> str:
        """Generate an email address."""
        first = self.rng.choice(self._pools["first_names"]).lower()
        last = self.rng.choice(self._pools["last_names"]).lower()
        domain = self.rng.choice(self._pools["email_domains"])
        separator = self.rng.choice([".", "_", ""])
        num = self.rng.randint(1, 99) if self.rng.random() > 0.5 else ""
        return f"{first}{separator}{last}{num}@{domain}"

    def company(self) -> str:
        """Generate a company name."""
        return self.rng.choice(self._pools["company_names"])

    def address(self) -> str:
        """Generate a street address."""
        number = self.rng.randint(1, 9999)
        street = self.rng.choice(self._pools["street_names"])
        suffix = self.rng.choice(STREET_SUFFIXES)
        return f"{number} {street} {suffix}"

    def full_address(self) -> str:
        """Generate a full address with city, state, zip."""
        addr = self.address()
        city = self.rng.choice(self._pools["cities"])
        state = self.rng.choice(self._pools["states"])
        zipcode = self.rng.randint(10000, 99999)
        return f"{addr}, {city}, {state} {zipcode}"

    def phone_number(self) -> str:
        """Generate a phone number."""
        area = self.rng.randint(200, 999)
        prefix = self.rng.randint(200, 999)
        line = self.rng.randint(1000, 9999)
        return f"({area}) {prefix}-{line}"

    def url(self) -> str:
        """Generate a URL."""
        base = self.rng.choice(URLS)
        path = ''.join(self.rng.choices(string.ascii_lowercase, k=8))
        return f"{base}/{path}"

    def sentence(self, words: int = 8) -> str:
        """Generate a lorem ipsum sentence."""
        selected = [self.rng.choice(self._pools["lorem_words"]) for _ in range(words)]
        selected[0] = selected[0].capitalize()
        return ' '.join(selected) + '.'

    def word(self) -> str:
        """Generate a single word."""
        return self.rng.choice(self._pools["lorem_words"])

    def text(self, sentences: int = 3) -> str:
        """Generate a paragraph of text."""
        return ' '.join(self.sentence() for _ in range(sentences))

    def uuid(self) -> str:
        """Generate a UUID-like string."""
        hex_chars = '0123456789abcdef'
        parts = [
            ''.join(self.rng.choices(hex_chars, k=8)),
            ''.join(self.rng.choices(hex_chars, k=4)),
            ''.join(self.rng.choices(hex_chars, k=4)),
            ''.join(self.rng.choices(hex_chars, k=4)),
            ''.join(self.rng.choices(hex_chars, k=12)),
        ]
        return '-'.join(parts)

