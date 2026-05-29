import streamlit as st
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import init_db
from views.chat_page import render_chat


init_db()
st.set_page_config(page_title="Chat", page_icon="💬", layout="wide")
render_chat()
