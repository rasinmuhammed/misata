import streamlit as st
from datetime import datetime

class StudioStore:
    """Centralized state management for Misata Studio."""
    
    @staticmethod
    def init():
        """Initialize all session state variables with smart defaults."""
        defaults = {
            # Navigation
            "active_tab": "Schema",
            "sidebar_expanded": True,
            
            # Data & Schema
            "schema_config": None,
            "schema_source": "Template", # "Template" or "AI"
            "warehouse_schema": {
                "type": "service_company",
                "customer_count": 500,
                "project_count": 2000
            },
            
            # Constraint Configuration
            "selected_constraint": None, # e.g. "invoices.amount"
            "warehouse_curve": [100000] * 12, # Default annual curve
            "start_date_input": datetime.now().date(),
            
            # Generation Config
            "warehouse_config": {
                "avg_transaction": 50.0,
                "seed": 42,
                "tier_distribution": [0.5, 0.3, 0.2]
            },
            
            # Results
            "generated_warehouse": None,
            "warehouse_generated": False
        }
        
        for key, default_val in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = default_val

    @staticmethod
    def get(key, default=None):
        return st.session_state.get(key, default)

    @staticmethod
    def set(key, value):
        st.session_state[key] = value

    @property
    def schema(self):
        return st.session_state.get("schema_config")
