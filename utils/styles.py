GLOBAL_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');
    
    /* Typography & Core Variables */
    .stApp, .stMarkdown, .stText, p, h1, h2, h3, label, .stButton button, .stSelectbox div, .stMultiSelect div, .stTextArea textarea, .stTextInput input {
        font-family: 'Outfit', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    }
    
    /* Soft Gridded Background */
    .main { 
        background-color: #f8fafc; 
        background-image: radial-gradient(#e2e8f0 1px, transparent 1px);
        background-size: 24px 24px;
    }
    
    /* Full Dashboard Container Card */
    .block-container {
        background-color: #ffffff;
        border-radius: 20px;
        box-shadow: 0 10px 40px -10px rgba(15, 23, 42, 0.15), 0 4px 6px -4px rgba(15, 23, 42, 0.1);
        border: 1px solid rgba(226, 232, 240, 0.8);
        margin-top: 2rem;
        margin-bottom: 2rem;
        padding-top: 2.5rem !important;
        padding-bottom: 2.5rem !important;
        transition: box-shadow 0.4s ease;
    }
    .block-container:hover {
        box-shadow: 0 20px 50px -10px rgba(15, 23, 42, 0.25), 0 10px 15px -3px rgba(15, 23, 42, 0.1);
    }
    
    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #eef4fb 0%, #f1f5f9 100%);
        border-right: 1px solid #dde6f0;
    }
    [data-testid="stSidebarContent"] { padding-top: 0 !important; }
    section[data-testid="stSidebar"] > div:first-child { padding-top: 0 !important; }
    [data-testid="stSidebar"] * { color: #334155 !important; font-size: 15.5px !important; }
    [data-testid="stSidebar"] h1, 
    [data-testid="stSidebar"] h2, 
    [data-testid="stSidebar"] h3 { color: #0f172a !important; }
    [data-testid="stSidebar"] .stButton>button {
        background: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        color: #334155 !important;
        font-size: 15.5px !important;
        width: 100%;
    }
    [data-testid="stSidebar"] .stButton>button:hover {
        background: #e0eaf6 !important;
        border-color: #93c5fd !important;
        color: #1e40af !important;
        transform: translateY(-1px);
    }
    [data-testid="stSidebar"] [data-baseweb="textarea"], 
    [data-testid="stSidebar"] [data-baseweb="input"] {
        background: #ffffff !important;
        border-color: #cbd5e1 !important;
        color: #334155 !important;
        border-radius: 8px;
        font-size: 15.5px !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] {
        background: #ffffff !important;
        border: 1px solid #dde6f0 !important;
    }
    [data-testid="stSidebar"] hr { border-color: #dde6f0 !important; }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"] * {
        font-size: 14px !important;
        color: #475569 !important;
    }
    [data-testid="stFileUploaderDropzone"] {
        background: #ffffff !important;
        border: 2px dashed #93c5fd !important;
        border-radius: 10px !important;
    }
    
    /* Premium Header */
    .premium-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 50%, #3b82f6 100%);
        padding: 12px 24px;
        border-radius: 12px;
        margin-bottom: 16px;
        color: white;
        box-shadow: 0 10px 30px -5px rgba(29, 78, 216, 0.4);
        position: relative;
        overflow: hidden;
    }
    .premium-header::before {
        content: ''; position: absolute; top: -50%; left: -50%; width: 200%; height: 200%;
        background: radial-gradient(circle, rgba(255,255,255,0.08) 0%, transparent 60%);
        pointer-events: none;
    }
    .premium-header h1 {
        margin: 0; color: white !important; display: flex; align-items: center; text-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }
    
    /* Button Aesthetics */
    .stButton>button { 
        border-radius: 10px; 
        font-weight: 600; 
        letter-spacing: 0.3px;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1); 
        border: 1px solid #e2e8f0;
        background-color: #ffffff;
        color: #475569;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }
    .stButton>button:hover { 
        transform: translateY(-2px); 
        box-shadow: 0 8px 16px rgba(0,0,0,0.06); 
        border-color: #3b82f6; 
        color: #2563eb;
    }
    
    /* Primary Action Button */
    .stButton>button[kind="primary"] {
        background: linear-gradient(135deg, #f43f5e 0%, #e11d48 100%);
        color: white !important;
        border: none;
        box-shadow: 0 6px 15px rgba(225, 29, 72, 0.35);
    }
    .stButton>button[kind="primary"]:hover {
        background: linear-gradient(135deg, #fb118e 0%, #be123c 100%);
        box-shadow: 0 10px 25px rgba(225, 29, 72, 0.5);
        color: white !important;
    }
    
    /* Expanders & Containers */
    div[data-testid="stExpander"] {
        border-radius: 12px;
        background: white;
        border: 1px solid #e2e8f0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.03);
        margin-bottom: 15px;
    }
    div[data-testid="stExpander"] div[role="button"] {
        padding: 5px 15px;
    }
    div[data-testid="stExpander"] div[role="button"]:hover {
        background-color: #f8fafc;
    }
    
    /* AgGrid Enhancements */
    .ag-theme-alpine {
        --ag-border-color: #e2e8f0;
        --ag-header-background-color: #f8fafc;
        --ag-row-hover-color: #eff6ff;
        --ag-font-family: 'Outfit';
        --ag-cell-horizontal-border: solid #e2e8f0;
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid #e2e8f0;
        box-shadow: 0 6px 12px rgba(0,0,0,0.04);
    }
    .ag-theme-alpine .ag-cell {
        border-right: 1px solid #e2e8f0 !important;
    }
    .ag-theme-alpine .ag-header-cell {
        border-right: 1px solid #cbd5e1 !important;
    }
    
    /* Multiselect Tags */
    span[data-baseweb="tag"] {
        background-color: #f43f5e !important;
        color: white !important;
        border-radius: 6px !important;
    }
    span[data-baseweb="tag"] span { color: white !important; }
    
    /* Custom Headings */
    h1, h2, h3 { color: #0f172a; font-weight: 700; letter-spacing: -0.5px; }
</style>
"""
