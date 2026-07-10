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
if "theme" not in st.session_state:
    st.session_state.theme = "dark"

if st.session_state.get("logout_requested"):
    st.session_state.logout_requested = False
    st.session_state.user = None
    st.session_state.selected_chat = None
    st.session_state.pending_chat = None
    st.session_state.show_profile = False
    components.html("""
    <script>
        window.localStorage.removeItem('agentic_user_id');
        const u = new URL(window.parent.location.href);
        u.searchParams.delete('user_id');
        u.searchParams.delete('code');
        u.searchParams.delete('state');
        window.parent.history.replaceState({}, '', u.toString());
        window.parent.location.reload();
    </script>
    """, height=0)
    st.stop()


def get_query_params():
    """Return query params using the stable API when available to avoid deprecation warnings."""
    if hasattr(st, "query_params"):
        return st.query_params
    try:
        return st.experimental_get_query_params()
    except Exception:
        return {}

def set_query_params(**kwargs):
    """Set query params using the stable API when available."""
    if hasattr(st, "set_query_params"):
        try:
            st.set_query_params(**kwargs)
            return
        except Exception:
            pass
    try:
        st.experimental_set_query_params(**kwargs)
    except Exception:
        # best-effort fallback: do nothing
        return

def get_param_from_query(name: str):
    params = get_query_params()
    value = params.get(name)
    if isinstance(value, list):
        return value[0] if value else None
    return value

def restore_user_from_query_params():
    """Restore a logged-in user from a persistent query param after page reload."""
    if st.session_state.get("user") is not None:
        return st.session_state.user
    user_id = get_param_from_query("user_id")
    if not user_id:
        return None
    user = user_store.get_user(user_id)
    if user:
        st.session_state.user = user
    return user

def new_chat(title: str = "New Chat"):
    cid = uuid.uuid4().hex
    now = datetime.datetime.utcnow().isoformat()
    chat = {"id": cid, "title": title, "created_at": now, "updated_at": now, "messages": []}
    st.session_state.pending_chat = chat
    st.session_state.selected_chat = None
    if "chat_to_open" in st.session_state:
        del st.session_state["chat_to_open"]


