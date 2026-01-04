import streamlit as st
import plotly.graph_objects as go
from misata.studio.state.store import StudioStore
from misata.studio.outcome_curve import get_curve_presets, CurvePoint, OutcomeCurve

def render_outcome_tab():
    """Render the Outcome Constraint configuration tab."""
    st.markdown("#### Define Outcome Constraints")
    
    # Check if a constraint is selected
    selected = StudioStore.get('selected_constraint')
    
    if not selected:
         # In AI mode, let them pick any float column
         schema_source = StudioStore.get('schema_source')
         schema_config = StudioStore.get('schema_config')
         
         if schema_source == "AI" and schema_config:
             st.info("Pick a column to constrain:")
             # List candidate columns
             candidates = []
             for t_name, cols in schema_config.columns.items():
                 for c in cols:
                     if c.type in ['float', 'int'] and c.name in ['amount', 'price', 'total', 'revenue', 'value', 'cost']:
                         candidates.append(f"{t_name}.{c.name}")
            
             if candidates:
                 selected_col = st.selectbox("Column", candidates)
                 if st.button("Add Constraint"):
                     StudioStore.set('selected_constraint', selected_col)
                     st.rerun()
             else:
                 st.warning("No suitable columns found for outcome constraints (need float/int like 'amount').")
                 
         else:
             st.info("👈 Select a numerical column (like **invoices.amount**) from the Schema tab to add a constraint.")
             st.markdown("""
             **What is an Outcome Constraint?**
             It forces the generated data to match a specific aggregated shape over time.
             
             *Example: Draw a revenue curve, and Misata generates millions of transactions that sum up exactly to that curve.*
             """)
         return
    
    st.markdown(f"""
    <div style="background:rgba(52, 78, 65, 0.05); border-left: 3px solid var(--sage-hunter); padding:1rem; border-radius:4px; margin-bottom:2rem;">
        <span style="font-size:0.8rem; text-transform:uppercase; color:var(--text-tertiary);">Active Constraint</span>
        <div style="font-size:1.2rem; font-weight:600; font-family:var(--font-mono); color:var(--sage-hunter);">
            {selected}
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("#### Presets")
        presets = get_curve_presets()
        
        # Current curve state
        current_curve = StudioStore.get('warehouse_curve', [100000] * 12)
        
        selected_preset = st.radio(
            "Shape",
            list(presets.keys()),
            help="Choose a starting shape for your curve"
        )
        
        # Scale
        total_target = st.number_input(
            "Total Target", 
            min_value=1000, 
            value=int(sum(current_curve)), 
            step=10000,
            format="%d"
        )
        
        if st.button("Apply Preset", type="primary", use_container_width=True):
            base_values = presets[selected_preset]
            # Rescale to match target
            current_sum = sum(base_values)
            scale = total_target / current_sum if current_sum > 0 else 1
            
            if selected_preset == "Random Volatility":
                 import random
                 values = [v * scale * random.uniform(0.8, 1.2) for v in base_values]
            else:
                values = [v * scale for v in base_values]
            StudioStore.set('warehouse_curve', values)
                 
        # NEXT BUTTON (Bottom of Tab)
        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("Next: Configure Generation →", type="primary", use_container_width=True):
             StudioStore.set('active_tab', "Configure")
             st.rerun()
    
    with col2:
        st.markdown("#### Shape the Curve")
        
        # Sliders for each month
        curve_points = StudioStore.get('warehouse_curve', [100000] * 12)
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        
        # Interactive chart
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=months,
            y=curve_points,
            marker_color='#588157',
            opacity=0.8
        ))
        
        fig.add_trace(go.Scatter(
            x=months,
            y=curve_points,
            mode='lines+markers',
            line=dict(color='#344E41', width=3, shape='spline'),
            marker=dict(size=8, color='#344E41')
        ))
        
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=20, r=20, t=20, b=20),
            height=300,
            showlegend=False
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("---")
        st.caption("Adjust Monthly Targets")
        
        # 3 columns of 4 sliders
        sc1, sc2, sc3 = st.columns(3)
        cols = [sc1, sc2, sc3]
        
        new_curve = list(curve_points)
        for i, month in enumerate(months):
            with cols[i // 4]:
                new_curve[i] = st.slider(
                    f"{month}", 
                    0, 
                    int(max(curve_points) * 2), 
                    int(new_curve[i]), 
                    key=f"slider_{i}"
                )
        
        StudioStore.set('warehouse_curve', new_curve)
