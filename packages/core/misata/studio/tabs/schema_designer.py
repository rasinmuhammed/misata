import streamlit as st
from misata.studio.state.store import StudioStore
from misata.llm_parser import generate_schema
from misata.studio.components.inspector import render_table_inspector

def render_schema_tab():
    """Render the Schema Designer tab."""
    # Check if we are in Inspector Mode
    if StudioStore.get("selected_table"):
        render_table_inspector()
        # Initial view is the inspector, but we also want to see the schema context?
        # For now, let's keep it simple: Modal-like experience. 
        # Or render inspector at top, schema below.
        st.markdown("---")
    
    st.markdown("#### Schema Designer")
    
    col_controls, col_viz = st.columns([1, 1])
    
    with col_controls:
        # Schema Source Selection
        source_mode = st.radio(
            "Design Mode", 
            ["Template", "AI Story 🧠"], 
            horizontal=True,
            label_visibility="collapsed"
        )
        
        if source_mode == "Template":
            schema_type = st.selectbox(
                "Select Template",
                ["Service Company", "E-commerce Store", "SaaS Platform", "Custom"],
                label_visibility="collapsed"
            )
            
            if schema_type == "Service Company":
                # Initialize default if not present
                warehouse_schema = StudioStore.get('warehouse_schema') or {}
                if not warehouse_schema or warehouse_schema.get('type') != 'service_company':
                     StudioStore.set('warehouse_schema', {
                        "type": "service_company",
                        "customer_count": 500,
                        "project_count": 2000
                    })
        else:
            # AI Story Mode
            schema_type = "AI"
            story = st.text_area(
                "Describe your data needs:",
                placeholder="e.g., A healthcare system with patients, doctors, and appointments...",
                height=100
            )
            if st.button("Generate Schema ✨", type="primary"):
                with st.spinner("consulting the architect..."):
                    try:
                        # Call LLM
                        config = generate_schema(story)
                        StudioStore.set('schema_config', config)
                        StudioStore.set('schema_source', "AI")
                        StudioStore.set('selected_table', None) # Reset selection
                        st.success("Schema generated!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Generation failed: {str(e)}")

    with col_viz:
        st.markdown("""
        <div style="text-align: center; color: var(--text-secondary); padding: 2rem;">
            <div style="font-size: 0.9rem;">Visual Relationship Mapper</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # RENDER AREA
    schema_source = StudioStore.get("schema_source")
    schema_config = StudioStore.get("schema_config")
    
    # 1. AI GENERATED SCHEMA
    if schema_source == "AI" and schema_config:
        st.markdown(f"#### {schema_config.name}")
        st.markdown(f"_{schema_config.description or 'Custom generated schema'}_")
        
        # Grid layout for tables
        cols = st.columns(3)
        for i, table in enumerate(schema_config.tables):
            col = cols[i % 3]
            with col:
                # Badge logic
                badge_color = "var(--sage-hunter)"
                badge_text = "Table"
                bg_style = ""
                
                if table.is_reference:
                    badge_color = "#D4A574" # Gold
                    badge_text = "Reference"
                elif hasattr(table, 'row_count') and table.row_count > 10000:
                    badge_text = "Transactional"
                    bg_style = "border-left-color: var(--sage-hunter); background: rgba(88, 129, 87, 0.05);"
                
                # Check if this table is being edited
                is_selected = (StudioStore.get("selected_table") == table.name)
                if is_selected:
                    bg_style += "border: 2px solid var(--sage-mint); box-shadow: 0 0 10px rgba(88,129,87,0.2);"

                st.markdown(f"""
                <div class="schema-node" style="{bg_style}">
                    <div class="node-header">
                        <span class="node-title">{table.name}</span>
                        <span class="node-badge" style="background:{badge_color}; color:white;">{badge_text}</span>
                    </div>
                """, unsafe_allow_html=True)
                
                # Header Actions: Edit Button
                c_row, c_edit = st.columns([2, 1])
                with c_row:
                    if not table.is_reference:
                        st.caption(f"{table.row_count:,} rows")
                    else:
                        st.caption("Ref Table")
                with c_edit:
                    if st.button("Edit ✎", key=f"edit_{table.name}"):
                        StudioStore.set("selected_table", table.name)
                        st.rerun()

                # Columns preview
                if table.name in schema_config.columns:
                    col_html = ""
                    for col_def in schema_config.columns[table.name][:5]:
                        col_html += f"""
                        <div style="display:flex; justify-content:space-between; margin-bottom:4px; font-size:0.8rem;">
                            <span>{col_def.name}</span><span style="color:var(--text-tertiary);">{col_def.type}</span>
                        </div>
                        """
                    if len(schema_config.columns[table.name]) > 5:
                         col_html += f"<div style='font-size:0.7rem; color:var(--text-tertiary);'>+ {len(schema_config.columns[table.name])-5} more...</div>"
                    
                    st.markdown(f"""
                    <div style="margin-top:0.5rem; padding:0.5rem; background:rgba(255,255,255,0.5); border-radius:4px;">
                        {col_html}
                    </div>
                    """, unsafe_allow_html=True)
                
                st.markdown("</div>", unsafe_allow_html=True)

    # 2. LEGACY TEMPLATE (Service Company)
    elif schema_source == "Template":
        warehouse_schema = StudioStore.get('warehouse_schema')
        col_t1, col_t2, col_t3 = st.columns(3)
        
        with col_t1:
            st.markdown("""
            <div class="schema-node">
                <div class="node-header">
                    <span class="node-title">customers</span>
                    <span class="node-badge">Dimension</span>
                </div>
            """, unsafe_allow_html=True)
            
            customer_count = st.number_input("Rows", 100, 100000, 
                                           warehouse_schema.get('customer_count', 500), 
                                           step=100, key="n_cust")
            st.markdown("<div style='font-size:0.8rem; color:var(--text-secondary); margin-top:0.5rem;'>Attributes: id, name, email, tier, created_at</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
            
        with col_t2:
            st.markdown("""
            <div class="schema-node">
                <div class="node-header">
                    <span class="node-title">projects</span>
                    <span class="node-badge">Dimension</span>
                </div>
            """, unsafe_allow_html=True)
            
            project_count = st.number_input("Rows", 500, 500000, 
                                          warehouse_schema.get('project_count', 2000), 
                                          step=500, key="n_proj")
            st.markdown("<div style='font-size:0.8rem; color:var(--text-secondary); margin-top:0.5rem;'>Attributes: id, customer_id, name, status</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
            
        with col_t3:
            st.markdown("""
            <div class="schema-node" style="border-left-color: var(--sage-hunter); background: rgba(88, 129, 87, 0.05);">
                <div class="node-header">
                    <span class="node-title">invoices</span>
                    <span class="node-badge" style="background:var(--sage-hunter); color:white;">Fact Table</span>
                </div>
            """, unsafe_allow_html=True)
            
            st.markdown("""
            <div style="font-size:0.85rem; font-family:'JetBrains Mono'; margin-bottom:0.5rem;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px; background:rgba(255,255,255,0.5); padding:2px 4px; border-radius:4px;">
                    <span>amount</span>
                    <div style="display:flex; align-items:center; gap:4px;">
                        <span style="color:var(--text-tertiary); font-size:0.8rem;">float</span>
                        <span style="font-size:0.8rem; color:var(--sage-hunter);" title="Has Outcome Constraint">◭</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("Configure Constraint ◭", key="btn_const_inv", use_container_width=True):
                StudioStore.set('active_tab', "Outcome Curve")
                StudioStore.set('selected_constraint', "invoices.amount")
                st.rerun()
            
            st.markdown("</div>", unsafe_allow_html=True)

        # Update state
        warehouse_schema['customer_count'] = customer_count
        warehouse_schema['project_count'] = project_count
    
    # NEXT BUTTON
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Next: Define Outcome Curve →", type="primary", use_container_width=True):
         StudioStore.set('active_tab', "Outcome Curve")
         st.rerun()
