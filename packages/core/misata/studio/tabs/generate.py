import streamlit as st
from datetime import datetime, timedelta
from misata.studio.state.store import StudioStore
from misata.studio.outcome_curve import OutcomeCurve, CurvePoint
from misata.studio.constraint_generator import (
    create_service_company_schema, generate_constrained_warehouse, convert_schema_config_to_spec
)

def render_generate_tab():
    """Render the generation and export tab."""
    st.markdown("#### Generate Complete Data Warehouse")
    
    # Summary
    schema = StudioStore.get('warehouse_schema', {})
    curve = StudioStore.get('warehouse_curve', [])
    config = StudioStore.get('warehouse_config', {})
    schema_source = StudioStore.get('schema_source', 'Template')
    schema_config = StudioStore.get('schema_config')
    
    schema_name = "Service Company"
    if schema_source == "AI" and schema_config:
        schema_name = schema_config.name
        
    st.markdown(f"""
    **Schema:** {schema_name}  
    **Revenue Periods:** {len(curve)}  
    **Total Target Revenue:** ${sum(curve):,.0f}
    """)
    
    if st.button("Generate Warehouse ▸", type="primary", use_container_width=True):
        with st.spinner("Generating complete data warehouse..."):
            # Build revenue curve
            start_date = datetime.combine(
                StudioStore.get('start_date_input', datetime.now().date()),
                datetime.min.time()
            )
            time_unit_val = "month"  # Simplify for now
            
            revenue_curve = OutcomeCurve(
                metric_name='revenue',
                time_unit=time_unit_val,
                points=[
                    CurvePoint(timestamp=start_date + timedelta(days=30*i), value=v)
                    for i, v in enumerate(curve)
                ],
                avg_transaction_value=config.get('avg_transaction', 50.0)
            )
            
            # Create warehouse spec
            spec = None
            if schema_source == "AI" and schema_config:
                spec = convert_schema_config_to_spec(
                    schema_config,
                    revenue_curve=revenue_curve
                )
            else:
                spec = create_service_company_schema(
                    customer_count=schema.get('customer_count', 500),
                    project_count=schema.get('project_count', 2000),
                    revenue_curve=revenue_curve
                )
            
            # Generate
            result = generate_constrained_warehouse(spec, seed=config.get('seed', 42))
            
            # Store result
            StudioStore.set('generated_warehouse', result)
            StudioStore.set('warehouse_generated', True)
        
        st.success("◆ Data warehouse generated successfully!")
    
    # Show results
    result = StudioStore.get('generated_warehouse')
    if result:
        # Show results
        for table_name, df in result.items():
            st.write(f"**{table_name}** ({len(df):,} rows)")
            st.dataframe(df.head(100), use_container_width=True)
        
        # Dynamic Verification
        # (Simplified for the modular view, but should use spec.constraints)
        # Using heuristic check for now if available
        if "invoices" in result:
             invoices = result['invoices']
             if 'amount' in invoices.columns:
                 total_actual = invoices['amount'].sum()
                 total_expected = sum(curve)
                 match_pct = 100 * total_actual / total_expected if total_expected > 0 else 0
                 
                 st.markdown("#### Verification")
                 col1, col2, col3 = st.columns(3)
                 with col1:
                     st.metric("Target Revenue", f"${total_expected:,.0f}")
                 with col2:
                     st.metric("Actual Revenue", f"${total_actual:,.0f}")
                 with col3:
                     st.metric("Match", f"{match_pct:.2f}%")
        
        # Export
        st.markdown("#### Export")
        
        if st.button("Download All Tables ▼"):
            import io
            import zipfile
            
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                for name, df in result.items():
                    csv_data = df.to_csv(index=False)
                    zf.writestr(f"{name}.csv", csv_data)
            
            st.download_button(
                "Download ZIP",
                zip_buffer.getvalue(),
                file_name="misata_warehouse.zip",
                mime="application/zip"
            )
