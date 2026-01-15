"""
Domain-Aware Reference Data Library

Pre-built realistic data templates for common business domains.
This ensures reference tables (plans, exercises, categories) have
sensible, domain-appropriate values instead of random garbage.

Usage:
    from misata.reference_data import get_reference_data, detect_domain
    
    domain = detect_domain(["plans", "subscriptions", "users"])
    plans_data = get_reference_data(domain, "plans")
"""

from typing import Any, Dict, List, Optional


# ============ DOMAIN TEMPLATES ============

REFERENCE_DATA_LIBRARY: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
    
    # ===== SaaS / Subscription Business =====
    "saas": {
        "plans": [
            {"id": 1, "name": "Free", "price": 0.00, "features": "Basic features, Community support"},
            {"id": 2, "name": "Starter", "price": 9.99, "features": "5GB storage, Email support"},
            {"id": 3, "name": "Pro", "price": 29.99, "features": "50GB storage, Priority support, Analytics"},
            {"id": 4, "name": "Business", "price": 79.99, "features": "200GB storage, Dedicated support, API access"},
            {"id": 5, "name": "Enterprise", "price": 199.99, "features": "Unlimited storage, SLA, Custom integrations"},
        ],
        "tiers": [
            {"id": 1, "name": "Bronze", "discount_pct": 0},
            {"id": 2, "name": "Silver", "discount_pct": 10},
            {"id": 3, "name": "Gold", "discount_pct": 20},
            {"id": 4, "name": "Platinum", "discount_pct": 30},
        ],
    },
    
    # ===== Fitness / Health App =====
    "fitness": {
        "exercises": [
            {"id": 1, "name": "Running", "category": "Cardio", "calories_per_minute": 10, "difficulty": "Medium"},
            {"id": 2, "name": "Swimming", "category": "Cardio", "calories_per_minute": 9, "difficulty": "Medium"},
            {"id": 3, "name": "Cycling", "category": "Cardio", "calories_per_minute": 8, "difficulty": "Easy"},
            {"id": 4, "name": "HIIT", "category": "Cardio", "calories_per_minute": 12, "difficulty": "Hard"},
            {"id": 5, "name": "Yoga", "category": "Flexibility", "calories_per_minute": 3, "difficulty": "Easy"},
            {"id": 6, "name": "Pilates", "category": "Flexibility", "calories_per_minute": 4, "difficulty": "Medium"},
            {"id": 7, "name": "Weight Training", "category": "Strength", "calories_per_minute": 6, "difficulty": "Medium"},
            {"id": 8, "name": "CrossFit", "category": "Strength", "calories_per_minute": 11, "difficulty": "Hard"},
        ],
        "plans": [
            {"id": 1, "name": "Free", "price": 0.00, "features": "Basic workouts"},
            {"id": 2, "name": "Basic", "price": 9.99, "features": "All workouts, Progress tracking"},
            {"id": 3, "name": "Premium", "price": 19.99, "features": "Personal trainer, Meal plans"},
            {"id": 4, "name": "Elite", "price": 49.99, "features": "1-on-1 coaching, Custom programs"},
        ],
        "workout_types": [
            {"id": 1, "name": "Morning Cardio", "duration_minutes": 30, "intensity": "Medium"},
            {"id": 2, "name": "Full Body Strength", "duration_minutes": 45, "intensity": "High"},
            {"id": 3, "name": "Relaxing Yoga", "duration_minutes": 60, "intensity": "Low"},
            {"id": 4, "name": "HIIT Blast", "duration_minutes": 20, "intensity": "Very High"},
        ],
    },
    
    # ===== E-commerce / Retail =====
    "ecommerce": {
        "categories": [
            {"id": 1, "name": "Electronics", "description": "Phones, laptops, gadgets"},
            {"id": 2, "name": "Clothing", "description": "Fashion and apparel"},
            {"id": 3, "name": "Home & Garden", "description": "Furniture, decor, outdoor"},
            {"id": 4, "name": "Sports & Outdoors", "description": "Fitness, camping, sports gear"},
            {"id": 5, "name": "Books & Media", "description": "Books, music, movies"},
            {"id": 6, "name": "Health & Beauty", "description": "Skincare, supplements, wellness"},
        ],
        "products": [
            {"id": 1, "name": "Wireless Headphones", "category_id": 1, "price": 79.99},
            {"id": 2, "name": "Smart Watch", "category_id": 1, "price": 199.99},
            {"id": 3, "name": "Cotton T-Shirt", "category_id": 2, "price": 24.99},
            {"id": 4, "name": "Running Shoes", "category_id": 4, "price": 89.99},
            {"id": 5, "name": "Yoga Mat", "category_id": 4, "price": 29.99},
        ],
        "shipping_methods": [
            {"id": 1, "name": "Standard", "days": 5, "price": 4.99},
            {"id": 2, "name": "Express", "days": 2, "price": 9.99},
            {"id": 3, "name": "Next Day", "days": 1, "price": 19.99},
            {"id": 4, "name": "Free Shipping", "days": 7, "price": 0.00},
        ],
    },
    
    # ===== Finance / Banking =====
    "finance": {
        "account_types": [
            {"id": 1, "name": "Checking", "interest_rate": 0.01, "monthly_fee": 0.00},
            {"id": 2, "name": "Savings", "interest_rate": 0.50, "monthly_fee": 0.00},
            {"id": 3, "name": "Money Market", "interest_rate": 1.00, "monthly_fee": 5.00},
            {"id": 4, "name": "Premium Checking", "interest_rate": 0.10, "monthly_fee": 15.00},
        ],
        "transaction_types": [
            {"id": 1, "name": "Deposit", "category": "Income"},
            {"id": 2, "name": "Withdrawal", "category": "Expense"},
            {"id": 3, "name": "Transfer", "category": "Transfer"},
            {"id": 4, "name": "Payment", "category": "Expense"},
            {"id": 5, "name": "Refund", "category": "Income"},
        ],
    },
    
    # ===== Education / LMS =====
    "education": {
        "courses": [
            {"id": 1, "name": "Python Fundamentals", "level": "Beginner", "duration_hours": 20, "price": 49.99},
            {"id": 2, "name": "Data Science Bootcamp", "level": "Intermediate", "duration_hours": 60, "price": 199.99},
            {"id": 3, "name": "Machine Learning", "level": "Advanced", "duration_hours": 40, "price": 149.99},
            {"id": 4, "name": "Web Development", "level": "Beginner", "duration_hours": 30, "price": 79.99},
        ],
        "difficulty_levels": [
            {"id": 1, "name": "Beginner", "description": "No prior experience needed"},
            {"id": 2, "name": "Intermediate", "description": "Some experience required"},
            {"id": 3, "name": "Advanced", "description": "Strong foundation needed"},
            {"id": 4, "name": "Expert", "description": "Professional level"},
        ],
    },
}


