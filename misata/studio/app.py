import streamlit as st
from misata.studio.state.store import StudioStore
from misata.studio.utils.styles import apply_custom_styles
from misata.studio.components.sidebar import render_sidebar
from misata.studio.tabs.schema_designer import render_schema_tab
from misata.studio.tabs.outcome_curve import render_outcome_tab
from misata.studio.tabs.configure import render_configure_tab
from misata.studio.tabs.generate import render_generate_tab

# Page Config
st.set_page_config(
    page_title="Misata Studio",
    page_icon="M",
    layout="wide",
    initial_sidebar_state="expanded"
)

def main():
    """Main Orchestrator for Misata Studio."""
    
    # 1. Initialize State & Styles
    StudioStore.init()
    apply_custom_styles()
    
    # 2. Render Sidebar
    render_sidebar()
    
    # 3. Router
    active_tab = StudioStore.get("active_tab", "Schema")
    
    # Content Area
    with st.container():
        if active_tab == "Schema":
            render_schema_tab()
            
        elif active_tab == "Outcome":
            render_outcome_tab()
            
        elif active_tab == "Configure":
            render_configure_tab()
            
        elif active_tab == "Generate":
            render_generate_tab()
            
        else:
            st.error(f"Unknown View: {active_tab}")

if __name__ == "__main__":
    main()
