# User Master Intelligence

## Features
- **AI Extraction**: Uses OpenAI GPT / Google Gemini to extract user data from Excel, PDF, Word files
- **Local Fallback**: Pure pandas extraction when API keys are exhausted — zero API calls needed
- **Smart Column Mapping**: Auto-detects headers using fuzzy matching and semantic aliases
- **Role Detection**: Supports tick-marked (✓/Yes/√) role columns
- **Duplicate Merge**: Intelligent deduplication across sheets and files
- **AI Assistant**: Post-extraction bulk editing via natural language commands

## Setup
1. Install dependencies: `pip install -r requirements.txt`
2. Add API keys to `.streamlit/secrets.toml`
3. Run: `streamlit run app.py`

## Tech Stack
- Python + Streamlit
- OpenAI / Google Gemini API
- Pandas, PyMuPDF, python-docx
