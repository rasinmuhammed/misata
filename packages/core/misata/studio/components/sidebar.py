import streamlit as st
from misata.studio.state.store import StudioStore

def render_sidebar():
    """Render the sidebar with navigation and branding."""
    with st.sidebar:
        # 1. Branding
        st.markdown('<div class="brand-logo">Misata</div>', unsafe_allow_html=True)
        st.markdown('<p style="font-size: 0.8rem; color: var(--text-tertiary); margin-top: -10px;">SYNTHETIC STUDIO PRO</p>', unsafe_allow_html=True)
        st.markdown("---")
        
        # 2. Navigation
        current_tab = StudioStore.get("active_tab", "Schema")
        
        # Helper for nav buttons
        def nav_button(label, key, icon=""):
            if st.button(f"{label}", key=key, use_container_width=True):
                StudioStore.set("active_tab", label.replace(" Builder", "").replace(" Curve", ""))
                st.rerun()
                
        nav_button("Schema Builder", "nav_schema")
        nav_button("Outcome Curve", "nav_outcome")
        nav_button("Configure", "nav_config")
        nav_button("Generate", "nav_gen")
            
        st.markdown("---")
        
        # 3. Status
        st.markdown("""
        <div style="background: rgba(255,255,255,0.1); padding: 1rem; border-radius: 8px; border: 1px solid rgba(255,255,255,0.1);">
            <div style="font-size: 0.75rem; color: rgba(255,255,255,0.6); text-transform: uppercase; letter-spacing: 0.05em;">Status</div>
            <div style="color: #FFFFFF !important; font-weight: 500; margin-top: 4px;">API Connected</div>
            <div style="font-size: 0.7rem; color: rgba(255,255,255,0.8) !important; margin-top: 4px;">v2.0.0 (World Class)</div>
        </div>
        """, unsafe_allow_html=True)
