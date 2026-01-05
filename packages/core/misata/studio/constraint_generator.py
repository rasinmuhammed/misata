"""
Constraint-Driven Data Warehouse Generator

This module generates complete data warehouses where:
1. Dimension tables are generated with specified distributions
2. Fact tables are generated to satisfy outcome constraints (e.g., monthly revenue targets)
3. All foreign key relationships are maintained

Example:
    schema = {
        "customers": {...},  # dimension
        "products": {...},   # dimension
        "orders": {...}      # fact table with revenue constraint
    }
    
    outcome = OutcomeCurve(revenue = [100K, 150K, 200K, ...])
    
    result = generate_constrained_warehouse(schema, outcome)
    # result["orders"] will sum to exactly the outcome curve when grouped by month
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from misata.schema import SchemaConfig
from misata.reference_data import detect_domain, get_reference_data
from misata.studio.outcome_curve import (
    OutcomeCurve, CurvePoint,
    generate_transactions_for_bucket
)
from misata.causal.graph import get_saas_template, CausalGraph
from misata.causal.solver import CausalSolver



@dataclass
class ColumnSpec:
    """Specification for a column's distribution."""
    name: str
    type: str  # "int", "float", "categorical", "text", "date", "boolean", "foreign_key"
    
    # For numeric
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    distribution: str = "uniform"  # "uniform", "normal", "lognormal"
    mean: Optional[float] = None
    std: Optional[float] = None
    
    # For categorical
    choices: Optional[List[str]] = None
    probabilities: Optional[List[float]] = None
    
    # For text
    text_type: str = "name"  # "name", "email", "company", "uuid", etc.
    
    # For foreign_key
    references: Optional[str] = None  # "customers.id"
    
    # For date
    date_start: Optional[datetime] = None
    date_end: Optional[datetime] = None


@dataclass
class TableSpec:
    """Specification for a table."""
    name: str
    row_count: int
    columns: List[ColumnSpec]
    is_fact: bool = False  # True for fact tables that get outcome constraints
    
    # For fact tables
    date_column: Optional[str] = None  # Which column holds the date
    amount_column: Optional[str] = None  # Which column holds the value to constrain
    
    # For reference tables - LLM-generated actual data
    inline_data: Optional[List[Dict[str, Any]]] = None


@dataclass
class OutcomeConstraint:
    """An outcome constraint for a metric."""
    metric_name: str  # e.g., "revenue", "orders", "signups"
    fact_table: str  # Which table to constrain
    value_column: str  # Which column to sum (e.g., "amount")
    date_column: str  # Which column has the date
    outcome_curve: OutcomeCurve  # The target values


@dataclass
class WarehouseSpec:
    """Complete specification for a data warehouse."""
    tables: List[TableSpec]
    constraints: List[OutcomeConstraint] = field(default_factory=list)


