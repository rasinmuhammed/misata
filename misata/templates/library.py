"""
Pre-built schema templates for common use cases.

Usage:
    from misata.templates.library import load_template, list_templates
    
    # See available templates
    print(list_templates())
    
    # Load a template
    config = load_template("ecommerce")
    
    # Generate data
    from misata import DataSimulator
    for table, batch in DataSimulator(config).generate_all():
        print(f"Generated {len(batch)} rows for {table}")
"""

from misata.schema import Column, Relationship, SchemaConfig, Table


def list_templates() -> list:
    """List all available built-in templates."""
    return ["ecommerce", "saas", "healthcare", "fintech"]


def load_template(name: str, row_multiplier: float = 1.0) -> SchemaConfig:
    """
    Load a pre-built schema template.
    
    Args:
        name: Template name (ecommerce, saas, healthcare, fintech)
        row_multiplier: Scale row counts (e.g., 0.1 for 10%, 2.0 for 2x)
        
    Returns:
        SchemaConfig ready for DataSimulator
    """
    templates = {
        "ecommerce": _ecommerce_template,
        "saas": _saas_template,
        "healthcare": _healthcare_template,
        "fintech": _fintech_template,
    }
    
    if name not in templates:
        raise ValueError(f"Unknown template: {name}. Available: {list(templates.keys())}")
    
    config = templates[name]()
    
    # Apply row multiplier
    if row_multiplier != 1.0:
        for table in config.tables:
            if not table.is_reference:
                table.row_count = int(table.row_count * row_multiplier)
    
    return config


def _ecommerce_template() -> SchemaConfig:
    """E-commerce platform with products, orders, reviews."""
    return SchemaConfig(
        name="E-commerce Platform",
        description="Complete e-commerce dataset with products, orders, and reviews",
        seed=42,
        tables=[
            # Reference tables
            Table(
                name="categories",
                is_reference=True,
                inline_data=[
                    {"id": 1, "name": "Electronics", "margin_pct": 15},
                    {"id": 2, "name": "Clothing", "margin_pct": 40},
                    {"id": 3, "name": "Home & Garden", "margin_pct": 25},
                    {"id": 4, "name": "Sports", "margin_pct": 30},
                    {"id": 5, "name": "Books", "margin_pct": 35},
                    {"id": 6, "name": "Beauty", "margin_pct": 50},
                ],
            ),
            Table(
                name="shipping_methods",
                is_reference=True,
                inline_data=[
                    {"id": 1, "name": "Standard", "days": 5, "cost": 4.99},
                    {"id": 2, "name": "Express", "days": 2, "cost": 9.99},
                    {"id": 3, "name": "Next Day", "days": 1, "cost": 19.99},
                    {"id": 4, "name": "Free Shipping", "days": 7, "cost": 0.00},
                ],
            ),
            # Transactional tables
            Table(name="customers", row_count=10000),
            Table(name="products", row_count=500),
            Table(name="orders", row_count=50000),
            Table(name="order_items", row_count=150000),
            Table(name="reviews", row_count=20000),
        ],
        columns={
            "customers": [
                Column(name="id", type="int", distribution_params={"min": 1, "max": 10000}, unique=True),
                Column(name="name", type="text", distribution_params={"text_type": "name"}),
                Column(name="email", type="text", distribution_params={"text_type": "email"}),
                Column(name="city", type="text", distribution_params={"text_type": "word", "smart_generate": True}),
                Column(name="created_at", type="date", distribution_params={"start": "2020-01-01", "end": "2024-12-31"}),
                Column(name="is_premium", type="boolean", distribution_params={"probability": 0.15}),
            ],
            "products": [
                Column(name="id", type="int", distribution_params={"min": 1, "max": 500}, unique=True),
                Column(name="name", type="text", distribution_params={"text_type": "sentence"}),
                Column(name="category_id", type="foreign_key", distribution_params={}),
                Column(name="price", type="float", distribution_params={"distribution": "uniform", "min": 9.99, "max": 299.99, "decimals": 2}),
                Column(name="stock", type="int", distribution_params={"distribution": "poisson", "lambda": 50}),
            ],
            "orders": [
                Column(name="id", type="int", distribution_params={"min": 1, "max": 50000}, unique=True),
                Column(name="customer_id", type="foreign_key", distribution_params={}),
                Column(name="shipping_method_id", type="foreign_key", distribution_params={}),
                Column(name="order_date", type="date", distribution_params={"start": "2023-01-01", "end": "2024-12-31"}),
                Column(name="status", type="categorical", distribution_params={"choices": ["completed", "pending", "shipped", "cancelled"], "probabilities": [0.6, 0.15, 0.2, 0.05]}),
                Column(name="total", type="float", distribution_params={"distribution": "exponential", "scale": 75, "min": 10, "decimals": 2}),
            ],
            "order_items": [
                Column(name="id", type="int", distribution_params={"min": 1, "max": 150000}, unique=True),
                Column(name="order_id", type="foreign_key", distribution_params={}),
                Column(name="product_id", type="foreign_key", distribution_params={}),
                Column(name="quantity", type="int", distribution_params={"distribution": "poisson", "lambda": 2, "min": 1}),
                Column(name="unit_price", type="float", distribution_params={"distribution": "uniform", "min": 5.0, "max": 200.0, "decimals": 2}),
            ],
            "reviews": [
                Column(name="id", type="int", distribution_params={"min": 1, "max": 20000}, unique=True),
                Column(name="product_id", type="foreign_key", distribution_params={}),
                Column(name="customer_id", type="foreign_key", distribution_params={}),
                Column(name="rating", type="int", distribution_params={"distribution": "categorical", "choices": [1, 2, 3, 4, 5], "probabilities": [0.05, 0.08, 0.15, 0.32, 0.40]}),
                Column(name="title", type="text", distribution_params={"text_type": "sentence", "smart_generate": True}),
                Column(name="created_at", type="date", distribution_params={"start": "2023-01-01", "end": "2024-12-31"}),
            ],
        },
        relationships=[
            Relationship(parent_table="categories", child_table="products", parent_key="id", child_key="category_id"),
            Relationship(parent_table="customers", child_table="orders", parent_key="id", child_key="customer_id"),
            Relationship(parent_table="shipping_methods", child_table="orders", parent_key="id", child_key="shipping_method_id"),
            Relationship(parent_table="orders", child_table="order_items", parent_key="id", child_key="order_id"),
            Relationship(parent_table="products", child_table="order_items", parent_key="id", child_key="product_id"),
            Relationship(parent_table="products", child_table="reviews", parent_key="id", child_key="product_id"),
            Relationship(parent_table="customers", child_table="reviews", parent_key="id", child_key="customer_id"),
        ],
    )


