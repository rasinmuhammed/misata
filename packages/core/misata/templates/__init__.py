"""
Industry templates for quick-start synthetic data generation.

Each template provides:
- Reference tables with realistic inline data
- Transactional tables with proper relationships
- Industry-specific column definitions
"""

from typing import Dict, List, Any

from misata.schema import SchemaConfig, Table, Column, Relationship


# ============================================================================
# SAAS TEMPLATE
# ============================================================================

SAAS_TEMPLATE = {
    "name": "SaaS Company Dataset",
    "description": "Complete SaaS company data with users, plans, subscriptions, and payments",
    "seed": 42,
    "tables": [
        {
            "name": "plans",
            "is_reference": True,
            "inline_data": [
                {"id": 1, "name": "Free", "price": 0.0, "billing_period": "monthly", "features": "Basic features, 1 user"},
                {"id": 2, "name": "Starter", "price": 9.99, "billing_period": "monthly", "features": "All free + 5 users, analytics"},
                {"id": 3, "name": "Professional", "price": 29.99, "billing_period": "monthly", "features": "All starter + 25 users, API access"},
                {"id": 4, "name": "Enterprise", "price": 99.99, "billing_period": "monthly", "features": "Unlimited users, custom integrations, SLA"},
            ]
        },
        {"name": "users", "row_count": 10000, "is_reference": False},
        {"name": "subscriptions", "row_count": 8000, "is_reference": False},
        {"name": "payments", "row_count": 50000, "is_reference": False},
        {"name": "usage_events", "row_count": 100000, "is_reference": False},
    ],
    "columns": {
        "users": [
            {"name": "id", "type": "int", "distribution_params": {"distribution": "uniform", "min": 1, "max": 10000}, "unique": True},
            {"name": "name", "type": "text", "distribution_params": {"text_type": "name"}},
            {"name": "email", "type": "text", "distribution_params": {"text_type": "email"}},
            {"name": "company", "type": "text", "distribution_params": {"text_type": "company"}},
            {"name": "created_at", "type": "date", "distribution_params": {"start": "2022-01-01", "end": "2024-12-31"}},
        ],
        "subscriptions": [
            {"name": "id", "type": "int", "distribution_params": {"distribution": "uniform", "min": 1, "max": 8000}},
            {"name": "user_id", "type": "foreign_key", "distribution_params": {}},
            {"name": "plan_id", "type": "foreign_key", "distribution_params": {}},
            {"name": "status", "type": "categorical", "distribution_params": {"choices": ["active", "cancelled", "paused", "trial"], "probabilities": [0.7, 0.15, 0.1, 0.05]}},
            {"name": "started_at", "type": "date", "distribution_params": {"start": "2022-01-01", "end": "2024-12-31"}},
        ],
        "payments": [
            {"name": "id", "type": "int", "distribution_params": {"distribution": "uniform", "min": 1, "max": 50000}},
            {"name": "subscription_id", "type": "foreign_key", "distribution_params": {}},
            {"name": "amount", "type": "categorical", "distribution_params": {"choices": [9.99, 29.99, 99.99], "probabilities": [0.5, 0.35, 0.15]}},
            {"name": "status", "type": "categorical", "distribution_params": {"choices": ["completed", "pending", "failed", "refunded"], "probabilities": [0.9, 0.05, 0.03, 0.02]}},
            {"name": "paid_at", "type": "date", "distribution_params": {"start": "2022-01-01", "end": "2024-12-31"}},
        ],
        "usage_events": [
            {"name": "id", "type": "int", "distribution_params": {"distribution": "uniform", "min": 1, "max": 100000}},
            {"name": "user_id", "type": "foreign_key", "distribution_params": {}},
            {"name": "event_type", "type": "categorical", "distribution_params": {"choices": ["login", "api_call", "export", "invite_user", "report_view"]}},
            {"name": "created_at", "type": "date", "distribution_params": {"start": "2023-01-01", "end": "2024-12-31"}},
        ],
    },
    "relationships": [
        {"parent_table": "users", "child_table": "subscriptions", "parent_key": "id", "child_key": "user_id"},
        {"parent_table": "plans", "child_table": "subscriptions", "parent_key": "id", "child_key": "plan_id"},
        {"parent_table": "subscriptions", "child_table": "payments", "parent_key": "id", "child_key": "subscription_id"},
        {"parent_table": "users", "child_table": "usage_events", "parent_key": "id", "child_key": "user_id"},
    ],
    "events": []
}


