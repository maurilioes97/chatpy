import os

from dotenv import load_dotenv

load_dotenv()

# Caminhos
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
EQUIPMENT_FILES_DIR = os.path.join(DATA_DIR, "equipment_files")

# Configuracoes da aplicacao
APP_NAME = "ChatPy - Estudos para concursos"
APP_DESCRIPTION = "Seu assistente inteligente com IA para provas, gabaritos e simulados"

# Configuracoes Streamlit
STREAMLIT_CONFIG = {
    "page_title": APP_NAME,
    "page_icon": "🤖",
    "layout": "wide",
    "initial_sidebar_state": "expanded",
}

# Configuracoes dos providers de IA
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "1200"))
DIRECT_STUDY_RESOLVER_ENABLED = os.getenv("DIRECT_STUDY_RESOLVER_ENABLED", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