def _saas_template() -> SchemaConfig:
    """SaaS platform with users, subscriptions, and usage events."""
    return SchemaConfig(
        name="SaaS Platform",
        description="B2B SaaS with companies, users, subscriptions, and usage tracking",
        seed=42,
        tables=[
            Table(
                name="plans",
                is_reference=True,
                inline_data=[
                    {"id": 1, "name": "Free", "price": 0, "seats": 1, "features": "Basic"},
                    {"id": 2, "name": "Starter", "price": 29, "seats": 5, "features": "Core features"},
                    {"id": 3, "name": "Professional", "price": 99, "seats": 20, "features": "All features"},
                    {"id": 4, "name": "Enterprise", "price": 299, "seats": 100, "features": "Custom"},
                ],
            ),
            Table(name="companies", row_count=1000),
            Table(name="users", row_count=25000),
            Table(name="subscriptions", row_count=1200),
            Table(name="usage_events", row_count=500000),
        ],
        columns={
            "companies": [
                Column(name="id", type="int", distribution_params={"min": 1, "max": 1000}, unique=True),
                Column(name="name", type="text", distribution_params={"text_type": "company"}),
                Column(name="industry", type="text", distribution_params={"text_type": "word", "smart_generate": True}),
                Column(name="employee_count", type="int", distribution_params={"distribution": "exponential", "scale": 50, "min": 1}),
                Column(name="created_at", type="date", distribution_params={"start": "2020-01-01", "end": "2024-06-30"}),
            ],
            "users": [
                Column(name="id", type="int", distribution_params={"min": 1, "max": 25000}, unique=True),
                Column(name="company_id", type="foreign_key", distribution_params={}),
                Column(name="name", type="text", distribution_params={"text_type": "name"}),
                Column(name="email", type="text", distribution_params={"text_type": "email"}),
                Column(name="role", type="categorical", distribution_params={"choices": ["admin", "member", "viewer"], "probabilities": [0.1, 0.6, 0.3]}),
                Column(name="is_active", type="boolean", distribution_params={"probability": 0.85}),
                Column(name="last_login", type="date", distribution_params={"start": "2024-01-01", "end": "2024-12-31"}),
            ],
            "subscriptions": [
                Column(name="id", type="int", distribution_params={"min": 1, "max": 1200}, unique=True),
                Column(name="company_id", type="foreign_key", distribution_params={}),
                Column(name="plan_id", type="foreign_key", distribution_params={}),
                Column(name="status", type="categorical", distribution_params={"choices": ["active", "cancelled", "trial", "past_due"], "probabilities": [0.7, 0.1, 0.15, 0.05]}),
                Column(name="start_date", type="date", distribution_params={"start": "2022-01-01", "end": "2024-12-31"}),
                Column(name="mrr", type="float", distribution_params={"distribution": "exponential", "scale": 100, "min": 0, "decimals": 2}),
            ],
            "usage_events": [
                Column(name="id", type="int", distribution_params={"min": 1, "max": 500000}, unique=True),
                Column(name="user_id", type="foreign_key", distribution_params={}),
                Column(name="event_type", type="categorical", distribution_params={"choices": ["page_view", "api_call", "export", "login", "feature_use"], "probabilities": [0.4, 0.3, 0.1, 0.1, 0.1]}),
                Column(name="timestamp", type="datetime", distribution_params={"start": "2024-01-01", "end": "2024-12-31"}),
            ],
        },
        relationships=[
            Relationship(parent_table="companies", child_table="users", parent_key="id", child_key="company_id"),
            Relationship(parent_table="companies", child_table="subscriptions", parent_key="id", child_key="company_id"),
            Relationship(parent_table="plans", child_table="subscriptions", parent_key="id", child_key="plan_id"),
            Relationship(parent_table="users", child_table="usage_events", parent_key="id", child_key="user_id"),
        ],
    )