def make_chat_title(message_text: str) -> str:
    text = message_text.strip()
    if not text:
        return "New Chat"

    text = re.sub(r"[^A-Za-z0-9 ]+", " ", text)
    text = re.sub(r"\b(plan|please|a|an|the|to|for|in|make|me|help|need|travel|trip|book|plan)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "New Chat"

    if len(text) > 40:
        text = text[:40].rsplit(" ", 1)[0]
    title = text.title()
    if not re.search(r"\b(Trip|Plan|Itinerary)\b", title, flags=re.IGNORECASE):
        title = f"{title} Plan"
    return title


def is_generic_title(title: str) -> bool:
    return not title or title.strip().lower() in ["new chat", "untitled"]


def normalize_chat_title(chat: dict) -> str:
    if not is_generic_title(chat.get("title", "")):
        return chat["title"]

    messages = chat.get("messages", [])
    if not messages:
        return chat.get("title", "New Chat")

    first_user = next((m for m in messages if m.get("role") == "user" and m.get("content")), None)
    source_text = first_user.get("content") if first_user else messages[0].get("content", "")
    if not source_text:
        return chat.get("title", "New Chat")

    new_title = make_chat_title(source_text)
    if new_title and new_title != chat.get("title"):
        try:
            store.update_chat_title(chat["id"], new_title)
            chat["title"] = new_title
        except Exception:
            pass
    return chat.get("title", new_title)


def refresh_chats(user_id: str):
    chats = store.list_chats(user_id=user_id)
    for chat in chats:
        normalize_chat_title(chat)
    return chats


def build_google_oauth_url(state: str) -> str:
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return ""
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "select_account consent",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code_for_token(code: str) -> dict:
    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    try:
        resp = requests.post(TOKEN_URL, data=data, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        # Include response body to help debug bad-request errors (redirect_uri mismatch etc.)
        body = None
        try:
            body = resp.text
        except Exception:
            body = str(e)
        raise Exception(f"Token exchange failed: {body}") from e


def fetch_google_userinfo(access_token: str) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(USERINFO_URL, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.json()


def authenticate_with_google():
    code = get_param_from_query("code")
    state = get_param_from_query("state")
    saved_state = st.session_state.get("oauth_state")
    if not code or not state:
        return None
    if not isinstance(code, str) or len(code) < 20:
        st.error("Received an invalid authorization code. This often indicates a redirect URI mismatch, a reused/expired code, or a proxy truncating the URL. \n\nCheck the app redirect URI and try signing in again.")
        st.info("Current redirect URI: " + REDIRECT_URI)
        if OAUTH_DEBUG:
            # Only show the raw client id when debug mode is explicitly enabled.
            st.info("Client ID (debug): " + (GOOGLE_CLIENT_ID or "(not set)"))
        else:
            st.info("Google OAuth is configured.")
        set_query_params()
        components.html("<script>window.history.replaceState({}, document.title, window.location.pathname);</script>", height=0)
        return None
    if " " in code:
        # Streamlit may decode '+' as space when parsing query params.
        st.warning("The authorization code contained spaces, which can happen when '+' is decoded incorrectly. Retrying with normalized code.")
        code = code.replace(" ", "+")
    if saved_state and state != saved_state:
        st.error("Invalid OAuth state. Please try signing in again.")
        set_query_params()
        components.html("<script>window.history.replaceState({}, document.title, window.location.pathname);</script>", height=0)
        return None
    try:
        token_data = exchange_code_for_token(code)
        access_token = token_data.get("access_token")
        if not access_token:
            st.error("Failed to receive an access token from Google.")
            return None
        profile = fetch_google_userinfo(access_token)
        if not profile.get("email"):
            st.error("Google did not return an email address. Please try another account.")
            return None
        user = user_store.get_user_by_email(profile["email"])
        if user is None:
            user = {
                "id": profile.get("sub"),
                "email": profile.get("email"),
                "name": profile.get("name") or profile.get("email"),
                "picture": profile.get("picture"),
                "profile": {"phone": "", "bio": ""},
            }
            user_store.save_user(user)
        else:
            user = user_store.update_user(user["id"], {
                "name": profile.get("name") or user.get("name"),
                "picture": profile.get("picture") or user.get("picture"),
            })
        st.session_state.user = user
        js_code = f"""
        <script>
            window.localStorage.setItem('agentic_user_id', '{user["id"]}');
            const u = new URL(window.parent.location.href);
            u.searchParams.delete('code');
            u.searchParams.delete('state');
            u.searchParams.set('user_id', '{user["id"]}');
            window.parent.history.replaceState({{}}, '', u.toString());
            window.parent.location.reload();
        </script>
        """
        components.html(js_code, height=0)
        st.stop()
    except Exception as e:
        js_code = """
        <script>
            const u = new URL(window.parent.location.href);
            u.searchParams.delete('code');
            u.searchParams.delete('state');
            window.parent.history.replaceState({}, '', u.toString());
            window.parent.location.reload();
        </script>
        """
        components.html(js_code, height=0)
        st.stop()


def logout_user():
    st.session_state.logout_requested = True
    try:
        st.rerun()
    except Exception:
        st.experimental_rerun()


def render_login_page():
    st.title("Welcome to Agentic AI Trip Planner")
    st.markdown("Sign in with Google to continue.")
    OAuth_state = st.session_state.get("oauth_state") or uuid.uuid4().hex
    st.session_state.oauth_state = OAuth_state
    sign_in_url = build_google_oauth_url(OAuth_state)
    # center the button container and use a reliable Google logo
    outer_start = "<div style='display:flex;justify-content:center;margin-top:18px;margin-bottom:12px;'>"
    outer_end = "</div>"
    if sign_in_url:
        inner = (
            "<a href='" + sign_in_url + "' style='text-decoration:none;'>"
            "<div style='display:flex;align-items:center;justify-content:center;padding:12px 18px;border:1px solid #dfe1e5;border-radius:8px;background:#fff;color:#3c4043;cursor:pointer;max-width:360px;'>"
            "<img src='https://developers.google.com/identity/images/g-logo.png' style='width:20px;height:20px;margin-right:12px;' alt='Google logo'/>"
            "<span style='font-size:16px;font-weight:500;'>Login with Google</span>"
            "</div></a>"
        )
    else:
        inner = (
            "<div style='display:flex;align-items:center;justify-content:center;padding:12px 18px;border:1px solid #dfe1e5;border-radius:8px;background:#f8f9fa;color:#888;max-width:360px;'>"
            "<span style='font-size:16px;font-weight:500;'>Google OAuth not configured</span>"
            "</div>"
        )

    st.markdown(outer_start + inner + outer_end, unsafe_allow_html=True)
    if not sign_in_url:
        st.warning("Google OAuth credentials are missing. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to your .env file.")
        st.markdown(
            "<div style='background:#202124;padding:12px;border-radius:6px;color:#fff;'>"
            "<strong>Required .env variables:</strong><br/>"
            "GOOGLE_CLIENT_ID=\"your-client-id\"<br/>"
            "GOOGLE_CLIENT_SECRET=\"your-client-secret\"<br/>"
            "GOOGLE_REDIRECT_URI=\"http://localhost:8501/\""
            "</div>",
            unsafe_allow_html=True,
        )
    st.markdown("---")
    st.info("Only authenticated users can access the Agent. Please sign in with the Google account you want to use.")
    st.stop()


def render_profile_modal():
    if not st.session_state.get("show_profile"):
        return
    user = st.session_state.user
    if not user:
        return
    st.markdown("---")
    st.subheader("Profile")
    name = st.text_input("Name", value=user.get("name") or "")
    email = st.text_input("Email", value=user.get("email") or "", disabled=True)
    phone = st.text_input("Phone", value=user.get("profile", {}).get("phone", ""))
    bio = st.text_area("Bio", value=user.get("profile", {}).get("bio", ""))
    cols = st.columns([1,1])
    if cols[0].button("Save Profile"):
        updates = {"name": name, "profile": {"phone": phone, "bio": bio}}
        user_store.update_user(user["id"], updates)
        st.session_state.user = user_store.get_user(user["id"])
        st.success("Profile updated")
        st.session_state.show_profile = False
    if cols[1].button("Close"):
        st.session_state.show_profile = False


def render_messages(msgs):
    bubble_css = """
    <style>
    .chat-container { max-width: 100%; margin: 0 auto; padding: 0; display: flex; flex-direction: column; gap: 12px; }
    .msg-box { padding: 14px 16px; border-radius: 14px; max-width: 100%; display: inline-block; line-height: 1.5; }
    .user-msg { background: #0b5cff; color: #fff; align-self: flex-end; text-align: right; }
    .assistant-msg { background: #262626; color: #e6e6e6; align-self: flex-start; text-align: left; }
    .meta { margin-top: 6px; font-size: 11px; color: #999; }
    </style>
    """
    st.markdown(bubble_css, unsafe_allow_html=True)
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    for m in msgs:
        role = m.get("role")
        ts = m.get("ts", "")
        content = m.get("content", "")
        if role == "user":
            st.markdown(
                f"<div class='msg-box user-msg'>{content}<div class='meta'>You • {ts}</div></div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div class='msg-box assistant-msg'>{content}<div class='meta'>Assistant • {ts}</div></div>",
                unsafe_allow_html=True,
            )
    st.markdown('</div>', unsafe_allow_html=True)


if st.session_state.user is None:
    restore_user_from_query_params()
if st.session_state.user is None and not st.session_state.local_storage_restore_attempted:
    st.session_state.local_storage_restore_attempted = True
    components.html(
        "<script>const stored = window.localStorage.getItem('agentic_user_id'); if (stored) { const u = new URL(window.location); u.searchParams.set('user_id', stored); window.location.replace(u.toString()); }</script>",
        height=0,
    )
if st.session_state.user is not None and (get_param_from_query('code') or get_param_from_query('state')):
    set_query_params(user_id=st.session_state.user['id'])
    try:
        st.experimental_rerun()
    except Exception:
        components.html("<script>window.location.reload()</script>", height=0)
if st.session_state.user is None:
    authenticate_with_google()
if st.session_state.user is None:
    render_login_page()

# Render profile modal if requested
render_profile_modal()

with st.sidebar:
    st.markdown("# Chats")
    user_id = st.session_state.user["id"]
    chats = refresh_chats(user_id)

    if chats:
        selected_chat_id = st.session_state.get("selected_chat")
        
        # Default to first chat if nothing is selected and no pending chat exists
        if not selected_chat_id and not st.session_state.get("pending_chat"):
            selected_chat_id = chats[0]["id"]
            st.session_state.selected_chat = selected_chat_id
            
        default_index = 0
        if selected_chat_id:
            default_index = next((i for i, chat in enumerate(chats) if chat.get("id") == selected_chat_id), 0)

        def on_chat_select():
            selected = st.session_state.chat_to_open
            if selected:
                st.session_state.selected_chat = selected["id"]
                st.session_state.pending_chat = None

        selected_chat = st.selectbox(
            "Select chat",
            options=chats,
            format_func=lambda chat: chat.get("title") or "(no title)",
            index=default_index,
            key="chat_to_open",
            on_change=on_chat_select
        )
    else:
        st.info("No existing chats. Create a new chat to begin.")

    if st.button("New Chat", key="sidebar_new_chat"):
        new_chat()

    st.markdown("---")
    st.markdown("**Model**")
    st.selectbox(
        "Model",
        options=[
            "groq/llama-3.3-70b-versatile",   # Llama 3.3 70B via Groq (free, fast)
            "groq/compound-beta",              # Groq Compound (production model)
            "openai/gpt-oss-120b",             # OpenAI via Groq routing
        ],
        index=0,
        key="model_select",
    )
    st.markdown("---")
    if st.session_state.selected_chat:
        if st.button("Delete Chat", key="delete_chat_button"):
            store.delete_chat(st.session_state.selected_chat, user_id=user_id)
            st.session_state.selected_chat = None
            st.session_state.pending_chat = None
            if "chat_to_open" in st.session_state:
                del st.session_state["chat_to_open"]
    if st.session_state.pending_chat:
        st.warning("A new unsaved chat has been created. Send a message to save it, or refresh to discard.")

    # User profile block at bottom of sidebar
    st.markdown("---")
    user = st.session_state.user
    if user:
        pic = user.get("picture")
        name = user.get("name") or user.get("email")
        email = user.get("email")
        cols = st.columns([1, 3])
        with cols[0]:
            if pic:
                st.image(pic, width=48)
            else:
                st.markdown(f"<div style='width:48px;height:48px;border-radius:24px;background:#6b7280;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:600'>{(name[0] if name else '?').upper()}</div>", unsafe_allow_html=True)
        with cols[1]:
            st.markdown(f"**{name}**")
            st.markdown(f"{email}")
        if st.button("Logout", key="sidebar_logout"):
            logout_user()


main_col, right_col = st.columns([3.4, 0.9])

# Top-right user avatar and menu
with right_col:
    user = st.session_state.user
    if user:
        pic = user.get("picture")
        name = user.get("name") or user.get("email")
        avatar_col, theme_col, button_col = st.columns([0.08, 0.05, 0.04])
        with avatar_col:
            if pic:
                st.image(pic, width=40)
            else:
                st.markdown(
                    f"<div style='width:40px;height:40px;border-radius:20px;background:#6b7280;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:600;margin-bottom:0px'>{(name[0] if name else '?').upper()}</div>",
                    unsafe_allow_html=True,
                )
        with theme_col:
            if st.button("🌞" if st.session_state.theme == "dark" else "🌙", key="theme_btn"):
                st.session_state.theme = "light" if st.session_state.theme == "dark" else "dark"
                try:
                    st.rerun()
                except Exception:
                    st.experimental_rerun()
        with button_col:
            if "show_menu" not in st.session_state:
                st.session_state.show_menu = False
            if st.button("⋮", key="top_menu_btn"):
                st.session_state.show_menu = not st.session_state.show_menu
        if st.session_state.show_menu:
            with st.container():
                st.markdown("<div style='display:flex;flex-direction:column;gap:8px;margin-top:4px;'>", unsafe_allow_html=True)
                if st.button("Profile", key="top_profile"):
                    st.session_state.show_profile = True
                    try:
                        st.rerun()
                    except Exception:
                        st.experimental_rerun()
                if st.button("Logout", key="top_logout"):
                    logout_user()
                st.markdown("</div>", unsafe_allow_html=True)

with main_col:
    # Inject Light Theme CSS if active
    if st.session_state.theme == "light":
        st.markdown("""
        <style>
        .stApp, .stApp > header {
            background-color: #f7fafc !important;
        }
        [data-testid="stSidebar"] {
            background-color: #edf2f7 !important;
        }
        h1, h2, h3, h4, h5, h6, p, span, div, label {
            color: #2d3748 !important;
        }
        .stTextInput > div > div > input, .stTextArea > div > textarea {
            background-color: #ffffff !important;
            color: #2d3748 !important;
            caret-color: #2d3748 !important;
            border: 1px solid #cbd5e0 !important;
            border-radius: 8px !important;
        }
        /* Selectbox / Dropdown */
        [data-baseweb="select"] > div {
            background-color: #ffffff !important;
            color: #2d3748 !important;
            border: 1px solid #cbd5e0 !important;
        }
        [data-baseweb="menu"], [data-baseweb="popover"] {
            background-color: #ffffff !important;
        }
        li[role="option"] {
            background-color: #ffffff !important;
            color: #2d3748 !important;
        }
        li[role="option"]:hover {
            background-color: #edf2f7 !important;
        }
        /* Buttons */
        .stButton > button {
            background-color: #edf2f7 !important;
            color: #2d3748 !important;
            border: 1px solid #cbd5e0 !important;
        }
        .stButton > button:hover {
            background-color: #e2e8f0 !important;
            border-color: #a0aec0 !important;
        }
        /* Message Bubbles */
        .assistant-msg {
            background-color: #ffffff !important;
            color: #2d3748 !important;
            border: 1px solid #e2e8f0 !important;
            box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
        }
        .user-msg {
            background-color: #3182ce !important;
            color: #ffffff !important;
        }
        .meta {
            color: #718096 !important;
        }
        </style>
        """, unsafe_allow_html=True)

    # Welcome block first
    st.markdown("# Welcome User to this platform!")
    st.markdown("How can I help you plan trips, estimate budgets, and suggest activities.? Let me know😊")
    st.markdown("---")


    st.markdown("# Conversations")
    active_chat = None
    if st.session_state.selected_chat:
        active_chat = store.get_chat(st.session_state.selected_chat, user_id=st.session_state.user["id"])
    elif st.session_state.pending_chat:
        active_chat = st.session_state.pending_chat

    if active_chat:
        is_pending = active_chat is st.session_state.pending_chat
        if is_pending:
            st.info("This is a new unsaved chat. Send a message to save it, or refresh to discard.")

        new_title_text = st.text_input("Chat title", value=active_chat.get("title") or "", key=f"title_{active_chat['id']}")
        if st.button("Save title"):
            if new_title_text.strip():
                active_chat["title"] = new_title_text.strip()
                if st.session_state.selected_chat:
                    store.update_chat_title(active_chat["id"], active_chat["title"], user_id=st.session_state.user["id"])
                elif st.session_state.pending_chat:
                    store.save_chat(active_chat, user_id=st.session_state.user["id"])
                    st.session_state.selected_chat = active_chat["id"]
                    st.session_state.pending_chat = None
                    if "chat_to_open" in st.session_state:
                        del st.session_state["chat_to_open"]
                
                st.success("Chat title updated")
                try:
                    st.rerun()
                except Exception:
                    st.experimental_rerun()

        st.subheader(active_chat.get("title") or "Untitled")
        msgs = active_chat.get("messages", [])
        if msgs:
            render_messages(msgs)
            if msgs and msgs[-1].get("role") == "assistant":
                st.markdown("---")
                import re
                default_filename = active_chat.get("title") or "travel_plan"
                safe_default = re.sub(r'[^A-Za-z0-9_\-\s]', '', default_filename).strip()
                safe_default = re.sub(r'\s+', '_', safe_default)
                
                export_filename = st.text_input("Export file name (without extension):", value=safe_default, key=f"export_name_{active_chat['id']}")
                final_filename = export_filename.strip() or safe_default
                
                export_md_col, export_pdf_col, export_word_col = st.columns(3)
                aggregated = "\n\n".join([f"**{m['role']}**: {m['content']}" for m in msgs])
                with export_md_col:
                    st.download_button(
                        label="📄 Download Markdown",
                        data=aggregated,
                        file_name=f"{final_filename}.md",
                        mime="text/markdown",
                        key=f"download_md_{active_chat['id']}"
                    )
                with export_pdf_col:
                    try:
                        pdf_bytes = build_pdf_bytes(aggregated)
                        st.download_button(
                            label="📑 Download PDF",
                            data=pdf_bytes,
                            file_name=f"{final_filename}.pdf",
                            mime="application/pdf",
                            key=f"download_pdf_{active_chat['id']}"
                        )
                    except Exception as e:
                        st.warning(f"PDF export failed: {e}")
                with export_word_col:
                    try:
                        word_bytes = build_word_bytes(aggregated)
                        st.download_button(
                            label="📝 Download Word",
                            data=word_bytes,
                            file_name=f"{final_filename}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"download_word_{active_chat['id']}"
                        )
                    except Exception as e:
                        st.warning(f"Word export failed: {e}")
        else:
            st.info("No messages yet — send one below.")

        with st.form("input_form", clear_on_submit=True):
            user_input = st.text_area("Message", placeholder="Plan a trip to Goa?", height=120)
            submitted = st.form_submit_button("Send")
            if submitted and user_input.strip():
                now = datetime.datetime.utcnow().isoformat()
                if is_pending:
                    active_chat.setdefault("messages", []).append({"role": "user", "content": user_input, "ts": now})
                    active_chat["updated_at"] = now
                    if active_chat.get("title", "").lower() in ["new chat", "untitled", ""]:
                        active_chat["title"] = make_chat_title(user_input)
                    store.save_chat(active_chat, user_id=st.session_state.user["id"])
                    st.session_state.selected_chat = active_chat["id"]
                    st.session_state.pending_chat = None
                    if "chat_to_open" in st.session_state:
                        del st.session_state["chat_to_open"]
                else:
                    store.append_message(active_chat["id"], {"role": "user", "content": user_input, "ts": now}, user_id=st.session_state.user["id"])
                    if active_chat.get("title", "").lower() in ["new chat", "untitled", ""]:
                        new_title = make_chat_title(user_input)
                        store.update_chat_title(active_chat["id"], new_title, user_id=st.session_state.user["id"])
                        active_chat["title"] = new_title
                try:
                    with st.spinner("Agent is thinking..."):
                        model_provider = st.session_state.get("model_select", "groq")
                        resp = requests.post(f"{BASE_URL}/query", json={"question": user_input, "model": model_provider}, timeout=120)
                    if resp.status_code == 200:
                        answer = resp.json().get("answer") or "(no answer returned)"
                        store.append_message(active_chat["id"], {"role": "assistant", "content": answer, "ts": datetime.datetime.utcnow().isoformat()}, user_id=st.session_state.user["id"])
                    else:
                        err = resp.text or str(resp.status_code)
                        store.append_message(active_chat["id"], {"role": "assistant", "content": f"Error: backend returned {err}", "ts": datetime.datetime.utcnow().isoformat()}, user_id=st.session_state.user["id"])
                except Exception as e:
                    store.append_message(active_chat["id"], {"role": "assistant", "content": f"Error calling backend: {e}", "ts": datetime.datetime.utcnow().isoformat()}, user_id=st.session_state.user["id"])
                # Rerun so the new message is immediately visible without a second click
                try:
                    st.rerun()
                except Exception:
                    st.experimental_rerun()
    else:
        st.markdown("## Start a new conversation")
        st.markdown("Click 'New Chat' in the sidebar to create or open a chat before sending a message.")

with right_col:
    st.markdown("### Actions")
    if st.button("New Chat", key="right_new"):
        new_chat()
    st.markdown("---")
    st.markdown("### Tips")
    st.markdown(
        "<div style='padding:12px;border-radius:12px;background:#1f2937;color:#e5e7eb;line-height:1.6;'>"
        "<p style='margin:0 0 8px 0;font-weight:600;'>Try these prompts:</p>"
        "<ul style='margin:0;padding-left:18px;'>"
        "<li>Start with: 'Plan a 5-day trip to Goa'</li>"
        "<li>Ask for budget, hotels, or activities</li>"
        "</ul>"
        "</div>",
        unsafe_allow_html=True,
    )

