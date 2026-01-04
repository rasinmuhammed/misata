import streamlit as st

def apply_custom_styles():
    """Apply the premium 'Botanical Sage' theme and architectural overrides."""
    st.markdown("""
    <style>
    /* ============ VARIABLES ============ */
    :root {
        --sage-bg: #F4F7F5;
        --sage-dark: #2A3B30;
        --sage-hunter: #344E41;
        --sage-fern: #588157;
        --sage-mint: #A3B18A;
        --sage-pale: #DAD7CD;
        
        --text-primary: #1A1C1A;
        --text-secondary: #4A524A;
        --text-tertiary: #849685;
        
        --card-bg: #FFFFFF;
        --border-default: #E2E8E2;
        --shadow-sm: 0 1px 2px rgba(42, 59, 48, 0.05);
        --shadow-md: 0 4px 6px -1px rgba(42, 59, 48, 0.08);
        --font-display: 'Instrument Serif', serif;
        --font-body: 'Inter', sans-serif;
        --font-mono: 'JetBrains Mono', monospace;
    }
    
    /* ============ GLOBAL RESET ============ */
    .stApp {
        background-color: var(--sage-bg);
        font-family: var(--font-body);
        color: var(--text-primary);
    }
    
    /* Override Sidebar */
    [data-testid="stSidebar"] {
        background-color: var(--sage-hunter);
        border-right: 1px solid var(--sage-dark);
    }
    
    /* Force White Text in Sidebar */
    section[data-testid="stSidebar"] p, 
    section[data-testid="stSidebar"] span, 
    section[data-testid="stSidebar"] div, 
    section[data-testid="stSidebar"] label {
        color: #FFFFFF !important;
    }
    
    /* Restore header but transparent */
    header { 
        visibility: visible !important;
        background: transparent !important;
    }
    .header-decoration { visibility: hidden; }

    /* ===== SIDEBAR TOGGLE (Locked Open) ===== */
    [data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"] {
        display: none !important;
    }
    
    /* ============ TYPOGRAPHY ============ */
    @import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&family=Pinyon+Script&display=swap');
    
    h1, h2, h3 { font-family: var(--font-body); letter-spacing: -0.02em; }
    h3 {
        font-family: 'Cormorant Garamond', serif !important;
        color: var(--text-primary) !important;
        font-weight: 500 !important;
    }

    /* ============ COMPONENT: LOGO ============ */
    .brand-logo {
        font-family: 'Pinyon Script', cursive;
        font-size: 2.8rem;
        color: #FFFFFF !important;
        text-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 0.5rem;
    }
    
    /* ============ COMPONENT: SCHEMA NODE ============ */
    .schema-node {
        background: white;
        border: 1px solid var(--border-default);
        border-radius: 8px;
        padding: 1rem;
        box-shadow: var(--shadow-sm);
        margin-bottom: 1rem;
        transition: all 0.2s ease;
        border-left: 3px solid var(--sage-mint);
    }
    .schema-node:hover {
        transform: translateY(-2px);
        box-shadow: var(--shadow-md);
        border-color: var(--sage-mint);
    }
    .node-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.75rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid var(--border-default);
    }
    .node-title {
        font-family: var(--font-mono);
        color: var(--sage-hunter);
        font-weight: 600;
        font-size: 0.95rem;
        background: rgba(52, 78, 65, 0.05);
        padding: 2px 6px;
        border-radius: 4px;
    }
    .node-badge {
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: var(--sage-fern);
        background: rgba(88, 129, 87, 0.1);
        padding: 2px 6px;
        border-radius: 99px;
        font-weight: 600;
    }
    
    /* ============ COMPONENT: BUTTONS ============ */
    .stButton button {
        border-radius: 6px;
        font-weight: 500;
        transition: all 0.2s;
    }
    /* Primary Button override */
    .stButton button[kind="primary"] {
        background: linear-gradient(135deg, var(--sage-hunter) 0%, #2A3B30 100%);
        border: none;
        box-shadow: 0 2px 8px rgba(52, 78, 65, 0.2);
    }
    .stButton button[kind="primary"]:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(52, 78, 65, 0.3);
    }

    </style>
    """, unsafe_allow_html=True)