def _healthcare_template() -> SchemaConfig:
    """Healthcare system with patients, doctors, appointments, prescriptions."""
    return SchemaConfig(
        name="Healthcare System",
        description="Hospital management with patients, appointments, and prescriptions",
        seed=42,
        tables=[
            Table(
                name="specialties",
                is_reference=True,
                inline_data=[
                    {"id": 1, "name": "General Practice", "avg_consult_mins": 15},
                    {"id": 2, "name": "Cardiology", "avg_consult_mins": 30},
                    {"id": 3, "name": "Dermatology", "avg_consult_mins": 20},
                    {"id": 4, "name": "Orthopedics", "avg_consult_mins": 25},
                    {"id": 5, "name": "Pediatrics", "avg_consult_mins": 20},
                    {"id": 6, "name": "Psychiatry", "avg_consult_mins": 45},
                    {"id": 7, "name": "Neurology", "avg_consult_mins": 30},
                ],
            ),
            Table(name="patients", row_count=10000),
            Table(name="doctors", row_count=100),
            Table(name="appointments", row_count=50000),
            Table(name="prescriptions", row_count=75000),
        ],
        columns={
            "patients": [
                Column(name="id", type="int", distribution_params={"min": 1, "max": 10000}, unique=True),
                Column(name="name", type="text", distribution_params={"text_type": "name"}),
                Column(name="date_of_birth", type="date", distribution_params={"start": "1940-01-01", "end": "2020-12-31"}),
                Column(name="gender", type="categorical", distribution_params={"choices": ["M", "F", "Other"], "probabilities": [0.48, 0.48, 0.04]}),
                Column(name="phone", type="text", distribution_params={"text_type": "phone"}),
                Column(name="insurance_id", type="text", distribution_params={"text_type": "word"}),
            ],
            "doctors": [
                Column(name="id", type="int", distribution_params={"min": 1, "max": 100}, unique=True),
                Column(name="name", type="text", distribution_params={"text_type": "name"}),
                Column(name="specialty_id", type="foreign_key", distribution_params={}),
                Column(name="years_experience", type="int", distribution_params={"distribution": "normal", "mean": 15, "std": 8, "min": 1, "max": 40}),
                Column(name="is_accepting_patients", type="boolean", distribution_params={"probability": 0.8}),
            ],
            "appointments": [
                Column(name="id", type="int", distribution_params={"min": 1, "max": 50000}, unique=True),
                Column(name="patient_id", type="foreign_key", distribution_params={}),
                Column(name="doctor_id", type="foreign_key", distribution_params={}),
                Column(name="appointment_date", type="datetime", distribution_params={"start": "2023-01-01", "end": "2024-12-31"}),
                Column(name="duration_mins", type="int", distribution_params={"distribution": "normal", "mean": 25, "std": 10, "min": 10, "max": 60}),
                Column(name="status", type="categorical", distribution_params={"choices": ["completed", "scheduled", "cancelled", "no_show"], "probabilities": [0.65, 0.2, 0.1, 0.05]}),
                Column(name="notes", type="text", distribution_params={"text_type": "sentence"}),
            ],
            "prescriptions": [
                Column(name="id", type="int", distribution_params={"min": 1, "max": 75000}, unique=True),
                Column(name="appointment_id", type="foreign_key", distribution_params={}),
                Column(name="medication", type="text", distribution_params={"text_type": "word", "smart_generate": True}),
                Column(name="dosage", type="text", distribution_params={"text_type": "word"}),
                Column(name="duration_days", type="int", distribution_params={"distribution": "categorical", "choices": [7, 14, 30, 60, 90], "probabilities": [0.3, 0.25, 0.25, 0.1, 0.1]}),
            ],
        },
        relationships=[
            Relationship(parent_table="specialties", child_table="doctors", parent_key="id", child_key="specialty_id"),
            Relationship(parent_table="patients", child_table="appointments", parent_key="id", child_key="patient_id"),
            Relationship(parent_table="doctors", child_table="appointments", parent_key="id", child_key="doctor_id"),
            Relationship(parent_table="appointments", child_table="prescriptions", parent_key="id", child_key="appointment_id"),
        ],
    )