class ConstrainedWarehouseGenerator:
    """Generates complete data warehouses with outcome constraints."""
    
    def __init__(self, spec: WarehouseSpec, seed: int = 42):
        self.spec = spec
        self.rng = np.random.default_rng(seed)
        self.generated_tables: Dict[str, pd.DataFrame] = {}
        
        # Auto-detect domain from table names
        table_names = [t.name for t in spec.tables]
        self.domain = detect_domain(table_names)

        # Causal Engine Integration
        self.causal_graph: Optional[CausalGraph] = None
        self.causal_mapping: Dict[str, str] = {} # GraphNode -> TableName
        self._detect_and_setup_causal()

    def _detect_and_setup_causal(self):
        """Attempts to map the current schema to a Causal Template (SaaS)."""
        # Try SaaS Template
        # Node Map: Traffic, Leads, Deals, Revenue
        mapping = {}
        tables = {t.name.lower(): t.name for t in self.spec.tables}
        
        # Heuristic mapping
        # 1. Traffic
        for kw in ['traffic', 'visits', 'sessions']:
            matching = [real for low, real in tables.items() if kw in low]
            if matching:
                mapping["Traffic"] = matching[0]
                break
        
        # 2. Leads
        for kw in ['leads', 'signups', 'users', 'registrations']:
            matching = [real for low, real in tables.items() if kw in low]
            if matching:
                mapping["Leads"] = matching[0]
                break
                
        # 3. Deals/Revenue (Often same table, e.g. Invoices or Subscriptions)
        for kw in ['deals', 'orders', 'subscriptions', 'invoices', 'sales']:
            matching = [real for low, real in tables.items() if kw in low]
            if matching:
                mapping["Deals"] = matching[0]
                mapping["Revenue"] = matching[0] # Revenue is usually a column in Deals
                break
        
        # If we have at least Traffic and Revenue/Deals, we can use the graph
        if "Traffic" in mapping and "Revenue" in mapping:
            self.causal_graph = get_saas_template()
            self.causal_mapping = mapping
            print(f"✅ Causal Engine Activated: Mapped to SaaS Template ({mapping})")

    
    def generate_all(self) -> Dict[str, pd.DataFrame]:
        """Generate all tables in the warehouse."""
        
        # 1. Try Causal Generation first if activated
        if self.causal_graph and self.spec.constraints:
            try:
                self._generate_causal_flow()
                # If successful, we still need to generate dimensions and fill remaining columns
                # The causal flow populates 'self.generated_tables' with the core rows.
            except Exception as e:
                print(f"⚠️ Causal Generation Failed: {e}. Falling back to stochastic.")
        
        # 2. Separate dimension tables from fact tables
        dimension_tables = [t for t in self.spec.tables if not t.is_fact]
        fact_tables = [t for t in self.spec.tables if t.is_fact]
        
        # 3. Generate dimension tables (if not already generated by Causal Engine)
        for table in dimension_tables:
            if table.name in self.generated_tables:
                continue
            self.generated_tables[table.name] = self._generate_dimension_table(table)
        
        # 4. Generate fact tables with constraints (if not already generated)
        for table in fact_tables:
            if table.name in self.generated_tables:
                continue
            # Find constraint for this table
            constraint = next(
                (c for c in self.spec.constraints if c.fact_table == table.name),
                None
            )
            self.generated_tables[table.name] = self._generate_fact_table(table, constraint)
        
        return self.generated_tables

    def _generate_causal_flow(self):
        """
        Executes the Causal Solver to generate consistent data across tables.
        """
        if not self.causal_graph or not self.spec.constraints:
            return

        # 1. Extract Constraints
        # We need to map 'Revenue' (Graph Node) to the specific Constraint Value
        target_constraints = {}
        
        for constraint in self.spec.constraints:
            # Check if this constraint applies to a mapped node
            # Mapped: Revenue -> Table 'invoices'
            # Constraint: Table 'invoices', Metric 'revenue'
            
            # Find which node maps to this table
            mapped_node = None
            for node, table_name in self.causal_mapping.items():
                if table_name == constraint.fact_table:
                     # Check if metric matches (Revenue vs Deals)
                     if node == "Revenue" and constraint.metric_name.lower() in ['revenue', 'amount', 'sales']:
                         mapped_node = "Revenue"
                     elif node == "Deals" and constraint.metric_name.lower() in ['count', 'orders', 'deals', 'volume']:
                         mapped_node = "Deals"
            
            if mapped_node:
                # Extract simple curve array (assuming monthly for now or resampling)
                # For simplicity in this v1, using the raw points values
                values = [p.value for p in constraint.outcome_curve.points]
                target_constraints[mapped_node] = np.array(values)

        if not target_constraints:
            return # No relevant constraints for the graph

        # 2. Solve
        solver = CausalSolver(self.causal_graph)
        # solve for Traffic if Revenue is constrained
        adjustable = ["Traffic"] 
        
        solved_inputs = solver.solve(target_constraints, adjustable_nodes=adjustable)
        
        # 3. Forward Pass to get all node values
        # Add defaults for conversion rates (exogenous)
        # TODO: Get these from "Fact Injection" in Phase 7
        full_inputs = solved_inputs.copy()
        sample_size = len(list(target_constraints.values())[0])
        full_inputs["LeadConversion"] = np.ones(sample_size) * 0.05 # 5% conversion
        full_inputs["SalesConversion"] = np.ones(sample_size) * 0.20 # 20% conversion
        full_inputs["AOV"] = np.ones(sample_size) * 100.0 # $100 AOV
        
        # If Revenue was constrained, AOV might need to shift if we want to hit it exactly with integer deals?
        # For now, CausalSolver solved for Traffic assuming these defaults (if we set them in solver).
        # Actually in solver.py we defaulted to 1.0. 
        # WE NEED TO MATCH DEFAULTS.
        # Let's fix solver usage later to be robust. For now, assuming defaults.
        
        # Re-run forward pass with our specific defaults
        final_nodes = self.causal_graph.forward_pass(full_inputs) # dict of node -> array
        
        # 4. Generate Tables from Node Arrays
        # Traffic Node -> Traffic Table
        if "Traffic" in self.causal_mapping:
            t_name = self.causal_mapping["Traffic"]
            self.generated_tables[t_name] = self._generate_table_from_curve(t_name, final_nodes["Traffic"])
            
        # Leads Node -> Leads Table
        if "Leads" in self.causal_mapping:
            t_name = self.causal_mapping["Leads"]
            if t_name not in self.generated_tables: # Avoid overwrite if same table
                 self.generated_tables[t_name] = self._generate_table_from_curve(t_name, final_nodes["Leads"])

        # Deals/Revenue Node -> Fact Table
        if "Deals" in self.causal_mapping:
             t_name = self.causal_mapping["Deals"]
             # If table is already generated (Traffic=Leads=Deals in one table?), handle merge.
             # Assuming distinct tables or overwriting for now.
             self.generated_tables[t_name] = self._generate_table_from_curve(t_name, final_nodes["Deals"], revenue_array=final_nodes.get("Revenue"))

    def _generate_table_from_curve(self, table_name: str, count_array: np.ndarray, revenue_array: Optional[np.ndarray] = None) -> pd.DataFrame:
        """Generates a table where row counts per bucket match the count_array."""
        table_spec = next(t for t in self.spec.tables if t.name == table_name)
        
        # Assuming monthly buckets for now (from Constraints)
        # We need start date.
        start_date = datetime.now() - timedelta(days=365) # Default
        
        all_rows = []
        for i, count in enumerate(count_array):
            bucket_start = start_date + timedelta(days=30*i)
            num_rows = int(max(0, count)) # Ensure integer and non-negative
            
            # Generate Basic Columns
            data = {}
            for col in table_spec.columns:
                data[col.name] = self._generate_column(col, num_rows)
            
            df = pd.DataFrame(data)
            
            # Override Date
            if table_spec.date_column:
                 # Spread randomly within month
                 offsets = self.rng.integers(0, 30, num_rows)
                 dates = [bucket_start + timedelta(days=int(o)) for o in offsets]
                 df[table_spec.date_column] = dates

            # Override Revenue if provided
            if revenue_array is not None and table_spec.amount_column and num_rows > 0:
                 # Distribute total revenue among rows
                 total_rev = revenue_array[i]
                 # Simple average for now: total / count
                 avg_rev = total_rev / num_rows
                 # Add some noise
                 revs = self.rng.normal(avg_rev, avg_rev * 0.1, num_rows)
                 # Correct sum
                 revs = revs * (total_rev / revs.sum())
                 df[table_spec.amount_column] = revs

            all_rows.append(df)

        final_df = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()
         # Add ID
        if 'id' not in final_df.columns and len(final_df) > 0:
            final_df.insert(0, 'id', range(1, len(final_df) + 1))
            
        return final_df

    
    def _generate_dimension_table(self, table: TableSpec) -> pd.DataFrame:
        """Generate a dimension table with specified distributions."""
        
        # Priority 1: Use inline_data if provided (from LLM)
        if table.inline_data:
            df = pd.DataFrame(table.inline_data)
            self.generated_tables[table.name] = df
            return df
        
        # Priority 2: Use domain-aware reference library
        library_data = get_reference_data(self.domain, table.name)
        if library_data:
            df = pd.DataFrame(library_data)
            self.generated_tables[table.name] = df
            return df
        
        # Priority 3: Generate from column specs with smart awareness
        data = {}
        
        for col in table.columns:
            data[col.name] = self._generate_column(col, table.row_count)
        
        df = pd.DataFrame(data)
        
        # Add ID if not present
        if 'id' not in df.columns:
            df.insert(0, 'id', range(1, len(df) + 1))
        
        return df
    
    def _generate_fact_table(
        self, 
        table: TableSpec, 
        constraint: Optional[OutcomeConstraint]
    ) -> pd.DataFrame:
        """Generate a fact table, optionally with outcome constraints."""
        
        if constraint is None:
            # No constraint - just generate normally
            return self._generate_dimension_table(table)
        
        # With constraint: use the outcome curve to generate rows
        curve = constraint.outcome_curve
        n_periods = len(curve.points)
        
        # Determine bucket duration
        if curve.time_unit == "day":
            bucket_delta = timedelta(days=1)
        elif curve.time_unit == "week":
            bucket_delta = timedelta(weeks=1)
        else:
            bucket_delta = timedelta(days=30)
        
        all_rows = []
        
        for i, point in enumerate(curve.points):
            bucket_start = point.timestamp
            bucket_end = bucket_start + bucket_delta
            
            # Generate transactions for this bucket
            bucket_df = generate_transactions_for_bucket(
                target_value=point.value,
                bucket_start=bucket_start,
                bucket_end=bucket_end,
                avg_transaction=50.0,  # Could be configurable
                rng=self.rng
            )
            
            # Add other columns
            for col in table.columns:
                if col.name == constraint.date_column:
                    # Date column already generated as 'timestamp'
                    bucket_df[col.name] = bucket_df['timestamp']
                elif col.name == constraint.value_column:
                    # Amount column already generated as 'amount'
                    bucket_df[col.name] = bucket_df['amount']
                elif col.type == "foreign_key" and col.references:
                    # Link to dimension table
                    ref_table, ref_col = col.references.split('.')
                    if ref_table in self.generated_tables:
                        fk_values = self.generated_tables[ref_table][ref_col].values
                        bucket_df[col.name] = self.rng.choice(fk_values, size=len(bucket_df))
                else:
                    # Generate other columns
                    bucket_df[col.name] = self._generate_column(col, len(bucket_df))
            
            # Clean up temp columns
            if 'timestamp' in bucket_df.columns and 'timestamp' != constraint.date_column:
                bucket_df = bucket_df.drop('timestamp', axis=1)
            if 'amount' in bucket_df.columns and 'amount' != constraint.value_column:
                bucket_df = bucket_df.drop('amount', axis=1)
            
            all_rows.append(bucket_df)
        
        # Combine all periods
        df = pd.concat(all_rows, ignore_index=True)
        
        # Add ID if not present
        if 'id' not in df.columns:
            df.insert(0, 'id', range(1, len(df) + 1))
        
        return df
    
    def _generate_column(self, col: ColumnSpec, size: int) -> np.ndarray:
        """Generate values for a single column."""
        col_name_lower = col.name.lower()
        
        if col.type == "int":
            if col.distribution == "normal":
                mean = col.mean or (col.min_val + col.max_val) / 2
                std = col.std or (col.max_val - col.min_val) / 6
                values = self.rng.normal(mean, std, size)
                values = np.clip(values, col.min_val, col.max_val)
                return values.astype(int)
            else:  # uniform
                return self.rng.integers(col.min_val or 0, col.max_val or 100, size)
        
        elif col.type == "float":
            # Smart price detection
            if any(kw in col_name_lower for kw in ['price', 'cost', 'amount', 'fee']):
                # Generate realistic price tiers
                price_tiers = [0.0, 9.99, 14.99, 19.99, 29.99, 49.99, 99.99, 199.99]
                return self.rng.choice(price_tiers, size=size)
            elif col.distribution == "normal":
                mean = col.mean or ((col.min_val or 0) + (col.max_val or 100)) / 2
                std = col.std or ((col.max_val or 100) - (col.min_val or 0)) / 6
                values = self.rng.normal(mean, std, size)
                return np.clip(values, col.min_val or 0, col.max_val or 100)
            elif col.distribution == "lognormal":
                values = self.rng.lognormal(col.mean or 0, col.std or 1, size)
                if col.max_val:
                    values = np.clip(values, col.min_val or 0, col.max_val)
                return values
            else:  # uniform
                return self.rng.uniform(col.min_val or 0, col.max_val or 100, size)
        
        elif col.type == "categorical":
            choices = col.choices or ["A", "B", "C"]
            probs = col.probabilities
            if probs:
                probs = np.array(probs) / sum(probs)  # Normalize
            return self.rng.choice(choices, size=size, p=probs)
        
        elif col.type == "boolean":
            prob = col.probabilities[0] if col.probabilities else 0.5
            return self.rng.random(size) < prob
        
        elif col.type == "date":
            start = col.date_start or datetime.now() - timedelta(days=365)
            end = col.date_end or datetime.now()
            start_ts = start.timestamp()
            end_ts = end.timestamp()
            random_ts = self.rng.uniform(start_ts, end_ts, size)
            return pd.to_datetime(random_ts, unit='s')
        
        elif col.type == "text":
            # Smart text generation based on column name
            if "category" in col_name_lower or "type" in col_name_lower:
                categories = ["Electronics", "Clothing", "Home & Garden", "Sports", "Books", "Toys", "Health", "Automotive"]
                return self.rng.choice(categories, size=size)
            elif "feature" in col_name_lower or "description" in col_name_lower:
                features = ["Premium Support", "Advanced Analytics", "Custom Reports", "API Access", "Priority Queue", "Unlimited Storage", "24/7 Support"]
                return self.rng.choice(features, size=size)
            elif "status" in col_name_lower:
                statuses = ["active", "pending", "completed", "cancelled", "on_hold"]
                return self.rng.choice(statuses, size=size)
            elif "plan" in col_name_lower or "tier" in col_name_lower:
                plans = ["Free", "Basic", "Pro", "Premium", "Enterprise"]
                return self.rng.choice(plans, size=size)
            elif col.text_type == "email":
                return [f"user{i}@example.com" for i in self.rng.integers(1000, 9999, size)]
            elif col.text_type == "uuid":
                import uuid
                return [str(uuid.uuid4()) for _ in range(size)]
            elif col.text_type == "company":
                companies = ["Acme Inc", "TechCorp", "GlobalSoft", "DataDrive", "CloudBase", "ByteForge", "NexGen Systems"]
                return self.rng.choice(companies, size=size)
            else:  # name
                first = ["John", "Jane", "Bob", "Alice", "Charlie", "Diana", "Eve", "Frank", "Grace", "Henry"]
                last = ["Smith", "Jones", "Brown", "Wilson", "Taylor", "Davis", "Clark", "Moore", "Anderson"]
                return [f"{self.rng.choice(first)} {self.rng.choice(last)}" for _ in range(size)]
        
        elif col.type == "foreign_key" and col.references:
            ref_table, ref_col = col.references.split('.')
            if ref_table in self.generated_tables:
                fk_values = self.generated_tables[ref_table][ref_col].values
                return self.rng.choice(fk_values, size=size)
            return self.rng.integers(1, 100, size)
        
        else:
            return self.rng.integers(1, 100, size)