# ============ DOMAIN DETECTION ============

# Keywords that indicate a specific domain
DOMAIN_KEYWORDS = {
    "saas": ["subscription", "plan", "tier", "billing", "invoice", "tenant"],
    "fitness": ["exercise", "workout", "calories", "fitness", "gym", "training", "health"],
    "ecommerce": ["product", "category", "cart", "order", "shipping", "inventory", "catalog"],
    "finance": ["account", "transaction", "balance", "payment", "transfer", "bank"],
    "education": ["course", "student", "lesson", "enrollment", "grade", "instructor"],
}


def detect_domain(table_names: List[str]) -> str:
    """
    Detect the business domain based on table names.
    
    Args:
        table_names: List of table names in the schema
        
    Returns:
        Domain name (saas, fitness, ecommerce, finance, education, or 'generic')
    """
    table_names_lower = [t.lower() for t in table_names]
    all_text = " ".join(table_names_lower)
    
    domain_scores = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in all_text)
        if score > 0:
            domain_scores[domain] = score
    
    if domain_scores:
        return max(domain_scores, key=domain_scores.get)
    
    return "generic"


def get_reference_data(domain: str, table_name: str) -> Optional[List[Dict[str, Any]]]:
    """
    Get pre-built reference data for a table.
    
    Strategy:
    1. Check specific domain (exact match)
    2. Check specific domain (singular/plural match)
    3. GLOBAL FALLBACK: Check ALL domains for exact match
    4. GLOBAL FALLBACK: Check ALL domains for partial match
    """
    # Normalize table name
    table_key = table_name.lower().rstrip('s')  # Remove plural 's'
    
    # 1. Try specific domain first
    domain_data = REFERENCE_DATA_LIBRARY.get(domain, {})
    
    # Exact match in domain
    if table_name in domain_data:
        return domain_data[table_name]
    
    # Singular match in domain
    if table_key in domain_data:
        return domain_data[table_key]
        
    # Partial match in domain
    for key, data in domain_data.items():
        if table_key in key or key in table_key:
            return data
            
    # 2. GLOBAL SEARCH: Check all other domains
    # This handles mixed schemas (e.g. "fitness app with products")
    for other_domain, tables in REFERENCE_DATA_LIBRARY.items():
        if other_domain == domain:
            continue
            
        # Exact match
        if table_name in tables:
            return tables[table_name]
            
        # Singular match
        if table_key in tables:
            return tables[table_key]
    
    # 3. GLOBAL PARTIAL SEARCH
    for other_domain, tables in REFERENCE_DATA_LIBRARY.items():
        for key, data in tables.items():
            if table_key in key or key in table_key:
                return data
    
    return None


def get_all_domains() -> List[str]:
    """Get list of all supported domains."""
    return list(REFERENCE_DATA_LIBRARY.keys())


def get_domain_tables(domain: str) -> List[str]:
    """Get list of tables available for a domain."""
    return list(REFERENCE_DATA_LIBRARY.get(domain, {}).keys())
