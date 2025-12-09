import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import time
import bcrypt
import re
import io
import logging

# Configure Logging
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 1. Page Configuration (Must be first) ---
st.set_page_config(page_title="ניהול ספקים", layout="wide", initial_sidebar_state="expanded")

# --- 2. Configuration & Constants ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "ניהול ספקים"
BCRYPT_ROUNDS = 12  # Security Fix: Increased rounds

# --- 3. Helper Functions (Logic & Security) ---

def normalize_text(text):
    """Data Normalization Fix: Consistent text cleaning."""
    if text is None:
        return ""
    return str(text).strip().lower()

def validate_password_strength(password):
    """Security Fix: Password complexity check."""
    if len(password) < 8:
        return False
    return True

def hash_password(password):
    """Security Fix: Increased salt rounds."""
    try:
        # Gensalt with 12 rounds for better security
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=BCRYPT_ROUNDS))
        return hashed.decode('utf-8')
    except Exception as e:
        logging.error(f"Password hashing failed: {e}")
        return None

def check_password(plain_text_password, hashed_password):
    """Security Fix: robust error handling."""
    try:
        if not plain_text_password or not hashed_password:
            return False
        return bcrypt.checkpw(plain_text_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except ValueError as e:
        logging.error(f"Password check value error: {e}")
        return False
    except Exception as e:
        logging.error(f"Password check failed: {e}")
        return False

def is_valid_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None

def check_duplicate_supplier(df, name, phone, email):
    """Data Normalization Fix: Check duplicates with normalized data."""
    if df.empty:
        return False, ""
    
    # Normalize inputs
    norm_name = normalize_text(name)
    norm_phone = normalize_text(phone)
    norm_email = normalize_text(email)
    
    # Normalize DataFrame columns for comparison (safely)
    # We use a temporary copy or on-the-fly conversion to avoid modifying the display DF
    
    try:
        existing_names = df['שם הספק'].astype(str).str.strip().str.lower().values
        if norm_name in existing_names:
            return True, f"שגיאה: שם '{name}' כבר קיים במערכת."

        if norm_phone: # Check only if phone provided
            existing_phones = df['טלפון'].astype(str).str.strip().str.lower().values
            if norm_phone in existing_phones:
                return True, f"שגיאה: טלפון '{phone}' כבר קיים במערכת."

        if norm_email: # Check only if email provided
            existing_emails = df['אימייל'].astype(str).str.strip().str.lower().values
            if norm_email in existing_emails:
                return True, f"שגיאה: אימייל '{email}' כבר קיים במערכת."
                
    except KeyError as e:
        logging.error(f"Column missing in Duplicate Check: {e}")
        return False, "" # Fail open to avoid blocking UI, but log error
        
    return False, ""

def validate_supplier_form(df, name, fields, phone, email, addr, pay):
    """DRY Fix: Centralized validation logic."""
    # 1. Empty Check
    if not (name and fields and phone and email and addr and pay):
        return False, "נא למלא את כל שדות החובה"
    
    # 2. Email Syntax
    if not is_valid_email(email):
        return False, "❌ כתובת אימייל לא תקינה"
    
    # 3. Duplicate Check
    is_dup, msg = check_duplicate_supplier(df, name, phone, email)
    if is_dup:
        return False, f"❌ {msg}"
        
    return True, ""

def generate_excel_template():
    columns = ['שם הספק', 'תחום עיסוק', 'טלפון', 'אימייל', 'כתובת', 'שם איש קשר', 'תנאי תשלום']
    df = pd.DataFrame(columns=columns)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return buffer

# --- 4. CSS (Design) ---
def set_css():
    st.markdown("""
    <style>
        /* RTL Direction */
        .stApp { direction: rtl; text-align: right; }
        
        .block-container {
            max-width: 100%;
            padding-top: 1rem;
            padding-right: 2rem;
            padding-left: 2rem;
            padding-bottom: 3rem;
        }

        h1, h2, h3, h4, h5, h6, p, div, span, label, .stMarkdown, .stButton, .stAlert, .stSelectbox, .stMultiSelect { 
            text-align: right !important; 
        }
        .stTextInput input, .stTextArea textarea, .stSelectbox, .stNumberInput input { 
            direction: rtl; text-align: right; 
        }
        
        .stTabs [data-baseweb="tab-list"] { 
            flex-direction: row-reverse; justify-content: flex-end; 
        }
        
        /* Admin Table */
        [data-testid="stDataEditor"] { direction: rtl; }
        [data-testid="stDataEditor"] div[role="columnheader"] {
            text-align: right !important;
            justify-content: flex-start !important;
            direction: rtl;
        }
        [data-testid="stDataEditor"] div[role="gridcell"] {
            text-align: right !important;
            justify-content: flex-end !important;
            direction: rtl;
        }

        /* User HTML Table */
        .rtl-table { 
            width: 100%; 
            border-collapse: collapse; 
            direction: rtl; 
            margin-top: 10px; 
        }
        .rtl-table th { 
            background-color: #f0f2f6; 
            text-align: right !important; 
            padding: 10px; 
            border-bottom: 2px solid #ddd; 
            color: #333; 
            font-weight: bold; 
            white-space: nowrap; 
        }
        .rtl-table td { 
            text-align: right !important; 
            padding: 10px; 
            border-bottom: 1px solid #eee; 
            color: #333; 
        }

        /* Mobile Cards */
        .mobile-card { background-color: white; border: 1px solid #ddd; border-radius: 8px; margin-bottom: 12px; padding: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); direction: rtl; text-align: right !important; }
        .mobile-card summary { font-weight: bold; cursor: pointer; color: #000; list-style: none; outline: none; display: flex; justify-content: space-between; align-items: center; }
        .mobile-card summary::after { content: "+"; font-size: 1.2em; color: #666; margin-right: 10px;}
        .mobile-card details[open] summary::after { content: "-"; }
        .mobile-card .card-content { margin-top: 10px; padding-top: 10px; border-top: 1px solid #eee; font-size: 0.95em; color: #333; }
        .mobile-card a { color: #0068c9; text-decoration: none; font-weight: bold; }
        
        /* Online Counter */
        .online-container { position: fixed; bottom: 15px; left: 15px; z-index: 99999; direction: rtl; font-family: sans-serif; }
        .online-badge { background-color: #4CAF50; color: white; padding: 8px 15px; border-radius: 50px; font-size: 0.9em; box-shadow: 0 2px 5px rgba(0,0,0,0.3); cursor: default; font-weight: bold; }
        .online-list { visibility: hidden; opacity: 0; position: absolute; bottom: 45px; left: 0; background-color: white; color: #333; min-width: 180px; padding: 10px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.2); border: 1px solid #eee; transition: all 0.2s ease-in-out; text-align: right; font-size: 0.85em; }
        .online-container:hover .online-list { visibility: visible; opacity: 1; bottom: 50px; }

        .desktop-view { display: block; }
        .mobile-view { display: none; }
        @media only screen and (max-width: 768px) {
            .desktop-view { display: none; }
            .mobile-view { display: block; }
            [data-testid="stSidebar"] { display: none !important; }
            .block-container { padding-top: 1rem !important; }
        }
    </style>
    """, unsafe_allow_html=True)

# --- 5. Google Sheets Integration ---

def get_client():
    """Establish connection to Google Sheets API."""
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        return client
    except KeyError:
        st.error("תצורת Secrets חסרה. אנא בדוק את ההגדרות.")
        return None
    except Exception as e:
        logging.error(f"GSpread Auth Error: {e}")
        st.error("שגיאה בהתחברות ל-Google Sheets")
        return None

# Performance Fix: Caching added (TTL 5 minutes)
# Modified to return ONLY DataFrame to allow caching (Sheet object isn't pickleable)
@st.cache_data(ttl=300)
def get_worksheet_data(worksheet_name):
    """Fetches data from a specific worksheet and returns as Pandas DataFrame."""
    try:
        # Internal client creation for the cached function
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        
        sheet = client.open(SHEET_NAME).worksheet(worksheet_name)
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except gspread.exceptions.WorksheetNotFound:
        logging.error(f"Worksheet not found: {worksheet_name}")
        return pd.DataFrame() # Return empty DF gracefully
    except Exception as e:
        logging.error(f"Error fetching data from {worksheet_name}: {e}")
        return pd.DataFrame()

def _get_sheet_object_for_write(worksheet_name):
    """Helper for write operations (not cached)."""
    try:
        client = get_client()
        if not client: return None
        return client.open(SHEET_NAME).worksheet(worksheet_name)
    except Exception as e:
        logging.error(f"Error accessing sheet for write {worksheet_name}: {e}")
        return None

def update_active_user(username):
    """Updates the active_users sheet with timestamp."""
    current_time = datetime.now()
    
    # Throttle updates to once per minute per session to save API quota
    if 'last_api_update' in st.session_state:
        if (current_time - st.session_state['last_api_update']).seconds < 60:
            return

    try:
        sheet = _get_sheet_object_for_write("active_users")
        if not sheet: return

        # We must read current data to know if update or append
        # This part is unavoidable for gspread without SQL-like update
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        timestamp_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Normalize for comparison
        username_norm = normalize_text(username)
        
        found = False
        row_idx = 2 # Sheets start at 1, header is 1
        
        if not df.empty:
            # Find index
            for idx, row in df.iterrows():
                if normalize_text(row['username']) == username_norm:
                    sheet.update_cell(idx + 2, 2, timestamp_str)
                    found = True
                    break
        
        if not found:
            sheet.append_row([username, timestamp_str])
            
        st.session_state['last_api_update'] = current_time
    except Exception as e:
        logging.error(f"Error updating active user: {e}")

def get_online_users_count_and_names():
    """Performance Fix: N+1 Query removed using Pandas Merge."""
    try:
        # Fetch cached DFs
        df_active = get_worksheet_data("active_users")
        df_users = get_worksheet_data("users")
        
        if df_active.empty:
            return 0, []
        
        # Time filter (last 5 minutes)
        now = datetime.now()
        df_active['last_seen'] = pd.to_datetime(df_active['last_seen'], errors='coerce')
        # Filter active sessions
        active_mask = (now - df_active['last_seen']).dt.total_seconds() < 300
        df_active_filtered = df_active[active_mask].copy()
        
        if df_active_filtered.empty:
            return 0, []

        # Normalize keys for merge
        df_active_filtered['join_key'] = df_active_filtered['username'].astype(str).str.strip().str.lower()
        
        if not df_users.empty:
            df_users['join_key'] = df_users['username'].astype(str).str.strip().str.lower()
            # Merge to get real names
            merged = pd.merge(df_active_filtered, df_users[['join_key', 'name']], on='join_key', how='left')
            # Use 'name' if available, else 'username'
            merged['display_name'] = merged['name'].fillna(merged['username'])
            active_names = merged['display_name'].tolist()
        else:
            active_names = df_active_filtered['username'].tolist()
            
        return len(active_names), active_names

    except Exception as e:
        logging.error(f"Error calculating online users: {e}")
        return 0, []

def add_row_to_sheet(worksheet_name, row_data):
    try:
        sheet = _get_sheet_object_for_write(worksheet_name)
        if sheet:
            sheet.append_row(row_data)
            # Clear cache to reflect new data immediately
            st.cache_data.clear()
            return True
    except Exception as e:
        st.error(f"שגיאה בשמירת הנתונים: {e}")
        logging.error(f"Add row error: {e}")
    return False

def delete_row_from_sheet(worksheet_name, key_col, key_val):
    try:
        sheet = _get_sheet_object_for_write(worksheet_name)
        if not sheet: return False
        
        data = sheet.get_all_records()
        for i, row in enumerate(data):
            # Normalize comparison
            if str(row[key_col]).strip() == str(key_val).strip():
                sheet.delete_rows(i + 2)
                st.cache_data.clear()
                return True
    except Exception as e:
        st.error(f"שגיאה במחיקת הנתונים: {e}")
        logging.error(f"Delete row error: {e}")
    return False

# --- 6. Admin Settings Helper ---
def get_settings_lists():
    df = get_worksheet_data("settings")
    if df.empty: return [], []
    # Drop N/A or empty strings
    fields = [x for x in df['fields'].tolist() if str(x).strip()]
    payment_terms = [x for x in df['payment_terms'].tolist() if str(x).strip()]
    return fields, payment_terms

def update_settings_list(column_name, new_list):
    try:
        sheet = _get_sheet_object_for_write("settings")
        if not sheet: return

        # We need to preserve the other column. 
        # Read directly from sheet to ensure latest state (bypass cache for write logic)
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        other_col = 'payment_terms' if column_name == 'fields' else 'fields'
        other_list = [x for x in df[other_col].tolist() if str(x).strip()] if not df.empty and other_col in df.columns else []
        
        max_len = max(len(new_list), len(other_list))
        new_list += [''] * (max_len - len(new_list))
        other_list += [''] * (max_len - len(other_list))
        
        new_df = pd.DataFrame({column_name: new_list, other_col: other_list})
        sheet.clear()
        sheet.update([new_df.columns.values.tolist()] + new_df.values.tolist())
        st.cache_data.clear()
    except Exception as e:
        st.error("שגיאה בעדכון הגדרות")
        logging.error(f"Settings update error: {e}")

# --- 7. UI Components ---

@st.dialog("אישור מחיקה מרובה")
def confirm_bulk_delete(suppliers_to_delete):
    st.write(f"האם למחוק **{len(suppliers_to_delete)}** ספקים?")
    col1, col2 = st.columns(2)
    if col1.button("כן, מחק", type="primary"):
        prog = st.progress(0)
        cnt = 0
        for i, name in enumerate(suppliers_to_delete):
            if delete_row_from_sheet("suppliers", "שם הספק", name): cnt += 1
            prog.progress((i + 1) / len(suppliers_to_delete))
        if cnt > 0:
            st.success(f"{cnt} נמחקו!")
            time.sleep(1)
            st.rerun()
        else: st.error("שגיאה במחיקה")
    if col2.button("ביטול"): st.rerun()

def show_admin_table_with_checkboxes(df, all_fields_list):
    c_search, c_filter = st.columns([2, 1])
    with c_search: search = st.text_input("🔍 חיפוש (מנהל)", "")
    with c_filter: cat = st.selectbox("📂 סינון (מנהל)", ["הכל"] + all_fields_list)

    if not df.empty:
        if cat != "הכל": df = df[df['תחום עיסוק'].astype(str).str.contains(cat, na=False)]
        if search: df = df[df['שם הספק'].astype(str).str.contains(search, case=False, na=False) | df['טלפון'].astype(str).str.contains(search, case=False, na=False)]
        
        # Order: Name first (Right), Delete last (Left) in RTL
        cols_order = ['שם הספק', 'תחום עיסוק', 'טלפון', 'אימייל', 'כתובת', 'שם איש קשר', 'תנאי תשלום', 'נוסף על ידי']
        final_cols = [c for c in cols_order if c in df.columns]
        df_disp = df[final_cols].copy()
        
        df_disp["מחיקה?"] = False

        st.write("סמן בתיבה את הספקים למחיקה:")
        
        edited_df = st.data_editor(
            df_disp,
            column_config={
                "מחיקה?": st.column_config.CheckboxColumn("מחק", default=False, width="small"),
                "שם הספק": st.column_config.TextColumn(disabled=True),
                "תחום עיסוק": st.column_config.TextColumn(disabled=True),
                "טלפון": st.column_config.TextColumn(disabled=True),
                "אימייל": st.column_config.TextColumn(disabled=True),
                "כתובת": st.column_config.TextColumn(disabled=True),
                "שם איש קשר": st.column_config.TextColumn(disabled=True),
                "תנאי תשלום": st.column_config.TextColumn(disabled=True),
                "נוסף על ידי": st.column_config.TextColumn(disabled=True),
            },
            hide_index=True,
            use_container_width=True
        )

        sel = edited_df[edited_df["מחיקה?"] == True]
        if not sel.empty:
            st.warning(f"נבחרו {len(sel)} למחיקה.")
            if st.button("🗑️ מחק מסומנים", type="primary"):
                confirm_bulk_delete(sel["שם הספק"].tolist())
    else: st.info("אין נתונים")

def show_suppliers_table(df, all_fields_list):
    c_search, c_filter = st.columns([2, 1])
    with c_search: search = st.text_input("🔍 חיפוש חופשי", "")
    with c_filter: cat = st.selectbox("📂 סינון", ["הכל"] + all_fields_list)

    if not df.empty:
        if cat != "הכל": df = df[df['תחום עיסוק'].astype(str).str.contains(cat, na=False)]
        if search: df = df[df['שם הספק'].astype(str).str.contains(search, case=False, na=False) | df['טלפון'].astype(str).str.contains(search, case=False, na=False)]
        
        cols = ['שם הספק', 'תחום עיסוק', 'טלפון', 'אימייל', 'כתובת', 'שם איש קשר', 'תנאי תשלום', 'נוסף על ידי']
        df_final = df[[c for c in cols if c in df.columns]]
        
        # HTML PC - One line to prevent breakage
        table_html = df_final.to_html(index=False, classes='rtl-table', border=0, escape=False).replace('\n', '')
        
        # HTML Mobile
        cards_html_list = []
        for _, row in df.iterrows():
            card = f"""<div class="mobile-card"><details><summary><span>{row['שם הספק']} | {row['תחום עיסוק']}</span></summary><div class="card-content"><div><strong>📞:</strong> <a href="tel:{row['טלפון']}">{row['טלפון']}</a></div><div><strong>✉️:</strong> <a href="mailto:{row.get('אימייל','')}">{row.get('אימייל','')}</a></div><div><strong>📍:</strong> {row['כתובת']}</div><div><strong>👤:</strong> {row.get('שם איש קשר','')}</div><div><strong>💳:</strong> {row.get('תנאי תשלום','')}</div><div style="font-size:0.8em;color:#888;margin-top:5px">נוסף ע"י: {row.get('נוסף על ידי','')}</div></div></details></div>"""
            cards_html_list.append(card)
        cards_html_full = "".join(cards_html_list)

        st.markdown(f'<div class="desktop-view">{table_html}</div><div class="mobile-view">{cards_html_full}</div>', unsafe_allow_html=True)
    else: st.info("אין נתונים")

# --- 8. Login Page ---
def login_page():
    c1, c2, c3 = st.columns([1, 1.5, 1])
    with c2:
        st.title("🔐 כניסה למערכת")
        with st.expander("כלי למנהל (הצפנה)"):
            p = st.text_input("סיסמה")
            if st.button("הצפן"): 
                h = hash_password(p)
                if h: st.code(h)

        t1, t2 = st.tabs(["התחברות", "הרשמה"])
        with t1:
            with st.form("login_form"):
                user = st.text_input("אימייל").lower().strip()
                pw = st.text_input("סיסמה", type="password")
                st.checkbox("זכור אותי")
                if st.form_submit_button("התחבר"):
                    df_users = get_worksheet_data("users")
                    if not df_users.empty:
                        # Normalize username column for search
                        df_users['username_norm'] = df_users['username'].astype(str).str.lower().str.strip()
                        rec = df_users[df_users['username_norm'] == user]
                        
                        if not rec.empty and check_password(pw, rec.iloc[0]['password']):
                            st.session_state['logged_in'] = True
                            st.session_state['username'] = user
                            st.session_state['name'] = rec.iloc[0]['name']
                            st.session_state['role'] = rec.iloc[0]['role']
                            update_active_user(user)
                            st.success("מחובר!")
                            time.sleep(0.5)
                            st.rerun()
                        else: st.error("פרטים שגויים")
                    else: st.error("שגיאה בטעינת משתמשים")

        with t2:
            with st.form("signup_form"):
                new_email = st.text_input("אימייל").lower().strip()
                new_pass = st.text_input("סיסמה", type="password")
                fname = st.text_input("שם מלא")
                if st.form_submit_button("הירשם"):
                    if not is_valid_email(new_email): 
                        st.error("אימייל לא תקין")
                    elif not validate_password_strength(new_pass):
                        st.error("סיסמה חייבת להיות לפחות 8 תווים")
                    else:
                        df_u = get_worksheet_data("users")
                        df_p = get_worksheet_data("pending_users")
                        
                        # Check duplicate in both lists
                        exists = False
                        if not df_u.empty and new_email in df_u['username'].astype(str).str.lower().str.strip().values: exists = True
                        if not df_p.empty and new_email in df_p['username'].astype(str).str.lower().str.strip().values: exists = True
                        
                        if exists: st.error("משתמש קיים במערכת")
                        else:
                            hashed = hash_password(new_pass)
                            if hashed:
                                add_row_to_sheet("pending_users", [new_email, hashed, fname, str(datetime.now())])
                                st.success("נשלח לאישור")
                            else:
                                st.error("שגיאה בהצפנת סיסמה")

# --- 9. Main Application ---
def main_app():
    user_role = st.session_state.get('role', 'user')
    user_name = st.session_state.get('name', 'User')
    current_user_email = st.session_state.get('username', '')
    update_active_user(current_user_email)
    
    fields_list, payment_list = get_settings_lists()
    df_suppliers = get_worksheet_data("suppliers")

    c1, c2, c3 = st.columns([6, 2, 1])
    c1.title(f"שלום, {user_name}")
    if c2.button("🔄"):
        st.cache_data.clear()
        st.rerun()
    if c3.button("יציאה"):
        st.session_state['logged_in'] = False
        st.rerun()

    with st.expander("📬 ההגשות שלי"):
        df_rejected = get_worksheet_data("rejected_suppliers")
        my_rejections = pd.DataFrame() 
        if not df_rejected.empty:
            mask = df_rejected['נוסף על ידי'].astype(str).str.contains(user_name, na=False) | df_rejected['נוסף על ידי'].astype(str).str.contains(current_user_email, na=False)
            my_rejections = df_rejected[mask]
        if not my_rejections.empty:
            st.error(f"יש {len(my_rejections)} ספקים שנדחו.")
            st.dataframe(my_rejections[['שם הספק', 'תאריך דחייה']], use_container_width=True)
        else: st.info("אין הודעות")

    st.markdown("---")

    if user_role == 'admin':
        df_pend_users = get_worksheet_data("pending_users")
        c_users = len(df_pend_users) if not df_pend_users.empty else 0
        df_pend_supp = get_worksheet_data("pending_suppliers")
        c_supp = len(df_pend_supp) if not df_pend_supp.empty else 0

        tabs = st.tabs(["📋 רשימת ספקים", f"⏳ אישור ספקים ({c_supp})", f"👥 אישור משתמשים ({c_users})", "➕ הוספה", "⚙️ הגדרות", "📥 יבוא"])
        
        with tabs[0]: show_admin_table_with_checkboxes(df_suppliers, fields_list)
        
        with tabs[1]:
            if c_supp > 0:
                for idx, row in df_pend_supp.iterrows():
                    with st.expander(f"{row['שם הספק']}"):
                        st.write(f"תחום: {row['תחום עיסוק']} | טלפון: {row['טלפון']}")
                        dup, err = check_duplicate_supplier(df_suppliers, row['שם הספק'], row['טלפון'], row.get('אימייל',''))
                        if dup: st.warning(err)
                        c1, c2 = st.columns(2)
                        if c1.button("אשר", key=f"ok_s_{idx}"):
                            add_row_to_sheet("suppliers", [
                                row['שם הספק'], row['תחום עיסוק'], row['טלפון'], 
                                row['כתובת'], row['תנאי תשלום'], row.get('אימייל',''), 
                                row.get('שם איש קשר',''), row['נוסף על ידי']
                            ])
                            delete_row_from_sheet("pending_suppliers", "שם הספק", row['שם הספק'])
                            st.rerun()
                        if c2.button("דחה", key=f"no_s_{idx}"):
                            row_data = row.values.tolist()
                            row_data.append(str(datetime.now()))
                            add_row_to_sheet("rejected_suppliers", row_data)
                            delete_row_from_sheet("pending_suppliers", "שם הספק", row['שם הספק'])
                            st.rerun()
            else: st.info("אין ספקים ממתינים")

        with tabs[2]:
            if c_users > 0:
                for idx, row in df_pend_users.iterrows():
                    st.write(f"בקשה: {row['name']} ({row['username']})")
                    c1, c2 = st.columns(2)
                    if c1.button("אשר", key=f"ok_u_{idx}"):
                        add_row_to_sheet("users", [row['username'], row['password'], 'user', row['name']])
                        delete_row_from_sheet("pending_users", "username", row['username'])
                        st.rerun()
                    if c2.button("דחה", key=f"no_u_{idx}"):
                        delete_row_from_sheet("pending_users", "username", row['username'])
                        st.rerun()
            else: st.info("אין משתמשים")

        with tabs[3]:
            with st.form("adm_add"):
                s_name = st.text_input("שם *")
                s_fields = st.multiselect("תחום *", fields_list)
                s_phone = st.text_input("טלפון *")
                s_email = st.text_input("אימייל *")
                s_contact = st.text_input("איש קשר")
                s_addr = st.text_input("כתובת *")
                s_pay = st.selectbox("תנאי תשלום *", payment_list)
                if st.form_submit_button("שמור"):
                    # DRY Validation Fix
                    valid, msg = validate_supplier_form(df_suppliers, s_name, s_fields, s_phone, s_email, s_addr, s_pay)
                    if valid:
                        fields_str = ", ".join(s_fields)
                        if add_row_to_sheet("suppliers", [s_name, fields_str, s_phone, s_addr, s_pay, s_email, s_contact, user_name]):
                            st.success("נוסף!")
                            time.sleep(1)
                            st.rerun()
                    else:
                        st.error(msg)
        
        with tabs[4]:
            st.subheader("ניהול רשימות")
            c_fields, c_terms = st.columns(2)
            with c_fields:
                new_field = st.text_input("הוסף תחום")
                if st.button("הוסף", key="add_f"):
                    if new_field and new_field not in fields_list:
                        fields_list.append(new_field)
                        update_settings_list("fields", fields_list)
                        st.rerun()
                rem_field = st.selectbox("מחק תחום", [""] + fields_list, key="sel_rem_f")
                if st.button("מחק", key="btn_rem_f"):
                    if rem_field:
                        fields_list.remove(rem_field)
                        update_settings_list("fields", fields_list)
                        st.rerun()
            with c_terms:
                new_term = st.text_input("הוסף תנאי")
                if st.button("הוסף", key="add_t"):
                    if new_term and new_term not in payment_list:
                        payment_list.append(new_term)
                        update_settings_list("payment_terms", payment_list)
                        st.rerun()
                rem_term = st.selectbox("מחק תנאי", [""] + payment_list, key="sel_rem_t")
                if st.button("מחק", key="btn_rem_t"):
                    if rem_term:
                        payment_list.remove(rem_term)
                        update_settings_list("payment_terms", payment_list)
                        st.rerun()

        with tabs[5]:
            st.subheader("יבוא נתונים")
            st.markdown("יש להשתמש בקובץ אקסל הבנוי בדיוק לפי התבנית.")
            template_buffer = generate_excel_template()
            st.download_button(label="📥 הורד תבנית אקסל", data=template_buffer, file_name="template.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.divider()
            up = st.file_uploader("העלה קובץ", type="xlsx")
            if up and st.button("בדוק וטען"):
                try:
                    new_df = pd.read_excel(up).astype(str).replace('nan', '')
                    expected_cols = ['שם הספק', 'תחום עיסוק', 'טלפון', 'אימייל', 'כתובת', 'שם איש קשר', 'תנאי תשלום']
                    if not all(col in new_df.columns for col in expected_cols):
                        st.error(f"הקובץ לא תואם. עמודות חובה: {', '.join(expected_cols)}")
                    else:
                        errors = []
                        valid_rows = []
                        current_db = get_worksheet_data("suppliers")
                        for idx, row in new_df.iterrows():
                            excel_row_num = idx + 2
                            mandatory = ['שם הספק', 'תחום עיסוק', 'טלפון', 'אימייל', 'כתובת', 'תנאי תשלום']
                            missing = [col for col in mandatory if not row[col].strip()]
                            if missing:
                                errors.append(f"שורה {excel_row_num}: חסר {', '.join(missing)}")
                                continue
                            if not is_valid_email(row['אימייל']):
                                errors.append(f"שורה {excel_row_num}: אימייל שגוי")
                                continue
                            is_dup, msg = check_duplicate_supplier(current_db, row['שם הספק'], row['טלפון'], row['אימייל'])
                            if is_dup:
                                errors.append(f"שורה {excel_row_num}: {msg}")
                                continue
                            
                            clean_row = [row[c].strip() for c in expected_cols]
                            clean_row.append(user_name)
                            valid_rows.append(clean_row)

                        if errors:
                            st.error("נמצאו שגיאות:")
                            for e in errors: st.warning(e)
                        elif not valid_rows:
                            st.warning("אין נתונים תקינים")
                        else:
                            sheet = _get_sheet_object_for_write("suppliers")
                            if sheet:
                                sheet.append_rows(valid_rows)
                                st.success(f"✅ {len(valid_rows)} ספקים נטענו!")
                                st.cache_data.clear()
                                time.sleep(2)
                                st.rerun()
                except Exception as e: st.error(f"שגיאה: {e}")

    else:
        user_tabs = st.tabs(["🔎 חיפוש", "➕ הצעה"])
        with user_tabs[0]: show_suppliers_table(df_suppliers, fields_list)
        with user_tabs[1]:
            with st.form("u_add"):
                s_name = st.text_input("שם *")
                s_fields = st.multiselect("תחום *", fields_list)
                s_phone = st.text_input("טלפון *")
                s_email = st.text_input("אימייל *")
                s_contact = st.text_input("איש קשר")
                s_addr = st.text_input("כתובת *")
                s_pay = st.selectbox("תנאי תשלום *", payment_list)
                if st.form_submit_button("שלח"):
                    # DRY Validation Fix
                    valid, msg = validate_supplier_form(df_suppliers, s_name, s_fields, s_phone, s_email, s_addr, s_pay)
                    if valid:
                        fields_str = ", ".join(s_fields)
                        if add_row_to_sheet("pending_suppliers", [s_name, fields_str, s_phone, s_addr, s_pay, s_email, s_contact, user_name, str(datetime.now())]):
                            st.success("נשלח!")
                    else:
                        st.error(msg)

    cnt, names = get_online_users_count_and_names()
    names_html = "<br>".join(names) if names else "אין"
    tooltip = f'<div class="online-list"><strong>מחוברים:</strong><br>{names_html}</div>'

    st.markdown(f"""
    <div class="online-container">
        {tooltip}
        <div class="online-badge">🟢 מחוברים: {cnt}</div>
    </div>
    """, unsafe_allow_html=True)

# --- 10. Execution ---
set_css()
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if not st.session_state['logged_in']: login_page()
else: main_app()
