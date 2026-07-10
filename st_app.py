import streamlit as st

# Page config must be the first Streamlit command in the script
try:
    st.set_page_config(
        page_title="🌍 Travel Planner — Agentic",
        page_icon="🌍",
        layout="wide",
        initial_sidebar_state="expanded",
    )
except Exception:
    pass

import os
import re
from urllib.parse import urlencode
from dotenv import load_dotenv
from utils.json_store import JsonStore
from utils.save_to_document import save_document, build_pdf_bytes
from utils.user_store import UserStore
import uuid
import datetime
import requests
import streamlit.components.v1 as components

BASE_URL = "http://localhost:8000"

load_dotenv()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8501/")
SCOPES = ["openid", "email", "profile"]
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

USER_DATA_PATH = "data/users.json"
user_store = UserStore(USER_DATA_PATH)

# Control whether sensitive OAuth details are shown in the UI for debugging.
# Set OAUTH_DEBUG=1 in your .env when you explicitly need to debug locally.
OAUTH_DEBUG = os.getenv("OAUTH_DEBUG", "").lower() in ("1", "true", "yes")

base_data = "data/chats.json"
store = JsonStore(base_data)

if "selected_chat" not in st.session_state:
    st.session_state.selected_chat = None
if "pending_chat" not in st.session_state:
    st.session_state.pending_chat = None
if "user" not in st.session_state:
    st.session_state.user = None
if "show_profile" not in st.session_state:
    st.session_state.show_profile = False
if "local_storage_restore_attempted" not in st.session_state:
    st.session_state.local_storage_restore_attempted = False
