import streamlit as st
from misata.studio.state.store import StudioStore

def render_configure_tab():
    """Render the configuration tab."""
    st.markdown("#### Generation Configuration")
    
    config = StudioStore.get('warehouse_config', {})
    
    col1, col2 = st.columns(2)
    
    with col1:
        avg_txn = st.number_input(
            "Avg Transaction Value ($)", 
            min_value=1.0, 
            value=config.get('avg_transaction', 50.0),
            help="Average value of a single invoice/transaction"
        )
        config['avg_transaction'] = avg_txn
        
    with col2:
        seed = st.number_input(
            "Random Seed", 
            min_value=1, 
            value=config.get('seed', 42),
            help="Fixed seed for reproducibility"
        )
        config['seed'] = seed
        
    st.markdown("#### Tier Distribution")
    st.caption("Distribution of Customer Segments")
    
    c1, c2, c3 = st.columns(3)
    defaults = config.get('tier_distribution', [0.5, 0.3, 0.2])
    
    with c1:
        tier_basic = st.slider("Basic %", 0, 100, int(defaults[0]*100))
    with c2:
        tier_pro = st.slider("Pro %", 0, 100, int(defaults[1]*100))
    with c3:
        tier_enterprise = st.slider("Enterprise %", 0, 100, int(defaults[2]*100))
        
    config['tier_distribution'] = [tier_basic/100, tier_pro/100, tier_enterprise/100]
    StudioStore.set('warehouse_config', config)
    
    # NEXT BUTTON (Bottom of Tab)
    st.markdown("<br><br>", unsafe_allow_html=True)
    if st.button("Next: Generate Data →", type="primary", use_container_width=True):
         StudioStore.set('active_tab', "Generate")
         st.rerun()
