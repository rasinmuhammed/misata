"""
Joint person-identity sampling: (culture, gender, first, last) as one draw.

The #1 "fake data" tell in generated people is independence between fields
that are strongly dependent in the real world:

  - first name and gender        ("Pablo, Female")
  - first name and last name     ("Wei Gonzalez", "Yuki Zhang")
  - name and email               (handled downstream in realism.py)

This module fixes the first two with a hierarchical joint model:

    culture ~ Categorical(mix)              # population mixture
    gender  ~ Bernoulli(p_female)           # or conditioned on a gender column
    first   ~ Pool[culture][gender]
    last    ~ Pool[culture]  (with a small cross-culture intermix probability,
                              because real populations are not endogamous)

Everything is seeded and vectorised. Reverse lookup tables (NAME_GENDER,
NAME_CULTURE) let post-generation realism rules repair rows where a
schema-declared ``gender`` column disagrees with the sampled name, without
disturbing the declared gender distribution.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Culture-keyed gendered name pools.
#
# Sources: US Census Bureau frequency tables (public domain), public-domain
# national name registries, manual curation. Pools are intentionally
# culture-pure: cross-culture surnames are introduced by the sampler's
# intermix step (measured, not accidental).
# ---------------------------------------------------------------------------

CULTURE_POOLS: Dict[str, Dict[str, List[str]]] = {
    "anglo": {
        "male": [
            "James", "John", "Robert", "Michael", "William", "David", "Richard",
            "Joseph", "Thomas", "Charles", "Christopher", "Daniel", "Matthew",
            "Anthony", "Donald", "Mark", "Paul", "Steven", "Andrew", "Kenneth",
            "George", "Joshua", "Kevin", "Brian", "Edward", "Ronald", "Timothy",
            "Jason", "Jeffrey", "Ryan", "Liam", "Noah", "Oliver", "Elijah",
            "Ethan", "Mason", "Aiden", "Lucas", "Henry", "Jack", "Owen", "Caleb",
        ],
        "female": [
            "Mary", "Patricia", "Jennifer", "Linda", "Barbara", "Elizabeth",
            "Susan", "Jessica", "Sarah", "Karen", "Lisa", "Nancy", "Betty",
            "Margaret", "Sandra", "Ashley", "Dorothy", "Kimberly", "Emily",
            "Donna", "Michelle", "Carol", "Amanda", "Melissa", "Deborah",
            "Stephanie", "Rebecca", "Sharon", "Laura", "Emma", "Olivia", "Ava",
            "Sophia", "Mia", "Charlotte", "Amelia", "Harper", "Evelyn", "Abigail",
            "Grace", "Chloe", "Hannah",
        ],
        "last": [
            "Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis",
            "Wilson", "Anderson", "Taylor", "Thomas", "Jackson", "White",
            "Harris", "Martin", "Thompson", "Young", "Robinson", "Lewis",
            "Walker", "Hall", "Allen", "Wright", "Scott", "Green", "Adams",
            "Baker", "Nelson", "Carter", "Mitchell", "Roberts", "Turner",
            "Phillips", "Campbell", "Parker", "Evans", "Collins", "Edwards",
            "Stewart", "Morris", "Rogers", "Reed", "Cook", "Morgan", "Bell",
            "Murphy", "Bailey", "Cooper", "Richardson", "Cox", "Howard", "Ward",
        ],
    },
    "south_asian": {
        "male": [
            "Arjun", "Rahul", "Vikram", "Rohan", "Aditya", "Sanjay", "Amit",
            "Ravi", "Suresh", "Kiran", "Rajesh", "Anil", "Vijay", "Deepak",
            "Manoj", "Arun", "Nikhil", "Varun", "Karthik", "Pranav", "Ashok",
            "Harish", "Ramesh", "Dinesh", "Gaurav",
        ],
        "female": [
            "Priya", "Ananya", "Kavya", "Deepa", "Sneha", "Pooja", "Neha",
            "Divya", "Nisha", "Meera", "Anjali", "Shreya", "Aishwarya", "Lakshmi",
            "Sunita", "Ritu", "Swati", "Pallavi", "Anita", "Rekha", "Sita",
            "Radha", "Aarti", "Vidya", "Smita",
        ],
        "last": [
            "Patel", "Singh", "Kumar", "Sharma", "Gupta", "Shah", "Mehta",
            "Joshi", "Desai", "Chopra", "Nair", "Iyer", "Reddy", "Rao", "Verma",
            "Malhotra", "Kapoor", "Banerjee", "Chatterjee", "Mukherjee", "Das",
            "Bose", "Menon", "Pillai", "Agarwal", "Bhat", "Hegde", "Kulkarni",
        ],
    },
    "chinese": {
        "male": [
            "Wei", "Ming", "Jian", "Hao", "Lei", "Feng", "Jun", "Bo", "Tao",
            "Cheng", "Long", "Peng", "Kai", "Yong", "Gang", "Bin", "Xin", "Chao",
        ],
        "female": [
            "Fang", "Jing", "Xiao", "Ying", "Hui", "Yan", "Li", "Mei", "Lin",
            "Na", "Xia", "Juan", "Yun", "Lan", "Hong", "Qing", "Shu", "Zhen",
        ],
        "last": [
            "Chen", "Wang", "Li", "Zhang", "Liu", "Yang", "Huang", "Wu", "Zhao",
            "Sun", "Zhou", "Xu", "Hu", "Zhu", "Gao", "Lin", "He", "Guo", "Ma",
            "Luo", "Liang", "Song", "Zheng", "Xie", "Tang", "Han", "Cao", "Deng",
        ],
    },
    "japanese": {
        "male": [
            "Kenji", "Takeshi", "Ryo", "Hiroshi", "Daiki", "Yuto", "Sota",
            "Haruto", "Kaito", "Ren", "Shota", "Kazuki", "Takumi", "Yuya",
        ],
        "female": [
            "Yuki", "Hana", "Sakura", "Aiko", "Nao", "Yui", "Rin", "Mio",
            "Akari", "Misaki", "Honoka", "Ayumi", "Kanon", "Emi",
        ],
        "last": [
            "Tanaka", "Suzuki", "Sato", "Yamamoto", "Kobayashi", "Watanabe",
            "Ito", "Nakamura", "Takahashi", "Kato", "Yoshida", "Yamada",
            "Sasaki", "Matsumoto", "Inoue", "Kimura", "Shimizu", "Hayashi",
        ],
    },
    "korean": {
        "male": [
            "Min-jun", "Seo-jun", "Do-yun", "Ji-ho", "Joon-woo", "Hyun-woo",
            "Ji-hoon", "Sung-min", "Dong-hyun", "Tae-yang", "Jae-won", "Woo-jin",
        ],
        "female": [
            "Seo-yeon", "Ji-woo", "Ha-eun", "Soo-ah", "Ye-jin", "Min-seo",
            "Chae-won", "Yu-na", "Eun-ji", "Hye-jin", "Da-eun", "So-yeon",
        ],
        "last": [
            "Kim", "Lee", "Park", "Choi", "Jung", "Kang", "Cho", "Yoon", "Jang",
            "Lim", "Han", "Shin", "Oh", "Seo", "Kwon", "Hwang", "Ahn", "Song",
        ],
    },
    "hispanic": {
        "male": [
            "Santiago", "Mateo", "Sebastian", "Diego", "Alejandro", "Andres",
            "Carlos", "Luis", "Miguel", "Pablo", "Ricardo", "Javier", "Fernando",
            "Jorge", "Eduardo", "Raul", "Manuel", "Francisco", "Antonio", "Pedro",
            "Hector", "Oscar", "Cesar", "Ruben",
        ],
        "female": [
            "Sofia", "Valentina", "Camila", "Isabella", "Lucia", "Gabriela",
            "Mariana", "Daniela", "Carmen", "Elena", "Adriana", "Paula",
            "Veronica", "Claudia", "Patricia", "Rosa", "Marisol", "Beatriz",
            "Catalina", "Ines", "Alejandra", "Teresa", "Pilar", "Juana",
        ],
        "last": [
            "Garcia", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
            "Sanchez", "Perez", "Ramirez", "Torres", "Flores", "Rivera", "Gomez",
            "Diaz", "Reyes", "Cruz", "Morales", "Ortiz", "Gutierrez", "Chavez",
            "Ramos", "Ruiz", "Alvarez", "Mendoza", "Vasquez", "Castillo",
            "Jimenez", "Moreno", "Romero", "Herrera", "Medina", "Aguilar",
        ],
    },
    "african": {
        "male": [
            "Kwame", "Kofi", "Jabari", "Darius", "Malik", "Tyrone", "DeShawn",
            "Chidi", "Emeka", "Sekou", "Amadou", "Tunde", "Femi", "Obi",
            "Mamadou", "Ousmane", "Kojo", "Yaw",
        ],
        "female": [
            "Aisha", "Amara", "Zara", "Imani", "Nia", "Simone", "Aaliyah",
            "Chioma", "Ngozi", "Adaeze", "Fatou", "Aminata", "Abena", "Akosua",
            "Folake", "Zainab", "Kemi", "Ama",
        ],
        "last": [
            "Okafor", "Mensah", "Diallo", "Traore", "Okeke", "Eze", "Nwosu",
            "Adeyemi", "Okonkwo", "Asante", "Boateng", "Owusu", "Kone", "Toure",
            "Cisse", "Ndiaye", "Sow", "Camara", "Keita", "Sane",
        ],
    },
    "middle_eastern": {
        "male": [
            "Omar", "Khalid", "Hassan", "Ibrahim", "Yousef", "Tariq", "Zaid",
            "Ali", "Ahmed", "Mohammed", "Mustafa", "Karim", "Samir", "Faisal",
            "Nasser", "Rashid", "Bilal", "Hamza",
        ],
        "female": [
            "Layla", "Yasmin", "Nour", "Rania", "Fatima", "Amira", "Salma",
            "Dina", "Hana", "Lina", "Maryam", "Zahra", "Huda", "Samira",
            "Leila", "Nadia", "Farah", "Aya",
        ],
        "last": [
            "Ibrahim", "Hassan", "Ali", "Ahmed", "Khalil", "Saleh", "Mansour",
            "Haddad", "Nasser", "Karim", "Aziz", "Rahman", "Farah", "Hamdan",
            "Khoury", "Najjar", "Sayegh", "Awad", "Said", "Yousef",
        ],
    },
    "german": {
        "male": [
            "Lukas", "Felix", "Jonas", "Maximilian", "Leon", "Niklas", "Florian",
            "Tobias", "Sebastian", "Stefan", "Matthias", "Andreas", "Markus",
            "Klaus", "Jurgen", "Wolfgang",
        ],
        "female": [
            "Anna", "Lena", "Hannah", "Laura", "Julia", "Katharina", "Sabine",
            "Petra", "Monika", "Claudia", "Birgit", "Ingrid", "Heike", "Ute",
            "Franziska", "Marlene",
        ],
        "last": [
            "Müller", "Schmidt", "Weber", "Fischer", "Becker", "Hoffmann",
            "Koch", "Wagner", "Schulz", "Bauer", "Richter", "Klein", "Wolf",
            "Schröder", "Neumann", "Schwarz", "Zimmermann", "Braun", "Krüger",
            "Hofmann", "Lange", "Schmitt", "Werner", "Meyer", "Jung",
        ],
    },
    "french": {
        "male": [
            "Louis", "Gabriel", "Arthur", "Jules", "Hugo", "Lucas", "Theo",
            "Antoine", "Nicolas", "Pierre", "Julien", "Mathieu", "Olivier",
            "Laurent", "Pascal", "Thierry",
        ],
        "female": [
            "Emma", "Jade", "Louise", "Alice", "Lea", "Manon", "Camille",
            "Juliette", "Marion", "Claire", "Sophie", "Isabelle", "Nathalie",
            "Celine", "Aurelie", "Margaux",
        ],
        "last": [
            "Dubois", "Leroy", "Martin", "Bernard", "Petit", "Durand", "Moreau",
            "Laurent", "Simon", "Michel", "Lefebvre", "Garcia", "Roux",
            "Fournier", "Morel", "Girard", "Mercier", "Blanc", "Faure", "Andre",
        ],
    },
    "italian": {
        "male": [
            "Leonardo", "Francesco", "Alessandro", "Lorenzo", "Matteo", "Andrea",
            "Gabriele", "Riccardo", "Marco", "Giuseppe", "Antonio", "Giovanni",
            "Luca", "Davide", "Stefano", "Paolo",
        ],
        "female": [
            "Giulia", "Aurora", "Alice", "Ginevra", "Emma", "Giorgia", "Greta",
            "Beatrice", "Anna", "Vittoria", "Francesca", "Chiara", "Sara",
            "Martina", "Elisa", "Valentina",
        ],
        "last": [
            "Rossi", "Ferrari", "Esposito", "Romano", "Russo", "Colombo",
            "Ricci", "Marino", "Greco", "Bruno", "Gallo", "Conti", "DeLuca",
            "Mancini", "Costa", "Giordano", "Rizzo", "Lombardi", "Moretti",
            "Barbieri",
        ],
    },
}

# Default population mixture — global-tech-workforce flavoured, US-skewed.
# Overridable per schema via realism config (``name_culture_mix``).
DEFAULT_CULTURE_MIX: Dict[str, float] = {
    "anglo": 0.38,
    "hispanic": 0.14,
    "south_asian": 0.11,
    "chinese": 0.07,
    "african": 0.07,
    "middle_eastern": 0.06,
    "german": 0.05,
    "french": 0.04,
    "italian": 0.04,
    "korean": 0.02,
    "japanese": 0.02,
}

# Probability that a person's surname comes from a different culture than
# their first name (marriage, migration, mixed heritage). Real datasets are
# not endogamous; a small intermix rate is MORE realistic than zero.
INTERMIX_RATE = 0.06

# ---------------------------------------------------------------------------
# Reverse lookups for post-generation repair rules
# ---------------------------------------------------------------------------

NAME_GENDER: Dict[str, str] = {}
NAME_CULTURE: Dict[str, str] = {}
for _culture, _pools in CULTURE_POOLS.items():
    for _gender in ("male", "female"):
        for _n in _pools[_gender]:
            # First writer wins; ambiguous names (e.g. "Emma" in anglo+french)
            # keep their first culture, which is fine for repair purposes.
            NAME_GENDER.setdefault(_n, _gender)
            NAME_CULTURE.setdefault(_n, _culture)

LAST_NAME_CULTURE: Dict[str, str] = {}
for _culture, _pools in CULTURE_POOLS.items():
    for _n in _pools["last"]:
        LAST_NAME_CULTURE.setdefault(_n, _culture)


class PersonSampler:
    """Vectorised joint sampler for coherent person identities.

    Draws ``(culture, gender, first, last)`` tuples so that every marginal
    AND every pairwise dependence looks like a real population:

    >>> sampler = PersonSampler(np.random.default_rng(0))
    >>> people = sampler.sample(1000)
    >>> people["first"][0], people["last"][0], people["gender"][0]

    ``mix``     — culture → weight mapping (normalised internally).
    ``p_female``— marginal gender split for sampled names.
    """

    def __init__(
        self,
        rng: np.random.Generator,
        mix: Optional[Dict[str, float]] = None,
        p_female: float = 0.50,
        intermix_rate: float = INTERMIX_RATE,
    ):
        self.rng = rng
        raw_mix = mix or DEFAULT_CULTURE_MIX
        cultures = [c for c in raw_mix if c in CULTURE_POOLS]
        weights = np.array([raw_mix[c] for c in cultures], dtype=float)
        self.cultures = cultures
        self.weights = weights / weights.sum()
        self.p_female = p_female
        self.intermix_rate = intermix_rate

    def sample(self, size: int) -> Dict[str, np.ndarray]:
        culture_idx = self.rng.choice(len(self.cultures), size=size, p=self.weights)
        cultures = np.array(self.cultures, dtype=object)[culture_idx]
        is_female = self.rng.random(size) < self.p_female

        # Surname culture: same as first-name culture except for intermixed rows
        surname_cultures = cultures.copy()
        intermix_mask = self.rng.random(size) < self.intermix_rate
        if intermix_mask.any():
            n_mix = int(intermix_mask.sum())
            mixed_idx = self.rng.choice(len(self.cultures), size=n_mix, p=self.weights)
            surname_cultures[intermix_mask] = np.array(self.cultures, dtype=object)[mixed_idx]

        first = np.empty(size, dtype=object)
        last = np.empty(size, dtype=object)
        for culture in self.cultures:
            pools = CULTURE_POOLS[culture]
            c_mask = cultures == culture
            for gender, g_mask in (("female", is_female), ("male", ~is_female)):
                mask = c_mask & g_mask
                n = int(mask.sum())
                if n:
                    first[mask] = self.rng.choice(pools[gender], size=n)
            s_mask = surname_cultures == culture
            n = int(s_mask.sum())
            if n:
                last[s_mask] = self.rng.choice(pools["last"], size=n)

        gender = np.where(is_female, "Female", "Male").astype(object)
        full = np.array([f"{f} {l}" for f, l in zip(first, last)], dtype=object)
        return {
            "first": first,
            "last": last,
            "full": full,
            "gender": gender,
            "culture": cultures,
        }

    def replacement_first_names(
        self, target_genders: np.ndarray, anchor_cultures: np.ndarray
    ) -> np.ndarray:
        """First names matching ``target_genders``, drawn per-row from
        ``anchor_cultures`` (e.g. the culture of an existing surname)."""
        size = len(target_genders)
        out = np.empty(size, dtype=object)
        for i in range(size):
            culture = anchor_cultures[i] if anchor_cultures[i] in CULTURE_POOLS else "anglo"
            gender = "female" if str(target_genders[i]).lower().startswith("f") else "male"
            out[i] = self.rng.choice(CULTURE_POOLS[culture][gender])
        return out


# ---------------------------------------------------------------------------
# Nationality → culture pool mapping (country names AND demonyms, lowercase).
# Approximations are deliberate and documented: Filipino naming is largely
# Hispanic (Spanish colonial surnames), Singapore maps to its Chinese
# majority, Brazil's Portuguese names are closest to the hispanic pool.
# ---------------------------------------------------------------------------

_NATIONALITY_GROUPS: Dict[str, List[str]] = {
    "south_asian": [
        "india", "indian", "pakistan", "pakistani", "bangladesh", "bangladeshi",
        "sri lanka", "sri lankan", "nepal", "nepali", "nepalese",
    ],
    "middle_eastern": [
        "uae", "united arab emirates", "emirati", "saudi arabia", "saudi",
        "egypt", "egyptian", "jordan", "jordanian", "lebanon", "lebanese",
        "syria", "syrian", "iraq", "iraqi", "oman", "omani", "qatar", "qatari",
        "kuwait", "kuwaiti", "bahrain", "bahraini", "yemen", "yemeni",
        "palestine", "palestinian", "morocco", "moroccan", "tunisia",
        "tunisian", "algeria", "algerian", "sudan", "sudanese",
    ],
    "anglo": [
        "united kingdom", "uk", "british", "united states", "usa", "american",
        "australia", "australian", "canada", "canadian", "ireland", "irish",
        "new zealand",
    ],
    "chinese": ["china", "chinese", "taiwan", "taiwanese", "hong kong", "singapore", "singaporean"],
    "japanese": ["japan", "japanese"],
    "korean": ["south korea", "korea", "korean"],
    "hispanic": [
        "philippines", "filipino", "filipina", "mexico", "mexican", "spain",
        "spanish", "colombia", "colombian", "argentina", "argentine", "peru",
        "peruvian", "chile", "chilean", "venezuela", "venezuelan", "brazil",
        "brazilian",
    ],
    "african": [
        "nigeria", "nigerian", "kenya", "kenyan", "ghana", "ghanaian",
        "ethiopia", "ethiopian", "south africa", "south african", "uganda",
        "ugandan", "tanzania", "tanzanian",
    ],
    "german": ["germany", "german", "austria", "austrian", "switzerland", "swiss"],
    "french": ["france", "french", "belgium", "belgian"],
    "italian": ["italy", "italian"],
}

NATIONALITY_CULTURE: Dict[str, str] = {}
for _culture, _labels in _NATIONALITY_GROUPS.items():
    for _label in _labels:
        NATIONALITY_CULTURE.setdefault(_label, _culture)


def lookup_nationality_culture(nationality: str) -> Optional[str]:
    """Culture pool for a nationality value (country name or demonym), else None."""
    return NATIONALITY_CULTURE.get(str(nationality).strip().lower())


def lookup_gender(first_name: str) -> Optional[str]:
    """Return 'male'/'female' for a known first name, else None."""
    return NAME_GENDER.get(str(first_name).split(" ")[0])


def lookup_surname_culture(last_name: str) -> str:
    return LAST_NAME_CULTURE.get(str(last_name), "anglo")
