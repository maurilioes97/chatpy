import streamlit as st
from pathlib import Path
import sys

# Adiciona src ao path para importacoes
sys.path.insert(0, str(Path(__file__).parent))

from models.database import init_db
from utils.config import STREAMLIT_CONFIG


init_db()
st.set_page_config(**STREAMLIT_CONFIG)

pages = [
    st.Page("pages/home_page.py", title="Pagina inicial", icon="🏠", default=True),
    st.Page("pages/equipment_page.py", title="Provas", icon="📝"),
    st.Page("pages/chat_page.py", title="Estudos", icon="💬"),
]

navigation = st.navigation(pages, position="sidebar")
navigation.run()