# ============================================================================
# E-COMMERCE TEMPLATE
# ============================================================================

ECOMMERCE_TEMPLATE = {
    "name": "E-Commerce Store Dataset",
    "description": "Complete e-commerce data with products, orders, and reviews",
    "seed": 42,
    "tables": [
        {
            "name": "categories",
            "is_reference": True,
            "inline_data": [
                {"id": 1, "name": "Electronics", "description": "Phones, computers, accessories"},
                {"id": 2, "name": "Clothing", "description": "Apparel and fashion"},
                {"id": 3, "name": "Home & Garden", "description": "Furniture and decor"},
                {"id": 4, "name": "Sports", "description": "Sports equipment and apparel"},
                {"id": 5, "name": "Books", "description": "Books and media"},
            ]
        },
        {
            "name": "products",
            "is_reference": True,
            "inline_data": [
                {"id": 1, "name": "iPhone 15 Pro", "category_id": 1, "price": 999.99, "stock": 150},
                {"id": 2, "name": "MacBook Air M3", "category_id": 1, "price": 1299.99, "stock": 80},
                {"id": 3, "name": "AirPods Pro", "category_id": 1, "price": 249.99, "stock": 500},
                {"id": 4, "name": "Classic T-Shirt", "category_id": 2, "price": 29.99, "stock": 1000},
                {"id": 5, "name": "Running Shoes", "category_id": 4, "price": 89.99, "stock": 300},
                {"id": 6, "name": "Yoga Mat", "category_id": 4, "price": 39.99, "stock": 450},
                {"id": 7, "name": "Coffee Table", "category_id": 3, "price": 199.99, "stock": 75},
                {"id": 8, "name": "Desk Lamp", "category_id": 3, "price": 49.99, "stock": 200},
                {"id": 9, "name": "Python Cookbook", "category_id": 5, "price": 49.99, "stock": 120},
                {"id": 10, "name": "Data Science Handbook", "category_id": 5, "price": 59.99, "stock": 100},
            ]
        },
        {"name": "customers", "row_count": 10000, "is_reference": False},
        {"name": "orders", "row_count": 25000, "is_reference": False},
        {"name": "order_items", "row_count": 50000, "is_reference": False},
        {"name": "reviews", "row_count": 15000, "is_reference": False},
    ],
    "columns": {
        "customers": [
            {"name": "id", "type": "int", "distribution_params": {"distribution": "uniform", "min": 1, "max": 10000}, "unique": True},
            {"name": "name", "type": "text", "distribution_params": {"text_type": "name"}},
            {"name": "email", "type": "text", "distribution_params": {"text_type": "email"}},
            {"name": "address", "type": "text", "distribution_params": {"text_type": "address"}},
            {"name": "created_at", "type": "date", "distribution_params": {"start": "2020-01-01", "end": "2024-12-31"}},
        ],
        "orders": [
            {"name": "id", "type": "int", "distribution_params": {"distribution": "uniform", "min": 1, "max": 25000}},
            {"name": "customer_id", "type": "foreign_key", "distribution_params": {}},
            {"name": "status", "type": "categorical", "distribution_params": {"choices": ["pending", "shipped", "delivered", "cancelled", "returned"], "probabilities": [0.1, 0.15, 0.65, 0.05, 0.05]}},
            {"name": "total", "type": "float", "distribution_params": {"distribution": "exponential", "scale": 150, "min": 10, "max": 5000}},
            {"name": "ordered_at", "type": "date", "distribution_params": {"start": "2022-01-01", "end": "2024-12-31"}},
        ],
        "order_items": [
            {"name": "id", "type": "int", "distribution_params": {"distribution": "uniform", "min": 1, "max": 50000}},
            {"name": "order_id", "type": "foreign_key", "distribution_params": {}},
            {"name": "product_id", "type": "foreign_key", "distribution_params": {}},
            {"name": "quantity", "type": "int", "distribution_params": {"distribution": "poisson", "lambda": 2, "min": 1, "max": 10}},
        ],
        "reviews": [
            {"name": "id", "type": "int", "distribution_params": {"distribution": "uniform", "min": 1, "max": 15000}},
            {"name": "product_id", "type": "foreign_key", "distribution_params": {}},
            {"name": "customer_id", "type": "foreign_key", "distribution_params": {}},
            {"name": "rating", "type": "int", "distribution_params": {"choices": [1, 2, 3, 4, 5], "probabilities": [0.05, 0.05, 0.15, 0.35, 0.40]}},
            {"name": "created_at", "type": "date", "distribution_params": {"start": "2022-01-01", "end": "2024-12-31"}},
        ],
    },
    "relationships": [
        {"parent_table": "customers", "child_table": "orders", "parent_key": "id", "child_key": "customer_id"},
        {"parent_table": "orders", "child_table": "order_items", "parent_key": "id", "child_key": "order_id"},
        {"parent_table": "products", "child_table": "order_items", "parent_key": "id", "child_key": "product_id"},
        {"parent_table": "products", "child_table": "reviews", "parent_key": "id", "child_key": "product_id"},
        {"parent_table": "customers", "child_table": "reviews", "parent_key": "id", "child_key": "customer_id"},
    ],
    "events": []
}


