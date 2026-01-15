import streamlit as st
from misata.studio.state.store import StudioStore
from misata.schema import Column
import random

def render_table_inspector():
    """Render the detailed inspector panel for the selected table."""
    selected_table_name = StudioStore.get("selected_table")
    schema_config = StudioStore.get("schema_config")
    
    if not selected_table_name or not schema_config:
        return

    # Find the table object
    table = next((t for t in schema_config.tables if t.name == selected_table_name), None)
    if not table:
        return

    with st.expander(f"🛠 Edit Table: {table.name}", expanded=True):
        # 1. Table Properties
        c1, c2 = st.columns([2, 1])
        with c1:
            new_name = st.text_input("Table Name", table.name)
            if new_name != table.name:
                table.name = new_name
                st.rerun()
                
        with c2:
            new_rows = st.number_input("Rows", 1, 1000000, table.row_count)
            table.row_count = new_rows

        st.markdown("---")
        st.markdown("**Columns**")
        
        # 2. Column Editor
        columns = schema_config.columns.get(table.name, [])
        
        # List existing
        for i, col in enumerate(columns):
            with st.container():
                c_name, c_type, c_del = st.columns([3, 2, 1])
                
                with c_name:
                    new_col_name = st.text_input(f"Name", col.name, key=f"cn_{table.name}_{i}", label_visibility="collapsed")
                    col.name = new_col_name
                    
                with c_type:
                    type_options = ["int", "float", "date", "text", "categorical", "boolean", "foreign_key"]
                    new_type = st.selectbox("Type", type_options, index=type_options.index(col.type) if col.type in type_options else 3, key=f"ct_{table.name}_{i}", label_visibility="collapsed")
                    col.type = new_type
                    
                with c_del:
                    if st.button("🗑", key=f"del_{table.name}_{i}"):
                        columns.pop(i)
                        st.rerun()
                        
                # Distribution Tweak (Simple expander for now)
                with st.expander("Distribution Settings", expanded=False):
                    if col.type in ["int", "float"]:
                        min_v = st.number_input("Min", value=float(col.distribution_params.get('min', 0)), key=f"min_{table.name}_{i}")
                        max_v = st.number_input("Max", value=float(col.distribution_params.get('max', 100)), key=f"max_{table.name}_{i}")
                        col.distribution_params['min'] = min_v
                        col.distribution_params['max'] = max_v
                    elif col.type == "categorical":
                        cats = st.text_input("Categories (comma sep)", value=",".join(col.distribution_params.get('choices', [])), key=f"cat_{table.name}_{i}")
                        col.distribution_params['choices'] = [c.strip() for c in cats.split(",")]
        
        # Add New Column Button
        if st.button("+ Add Column", key=f"add_col_{table.name}"):
            new_col = Column(
                name=f"new_column_{len(columns)+1}",
                type="text",
                distribution_params={}
            )
            columns.append(new_col)
            st.rerun()

        # Save/Close
        if st.button("Done Editing", type="primary", use_container_width=True):
            StudioStore.set("selected_table", None)
            st.rerun()
