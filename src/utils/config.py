import os
from dotenv import load_dotenv

load_dotenv()

# Configurações da aplicação
APP_NAME = "ChatBot Gemini"
APP_DESCRIPTION = "Seu assistente inteligente com IA Gemini"

# Configurações Streamlit
STREAMLIT_CONFIG = {
    "page_title": APP_NAME,
    "page_icon": "🤖",
    "layout": "wide",
    "initial_sidebar_state": "expanded"
}

# Configurações Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Caminhos
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")