# ============================================================================
# FITNESS TEMPLATE
# ============================================================================

FITNESS_TEMPLATE = {
    "name": "Fitness App Dataset",
    "description": "Fitness app data with exercises, workouts, and nutrition",
    "seed": 42,
    "tables": [
        {
            "name": "plans",
            "is_reference": True,
            "inline_data": [
                {"id": 1, "name": "Free", "price": 0.0, "features": "Basic workout tracking"},
                {"id": 2, "name": "Premium", "price": 9.99, "features": "All workouts + nutrition tracking"},
                {"id": 3, "name": "Pro", "price": 19.99, "features": "Everything + personal coaching"},
            ]
        },
        {
            "name": "exercises",
            "is_reference": True,
            "inline_data": [
                {"id": 1, "name": "Running", "category": "Cardio", "calories_per_minute": 10, "difficulty": "medium"},
                {"id": 2, "name": "Cycling", "category": "Cardio", "calories_per_minute": 8, "difficulty": "easy"},
                {"id": 3, "name": "Swimming", "category": "Cardio", "calories_per_minute": 9, "difficulty": "medium"},
                {"id": 4, "name": "Yoga", "category": "Flexibility", "calories_per_minute": 3, "difficulty": "easy"},
                {"id": 5, "name": "Pilates", "category": "Flexibility", "calories_per_minute": 4, "difficulty": "medium"},
                {"id": 6, "name": "Weightlifting", "category": "Strength", "calories_per_minute": 6, "difficulty": "hard"},
                {"id": 7, "name": "HIIT", "category": "Cardio", "calories_per_minute": 12, "difficulty": "hard"},
                {"id": 8, "name": "Boxing", "category": "Cardio", "calories_per_minute": 11, "difficulty": "hard"},
                {"id": 9, "name": "Stretching", "category": "Flexibility", "calories_per_minute": 2, "difficulty": "easy"},
                {"id": 10, "name": "Walking", "category": "Cardio", "calories_per_minute": 4, "difficulty": "easy"},
            ]
        },
        {
            "name": "meal_types",
            "is_reference": True,
            "inline_data": [
                {"id": 1, "name": "Breakfast", "typical_calories": 400},
                {"id": 2, "name": "Lunch", "typical_calories": 600},
                {"id": 3, "name": "Dinner", "typical_calories": 700},
                {"id": 4, "name": "Snack", "typical_calories": 200},
            ]
        },
        {"name": "users", "row_count": 10000, "is_reference": False},
        {"name": "subscriptions", "row_count": 8000, "is_reference": False},
        {"name": "workouts", "row_count": 100000, "is_reference": False},
        {"name": "meals", "row_count": 50000, "is_reference": False},
    ],
    "columns": {
        "users": [
            {"name": "id", "type": "int", "distribution_params": {"distribution": "uniform", "min": 1, "max": 10000}, "unique": True},
            {"name": "name", "type": "text", "distribution_params": {"text_type": "name"}},
            {"name": "email", "type": "text", "distribution_params": {"text_type": "email"}},
            {"name": "age", "type": "int", "distribution_params": {"distribution": "uniform", "min": 18, "max": 65}},
            {"name": "weight_kg", "type": "float", "distribution_params": {"distribution": "normal", "mean": 75, "std": 15, "min": 40, "max": 150}},
            {"name": "height_cm", "type": "float", "distribution_params": {"distribution": "normal", "mean": 170, "std": 10, "min": 140, "max": 210}},
            {"name": "goal", "type": "categorical", "distribution_params": {"choices": ["lose_weight", "build_muscle", "maintain", "improve_endurance"]}},
        ],
        "subscriptions": [
            {"name": "id", "type": "int", "distribution_params": {"distribution": "uniform", "min": 1, "max": 8000}},
            {"name": "user_id", "type": "foreign_key", "distribution_params": {}},
            {"name": "plan_id", "type": "foreign_key", "distribution_params": {}},
            {"name": "status", "type": "categorical", "distribution_params": {"choices": ["active", "cancelled", "paused"], "probabilities": [0.75, 0.15, 0.10]}},
            {"name": "started_at", "type": "date", "distribution_params": {"start": "2022-01-01", "end": "2024-12-31"}},
        ],
        "workouts": [
            {"name": "id", "type": "int", "distribution_params": {"distribution": "uniform", "min": 1, "max": 100000}},
            {"name": "user_id", "type": "foreign_key", "distribution_params": {}},
            {"name": "exercise_id", "type": "foreign_key", "distribution_params": {}},
            {"name": "duration_minutes", "type": "int", "distribution_params": {"distribution": "uniform", "min": 15, "max": 90}},
            {"name": "calories_burned", "type": "int", "distribution_params": {"distribution": "normal", "mean": 300, "std": 150, "min": 50, "max": 1500}},
            {"name": "date", "type": "date", "distribution_params": {"start": "2023-01-01", "end": "2024-12-31"}},
        ],
        "meals": [
            {"name": "id", "type": "int", "distribution_params": {"distribution": "uniform", "min": 1, "max": 50000}},
            {"name": "user_id", "type": "foreign_key", "distribution_params": {}},
            {"name": "meal_type_id", "type": "foreign_key", "distribution_params": {}},
            {"name": "calories", "type": "int", "distribution_params": {"distribution": "normal", "mean": 500, "std": 200, "min": 100, "max": 1500}},
            {"name": "date", "type": "date", "distribution_params": {"start": "2023-01-01", "end": "2024-12-31"}},
        ],
    },
    "relationships": [
        {"parent_table": "users", "child_table": "subscriptions", "parent_key": "id", "child_key": "user_id"},
        {"parent_table": "plans", "child_table": "subscriptions", "parent_key": "id", "child_key": "plan_id"},
        {"parent_table": "users", "child_table": "workouts", "parent_key": "id", "child_key": "user_id"},
        {"parent_table": "exercises", "child_table": "workouts", "parent_key": "id", "child_key": "exercise_id"},
        {"parent_table": "users", "child_table": "meals", "parent_key": "id", "child_key": "user_id"},
        {"parent_table": "meal_types", "child_table": "meals", "parent_key": "id", "child_key": "meal_type_id"},
    ],
    "events": []
}