def _fintech_template() -> SchemaConfig:
    """Fintech platform with accounts, transactions, and fraud detection."""
    return SchemaConfig(
        name="Fintech Platform",
        description="Banking/payments platform with accounts, transactions, and fraud labels",
        seed=42,
        tables=[
            Table(
                name="account_types",
                is_reference=True,
                inline_data=[
                    {"id": 1, "name": "Checking", "min_balance": 0, "monthly_fee": 0},
                    {"id": 2, "name": "Savings", "min_balance": 100, "monthly_fee": 0},
                    {"id": 3, "name": "Premium", "min_balance": 5000, "monthly_fee": 15},
                    {"id": 4, "name": "Business", "min_balance": 1000, "monthly_fee": 25},
                ],
            ),
            Table(
                name="transaction_types",
                is_reference=True,
                inline_data=[
                    {"id": 1, "name": "deposit", "direction": "in"},
                    {"id": 2, "name": "withdrawal", "direction": "out"},
                    {"id": 3, "name": "transfer", "direction": "both"},
                    {"id": 4, "name": "payment", "direction": "out"},
                    {"id": 5, "name": "refund", "direction": "in"},
                ],
            ),
            Table(name="customers", row_count=25000),
            Table(name="accounts", row_count=35000),
            Table(name="transactions", row_count=500000),
        ],
        columns={
            "customers": [
                Column(name="id", type="int", distribution_params={"min": 1, "max": 25000}, unique=True),
                Column(name="name", type="text", distribution_params={"text_type": "name"}),
                Column(name="email", type="text", distribution_params={"text_type": "email"}),
                Column(name="phone", type="text", distribution_params={"text_type": "phone"}),
                Column(name="created_at", type="date", distribution_params={"start": "2018-01-01", "end": "2024-12-31"}),
                Column(name="risk_score", type="int", distribution_params={"distribution": "normal", "mean": 30, "std": 20, "min": 0, "max": 100}),
                Column(name="is_verified", type="boolean", distribution_params={"probability": 0.92}),
            ],
            "accounts": [
                Column(name="id", type="int", distribution_params={"min": 1, "max": 35000}, unique=True),
                Column(name="customer_id", type="foreign_key", distribution_params={}),
                Column(name="account_type_id", type="foreign_key", distribution_params={}),
                Column(name="balance", type="float", distribution_params={"distribution": "exponential", "scale": 5000, "min": 0, "decimals": 2}),
                Column(name="opened_date", type="date", distribution_params={"start": "2018-01-01", "end": "2024-12-31"}),
                Column(name="is_active", type="boolean", distribution_params={"probability": 0.88}),
            ],
            "transactions": [
                Column(name="id", type="int", distribution_params={"min": 1, "max": 500000}, unique=True),
                Column(name="account_id", type="foreign_key", distribution_params={}),
                Column(name="transaction_type_id", type="foreign_key", distribution_params={}),
                Column(name="amount", type="float", distribution_params={"distribution": "exponential", "scale": 150, "min": 0.01, "decimals": 2}),
                Column(name="timestamp", type="datetime", distribution_params={"start": "2024-01-01", "end": "2024-12-31"}),
                Column(name="merchant", type="text", distribution_params={"text_type": "company"}),
                Column(name="is_fraud", type="boolean", distribution_params={"probability": 0.012}),  # 1.2% fraud rate
            ],
        },
        relationships=[
            Relationship(parent_table="customers", child_table="accounts", parent_key="id", child_key="customer_id"),
            Relationship(parent_table="account_types", child_table="accounts", parent_key="id", child_key="account_type_id"),
            Relationship(parent_table="accounts", child_table="transactions", parent_key="id", child_key="account_id"),
            Relationship(parent_table="transaction_types", child_table="transactions", parent_key="id", child_key="transaction_type_id"),
        ],
    )