def generate_constrained_warehouse(
    spec: WarehouseSpec,
    seed: int = 42
) -> Dict[str, pd.DataFrame]:
    """
    Generate a complete data warehouse with outcome constraints.
    
    Args:
        spec: Complete warehouse specification
        seed: Random seed for reproducibility
        
    Returns:
        Dict mapping table names to DataFrames
    """
    generator = ConstrainedWarehouseGenerator(spec, seed)
    return generator.generate_all()


# ============ Quick Builder Functions ============

def create_service_company_schema(
    customer_count: int = 500,
    project_count: int = 2000,
    revenue_curve: Optional[OutcomeCurve] = None
) -> WarehouseSpec:
    """Create a typical service company data warehouse schema."""
    
    customers = TableSpec(
        name="customers",
        row_count=customer_count,
        columns=[
            ColumnSpec(name="id", type="int", min_val=1, max_val=customer_count),
            ColumnSpec(name="name", type="text", text_type="name"),
            ColumnSpec(name="email", type="text", text_type="email"),
            ColumnSpec(name="tier", type="categorical", 
                      choices=["Basic", "Pro", "Enterprise"],
                      probabilities=[0.5, 0.3, 0.2]),
            ColumnSpec(name="created_at", type="date"),
        ]
    )
    
    projects = TableSpec(
        name="projects",
        row_count=project_count,
        columns=[
            ColumnSpec(name="id", type="int", min_val=1, max_val=project_count),
            ColumnSpec(name="customer_id", type="foreign_key", references="customers.id"),
            ColumnSpec(name="name", type="text", text_type="company"),
            ColumnSpec(name="status", type="categorical",
                      choices=["Active", "Completed", "On Hold"],
                      probabilities=[0.6, 0.3, 0.1]),
        ]
    )
    
    invoices = TableSpec(
        name="invoices",
        row_count=10000,  # Will be determined by constraint
        columns=[
            ColumnSpec(name="id", type="int"),
            ColumnSpec(name="project_id", type="foreign_key", references="projects.id"),
            ColumnSpec(name="invoice_date", type="date"),
            ColumnSpec(name="amount", type="float", min_val=100, max_val=10000),
            ColumnSpec(name="status", type="categorical",
                      choices=["Paid", "Pending", "Overdue"],
                      probabilities=[0.7, 0.2, 0.1]),
        ],
        is_fact=True,
        date_column="invoice_date",
        amount_column="amount"
    )
    
    constraints = []
    if revenue_curve:
        constraints.append(OutcomeConstraint(
            metric_name="revenue",
            fact_table="invoices",
            value_column="amount",
            date_column="invoice_date",
            outcome_curve=revenue_curve
        ))
    
    return WarehouseSpec(
        tables=[customers, projects, invoices],
        constraints=constraints
    )