# ============================================================================
# HEALTHCARE TEMPLATE
# ============================================================================

HEALTHCARE_TEMPLATE = {
    "name": "Healthcare System Dataset",
    "description": "Healthcare data with patients, doctors, appointments, and diagnoses",
    "seed": 42,
    "tables": [
        {
            "name": "departments",
            "is_reference": True,
            "inline_data": [
                {"id": 1, "name": "Cardiology", "floor": 3},
                {"id": 2, "name": "Orthopedics", "floor": 4},
                {"id": 3, "name": "Pediatrics", "floor": 2},
                {"id": 4, "name": "Neurology", "floor": 5},
                {"id": 5, "name": "General Medicine", "floor": 1},
                {"id": 6, "name": "Emergency", "floor": 1},
            ]
        },
        {
            "name": "diagnoses_catalog",
            "is_reference": True,
            "inline_data": [
                {"id": 1, "code": "J06.9", "name": "Acute upper respiratory infection", "category": "Respiratory"},
                {"id": 2, "code": "I10", "name": "Essential hypertension", "category": "Cardiovascular"},
                {"id": 3, "code": "E11.9", "name": "Type 2 diabetes", "category": "Endocrine"},
                {"id": 4, "code": "M54.5", "name": "Low back pain", "category": "Musculoskeletal"},
                {"id": 5, "code": "J18.9", "name": "Pneumonia", "category": "Respiratory"},
                {"id": 6, "code": "K21.0", "name": "GERD", "category": "Digestive"},
                {"id": 7, "code": "F32.9", "name": "Major depressive disorder", "category": "Mental Health"},
                {"id": 8, "code": "G43.909", "name": "Migraine", "category": "Neurological"},
            ]
        },
        {"name": "doctors", "row_count": 100, "is_reference": False},
        {"name": "patients", "row_count": 10000, "is_reference": False},
        {"name": "appointments", "row_count": 50000, "is_reference": False},
        {"name": "patient_diagnoses", "row_count": 30000, "is_reference": False},
    ],
    "columns": {
        "doctors": [
            {"name": "id", "type": "int", "distribution_params": {"distribution": "uniform", "min": 1, "max": 100}, "unique": True},
            {"name": "name", "type": "text", "distribution_params": {"text_type": "name"}},
            {"name": "department_id", "type": "foreign_key", "distribution_params": {}},
            {"name": "specialization", "type": "categorical", "distribution_params": {"choices": ["MD", "DO", "Specialist", "Surgeon"]}},
            {"name": "years_experience", "type": "int", "distribution_params": {"distribution": "uniform", "min": 1, "max": 35}},
        ],
        "patients": [
            {"name": "id", "type": "int", "distribution_params": {"distribution": "uniform", "min": 1, "max": 10000}, "unique": True},
            {"name": "name", "type": "text", "distribution_params": {"text_type": "name"}},
            {"name": "date_of_birth", "type": "date", "distribution_params": {"start": "1940-01-01", "end": "2010-12-31"}},
            {"name": "gender", "type": "categorical", "distribution_params": {"choices": ["Male", "Female", "Other"], "probabilities": [0.48, 0.48, 0.04]}},
            {"name": "phone", "type": "text", "distribution_params": {"text_type": "phone"}},
            {"name": "blood_type", "type": "categorical", "distribution_params": {"choices": ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]}},
        ],
        "appointments": [
            {"name": "id", "type": "int", "distribution_params": {"distribution": "uniform", "min": 1, "max": 50000}},
            {"name": "patient_id", "type": "foreign_key", "distribution_params": {}},
            {"name": "doctor_id", "type": "foreign_key", "distribution_params": {}},
            {"name": "scheduled_at", "type": "date", "distribution_params": {"start": "2023-01-01", "end": "2025-12-31"}},
            {"name": "status", "type": "categorical", "distribution_params": {"choices": ["scheduled", "completed", "cancelled", "no_show"], "probabilities": [0.2, 0.65, 0.10, 0.05]}},
            {"name": "duration_minutes", "type": "int", "distribution_params": {"choices": [15, 30, 45, 60], "probabilities": [0.3, 0.4, 0.2, 0.1]}},
        ],
        "patient_diagnoses": [
            {"name": "id", "type": "int", "distribution_params": {"distribution": "uniform", "min": 1, "max": 30000}},
            {"name": "patient_id", "type": "foreign_key", "distribution_params": {}},
            {"name": "diagnosis_id", "type": "foreign_key", "distribution_params": {}},
            {"name": "diagnosed_at", "type": "date", "distribution_params": {"start": "2020-01-01", "end": "2024-12-31"}},
            {"name": "severity", "type": "categorical", "distribution_params": {"choices": ["mild", "moderate", "severe"], "probabilities": [0.5, 0.35, 0.15]}},
        ],
    },
    "relationships": [
        {"parent_table": "departments", "child_table": "doctors", "parent_key": "id", "child_key": "department_id"},
        {"parent_table": "patients", "child_table": "appointments", "parent_key": "id", "child_key": "patient_id"},
        {"parent_table": "doctors", "child_table": "appointments", "parent_key": "id", "child_key": "doctor_id"},
        {"parent_table": "patients", "child_table": "patient_diagnoses", "parent_key": "id", "child_key": "patient_id"},
        {"parent_table": "diagnoses_catalog", "child_table": "patient_diagnoses", "parent_key": "id", "child_key": "diagnosis_id"},
    ],
    "events": []
}


