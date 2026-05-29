import streamlit as st
from pathlib import Path
import sys

# Adiciona src ao path para importacoes
sys.path.insert(0, str(Path(__file__).parent))

from models.database import init_db
from utils.config import STREAMLIT_CONFIG
from views.home import render_home


init_db()
st.set_page_config(**STREAMLIT_CONFIG)

# Mantem o fluxo principal no multipage do Streamlit.
if "user_id" in st.session_state:
    st.switch_page("pages/chat_page.py")
else:
    render_home()
