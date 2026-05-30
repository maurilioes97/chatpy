import os

from dotenv import load_dotenv

load_dotenv()

# Caminhos
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

# Configuracoes da aplicacao
APP_NAME = "ChatPy - Assistente inteligente IA"
APP_DESCRIPTION = "Seu assistente inteligente com IA Gemini"

# Configuracoes Streamlit
STREAMLIT_CONFIG = {
    "page_title": APP_NAME,
    "page_icon": "🤖",
    "layout": "wide",
    "initial_sidebar_state": "expanded",
}

# Configuracoes Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