# ============================================================================
# TEMPLATE REGISTRY
# ============================================================================

TEMPLATES = {
    "saas": SAAS_TEMPLATE,
    "ecommerce": ECOMMERCE_TEMPLATE,
    "fitness": FITNESS_TEMPLATE,
    "healthcare": HEALTHCARE_TEMPLATE,
}


def get_template(name: str) -> Dict[str, Any]:
    """
    Get a template by name.

    Args:
        name: Template name (saas, ecommerce, fitness, healthcare)

    Returns:
        Template dictionary

    Raises:
        ValueError: If template not found
    """
    if name not in TEMPLATES:
        available = ", ".join(TEMPLATES.keys())
        raise ValueError(f"Template '{name}' not found. Available: {available}")
    return TEMPLATES[name]


def list_templates() -> List[str]:
    """Get list of available template names."""
    return list(TEMPLATES.keys())


def template_to_schema(template_name: str, row_multiplier: float = 1.0) -> SchemaConfig:
    """
    Convert a template to a SchemaConfig.

    Args:
        template_name: Name of template
        row_multiplier: Multiply row counts by this factor

    Returns:
        SchemaConfig ready for generation
    """
    template = get_template(template_name)

    # Adjust row counts
    if row_multiplier != 1.0:
        for table in template["tables"]:
            if "row_count" in table and not table.get("is_reference"):
                table["row_count"] = int(table["row_count"] * row_multiplier)

    # Parse tables
    tables = []
    for t in template["tables"]:
        tables.append(Table(
            name=t["name"],
            row_count=t.get("row_count", len(t.get("inline_data", [])) or 100),
            is_reference=t.get("is_reference", False),
            inline_data=t.get("inline_data"),
        ))

    # Parse columns
    columns = {}
    for table_name, cols in template["columns"].items():
        columns[table_name] = []
        for c in cols:
            columns[table_name].append(Column(
                name=c["name"],
                type=c["type"],
                distribution_params=c.get("distribution_params", {}),
                nullable=c.get("nullable", False),
                unique=c.get("unique", False),
            ))

    # Add inferred columns for reference tables
    for table in tables:
        if table.is_reference and table.inline_data and table.name not in columns:
            columns[table.name] = []
            first_row = table.inline_data[0]
            for col_name in first_row.keys():
                columns[table.name].append(Column(
                    name=col_name,
                    type="text",  # Will be inferred
                    distribution_params={},
                ))

    # Parse relationships
    relationships = []
    for r in template["relationships"]:
        relationships.append(Relationship(
            parent_table=r["parent_table"],
            child_table=r["child_table"],
            parent_key=r["parent_key"],
            child_key=r["child_key"],
        ))

    return SchemaConfig(
        name=template["name"],
        description=template.get("description"),
        tables=tables,
        columns=columns,
        relationships=relationships,
        events=[],
        seed=template.get("seed", 42),
    )