def convert_schema_config_to_spec(
    config: SchemaConfig,
    revenue_curve: Optional[OutcomeCurve] = None
) -> WarehouseSpec:
    """Convert a generic SchemaConfig (e.g. from LLM) to a WarehouseSpec."""
    
    table_specs = []
    fact_table_name = None
    date_col_name = None
    amount_col_name = None
    
    # 1. Identify Fact Table Heuristically (largest table with date + amount)
    # or just pick the one with most rows that isn't reference
    candidate_tables = []
    
    for table_name, columns in config.columns.items():
        # Find table definition
        table_def = next((t for t in config.tables if t.name == table_name), None)
        if not table_def or table_def.is_reference:
            continue
            
        has_date = any(c.type == 'date' for c in columns)
        has_amount = any(c.name in ['amount', 'price', 'total', 'revenue', 'value', 'cost'] and c.type in ['float', 'int'] for c in columns)
        
        if has_date and has_amount:
            candidate_tables.append({
                "name": table_name,
                "rows": table_def.row_count,
                "date_col": next(c.name for c in columns if c.type == 'date'),
                "amount_col": next(c.name for c in columns if c.name in ['amount', 'price', 'total', 'revenue', 'value', 'cost'] and c.type in ['float', 'int'])
            })
    
    # Sort candidates by row count (fact tables are usually largest)
    if candidate_tables:
        candidate_tables.sort(key=lambda x: x["rows"], reverse=True)
        best_candidate = candidate_tables[0]
        fact_table_name = best_candidate["name"]
        date_col_name = best_candidate["date_col"]
        amount_col_name = best_candidate["amount_col"]
    
    # 2. Convert Tables
    for table in config.tables:
        # Skip reference tables if they are just data (generator handles them differently? 
        # No, generator needs specs for everything that isn't purely inline constraint)
        # Actually ConstrainedWarehouseGenerator needs spec for everything to generate it.
        # But if it has inline_data, we might treat it differently? 
        # For now, let's assume we map everything, but reference tables rely on their inline data in the original schema
        # The generator 'generate_constrained_warehouse' builds from scratch.
        # IF IT IS A REFERENCE TABLE, WE SHOULD RESPECT INLINE DATA
        # But TableSpec doesn't strictly support inline data in this version yet.
        # We will map it as best we can.
        
        cols = config.columns.get(table.name, [])
        col_specs = []
        
        for c in cols:
            # Map params
            params = c.distribution_params or {}
            
            spec = ColumnSpec(
                name=c.name,
                type=c.type if c.type != 'foreign_key' else 'foreign_key',
                min_val=params.get('min'),
                max_val=params.get('max'),
                mean=params.get('mean'),
                std=params.get('std'),
                choices=params.get('choices'),
                probabilities=params.get('probabilities'),
                text_type=params.get('text_type', 'word'),
                references=None # We need to resolve this if it's FK
            )
            
            # Resolve FK references logic roughly
            if c.type == 'foreign_key':
                # Try to find relationship
                # This is hard without explicit rels in SchemaConfig sometimes, but SchemaConfig HAS relationships!
                rel = next((r for r in config.relationships if r.child_table == table.name and r.child_key == c.name), None)
                if rel:
                    spec.references = f"{rel.parent_table}.{rel.parent_key}"
            
            col_specs.append(spec)
            
        is_fact = (table.name == fact_table_name)
        
        table_specs.append(TableSpec(
            name=table.name,
            row_count=table.row_count,
            columns=col_specs,
            is_fact=is_fact,
            date_column=date_col_name if is_fact else None,
            amount_column=amount_col_name if is_fact else None,
            inline_data=table.inline_data if table.is_reference and table.inline_data else None
        ))
        
    # 3. Create Constraints
    constraints = []
    if revenue_curve and fact_table_name:
        constraints.append(OutcomeConstraint(
            metric_name="revenue",
            fact_table=fact_table_name,
            value_column=amount_col_name,
            date_column=date_col_name,
            outcome_curve=revenue_curve
        ))
        
    return WarehouseSpec(tables=table_specs, constraints=constraints)
