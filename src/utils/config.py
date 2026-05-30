import os

from dotenv import load_dotenv

load_dotenv()

# Caminhos
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
EQUIPMENT_FILES_DIR = os.path.join(DATA_DIR, "equipment_files")

# Configuracoes da aplicacao
APP_NAME = "ChatPy - Assistente inteligente IA"
APP_DESCRIPTION = "Seu assistente inteligente com IA para manuais tecnicos"

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
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "180"))
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "all-minilm")
EMBEDDINGS_ENABLED = os.getenv("EMBEDDINGS_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}

# Configuracoes de OCR
OCR_ENABLED = os.getenv("OCR_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
OCR_LANGUAGE = os.getenv("OCR_LANGUAGE", "por")
OCR_MIN_TEXT_CHARS = int(os.getenv("OCR_MIN_TEXT_CHARS", "80"))
OCR_RENDER_SCALE = float(os.getenv("OCR_RENDER_SCALE", "2.0"))
OCR_TIMEOUT_SECONDS = int(os.getenv("OCR_TIMEOUT_SECONDS", "45"))
OCR_TESSERACT_CONFIG = os.getenv("OCR_TESSERACT_CONFIG", "--oem 3 --psm 6")
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")
