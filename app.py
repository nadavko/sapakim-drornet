import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime
import time
import bcrypt
import re
import io
import logging

# --- 1. הגדרת עמוד ---
st.set_page_config(page_title="ניהול ספקים", layout="wide", initial_sidebar_state="collapsed")

# --- 2. הגדרות וחיבורים ---
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
SHEET_NAME = "ניהול ספקים"
BCRYPT_ROUNDS = 12

logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 3. פונקציות עזר (לוגיקה ואבטחה) ---

def normalize_text(text):
    if text is None: return ""
    return str(text).strip().lower()

def validate_password_strength(password):
    return len(password) >= 6

def hash_password(password):
    try:
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=BCRYPT_ROUNDS))
        return hashed.decode('utf-8')
    except Exception as e:
        logging.error(f"Hashing failed: {e}")
        return None

def check_password(plain_text_password, hashed_password):
    try:
        if not plain_text_password or not hashed_password: return False
        return bcrypt.checkpw(plain_text_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except ValueError: return False

def is_valid_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None

def check_duplicate_supplier(df, name, phone, email):
    if df.empty: return False, ""
    
    norm_name = normalize_text(name)
    norm_phone = normalize_text(phone)
    norm_email = normalize_text(email)
    
    try:
        existing_names = df['שם הספק'].astype(str).str.strip().str.lower().values
        if norm_name in existing_names: return True, f"שם '{name}' כבר קיים."

        if norm_phone:
            existing_phones = df['טלפון'].astype(str).str.strip().str.lower().values
            if norm_phone in existing_phones: return True, f"טלפון '{phone}' כבר קיים."

        if norm_email:
            existing_emails = df['אימייל'].astype(str).str.strip().str.lower().values
            if norm_email in existing_emails: return True, f"אימייל '{email}' כבר קיים."
    except KeyError: pass
        
    return False, ""

def validate_supplier_form(df, name, fields, phone, email, addr, pay, files_dict):
    if not (name and fields and phone and email and addr and pay):
        return False, "נא למלא את כל שדות החובה (פרטי ספק)"
    
    # בדיקת קבצים חובה
    missing_files = [k for k, v in files_dict.items() if v is None]
    if missing_files:
        return False, f"חסרים קבצים: {', '.join(missing_files)}"

    if not is_valid_email(email):
        return False, "כתובת אימייל לא תקינה"
    
    is_dup, msg = check_duplicate_supplier(df, name, phone, email)
    if is_dup:
        return False, msg
    return True, ""

def generate_excel_template():
    columns = ['שם הספק', 'תחום עיסוק', 'טלפון', 'אימייל', 'כתובת', 'שם איש קשר', 'תנאי תשלום']
    df = pd.DataFrame(columns=columns)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return buffer

# --- 4. פונקציות גוגל (דרייב + שיטס) ---

def get_credentials_dict():
    return dict(st.secrets["gcp_service_account"])

def get_client():
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(get_credentials_dict(), SCOPE)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error("שגיאת התחברות ל-Google Sheets")
        return None

def upload_file_to_drive(file_obj, filename_prefix):
    """
    מעלה קובץ ל-Google Drive ומחזיר את הקישור אליו.
    """
    if not file_obj: return ""
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(get_credentials_dict(), SCOPE)
        service = build('drive', 'v3', credentials=creds)
        
        file_name = f"{filename_prefix}_{file_obj.name}"
        file_metadata = {'name': file_name}
        
        file_obj.seek(0)
        media = MediaIoBaseUpload(file_obj, mimetype=file_obj.type)
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        
        return file.get('webViewLink')
        
    except Exception as e:
        logging.error(f"Drive Upload Error: {e}")
        return None

@st.cache_data(ttl=300)
def get_worksheet_data(worksheet_name):
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(get_credentials_dict(), SCOPE)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME).worksheet(worksheet_name)
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame()

def _get_sheet_object(worksheet_name):
    try:
        client = get_client()
        return client.open(SHEET_NAME).worksheet(worksheet_name)
    except: return None

def update_active_user(username):
    current_time = datetime.now()
    if 'last_api_update' in st.session_state:
        if (current_time - st.session_state['last_api_update']).seconds < 60: return
    try:
        sheet = _get_sheet_object("active_users")
        if not sheet: return
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        ts_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
        found = False
        if not df.empty:
            for idx, row in df.iterrows():
                if normalize_text(row['username']) == normalize_text(username):
                    sheet.update_cell(idx + 2, 2, ts_str)
                    found = True
                    break
        if not found: sheet.append_row([username, ts_str])
        st.session_state['last_api_update'] = current_time
    except: pass

def get_online_users_count_and_names():
    try:
        df_active = get_worksheet_data("active_users")
        if df_active.empty: return 0, []
        df_users = get_worksheet_data("users")
        now = datetime.now()
        active_names = []
        for _, row in df_active.iterrows():
            try:
                last_seen = datetime.strptime(str(row['last_seen']), "%Y-%m-%d %H:%M:%S")
                if (now - last_seen).total_seconds() < 300: 
                    email = str(row['username']).lower().strip()
                    display_name = email
                    if not df_users.empty:
                        user_row = df_users[df_users['username'].astype(str).str.lower().str.strip() == email]
                        if not user_row.empty: display_name = user_row.iloc[0]['name']
                    active_names.append(display_name)
            except: continue
        return len(active_names), active_names
    except: return 0, []

def add_row_to_sheet(worksheet_name, row_data):
    try:
        sheet = _get_sheet_object(worksheet_name)
        if sheet:
            sheet.append_row(row_data)
            st.cache_data.clear()
            return True
    except Exception as e: st.error(f"שגיאה: {e}")
    return False

def delete_row_from_sheet(worksheet_name, key_col, key_val):
    try:
        sheet = _get_sheet_object(worksheet_name)
        if not sheet: return False
        data = sheet.get_all_records()
        for i, row in enumerate(data):
            if str(row[key_col]).strip() == str(key_val).strip():
                sheet.delete_rows(i + 2)
                st.cache_data.clear()
                return True
    except Exception as e: st.error(f"שגיאה: {e}")
    return False

# --- פונקציות ניהול משתמשים ורשימות ---
def update_user_details(original_email, new_email, new_name, new_role, new_password=None):
    try:
        sheet = _get_sheet_object("users")
        if not sheet: return False
        data = sheet.get_all_records()
        idx = -1
        for i, row in enumerate(data):
            if str(row['username']).lower() == str(original_email).lower():
                idx = i + 2; break
        if idx != -1:
            if new_email: sheet.update_cell(idx, 1, new_email)
            sheet.update_cell(idx, 3, new_role)
            sheet.update_cell(idx, 4, new_name)
            if new_password:
                h = hash_password(new_password)
                if h: sheet.update_cell(idx, 2, h)
            st.cache_data.clear()
            return True
    except: pass
    return False

def get_settings_lists():
    df = get_worksheet_data("settings")
    if df.empty: return [], []
    fields = [x for x in df['fields'].tolist() if x]
    payment_terms = [x for x in df['payment_terms'].tolist() if x]
    return fields, payment_terms

def update_settings_list(column_name, new_list):
    try:
        sheet = _get_sheet_object("settings")
        if not sheet: return
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        other_col = 'payment_terms' if column_name == 'fields' else 'fields'
        other_list = [x for x in df[other_col].tolist() if x] if not df.empty and other_col in df.columns else []
        max_len = max(len(new_list), len(other_list))
        new_list += [''] * (max_len - len(new_list))
        other_list += [''] * (max_len - len(other_list))
        new_df = pd.DataFrame({column_name: new_list, other_col: other_list})
        sheet.clear()
        sheet.update([new_df.columns.values.tolist()] + new_df.values.tolist())
        st.cache_data.clear()
    except: pass

# --- CSS ---
def set_css():
    st.markdown("""
    <style>
        .stApp { direction: rtl; text-align: right; }
        .block-container { max-width: 100%; padding: 1.5rem 1.5rem 3rem 1.5rem; }
        h1, h2, h3, h4, h5, h6, p, div, span, label, .stMarkdown, .stButton, .stAlert, .stSelectbox, .stMultiSelect { text-align: right !important; }
        .stTextInput input, .stTextArea textarea, .stSelectbox, .stNumberInput input { direction: rtl; text-align: right; }
        .stTabs [data-baseweb="tab-list"] { flex-direction: row-reverse; justify-content: flex-end; }
        [data-testid="stDataEditor"] { direction: rtl; }
        [data-testid="stDataEditor"] div[role="columnheader"] { text-align: right !important; justify-content: flex-start !important; direction: rtl; }
        [data-testid="stDataEditor"] div[role="gridcell"] { text-align: right !important; justify-content: flex-end !important; direction: rtl; }
        .rtl-table { width: 100%; border-collapse: collapse; direction: rtl; margin-top: 10px; }
        .rtl-table th { background-color: #f0f2f6; text-align: right; padding: 10px; border-bottom: 2px solid #ddd; }
        .rtl-table td { text-align: right; padding: 10px; border-bottom: 1px solid #eee; }
        .mobile-card { background-color: white; border: 1px solid #ddd; border-radius: 8px; margin-bottom: 10px; padding: 10px; direction: rtl; text-align: right; }
        .online-container { position: fixed; bottom: 15px; left: 15px; z-index: 9999; direction: rtl; font-family: sans-serif; }
        .online-badge { background-color: #4CAF50; color: white; padding: 8px 15px; border-radius: 50px; font-size: 0.9em; cursor: default; }
        .online-list { visibility: hidden; opacity: 0; position: absolute; bottom: 45px; left: 0; background: white; color: #333; min-width: 180px; padding: 10px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.2); transition: all 0.2s; }
        .online-container:hover .online-list { visibility: visible; opacity: 1; bottom: 50px; }
        .desktop-view { display: block; } .mobile-view { display: none; }
        @media only screen and (max-width: 768px) { .desktop-view { display: none; } .mobile-view { display: block; } [data-testid="stSidebar"] { display: none !important; } }
    </style>
    """, unsafe_allow_html=True)

# --- 7. ממשקי UI ---

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
        else: st.error("שגיאה")
    if col2.button("ביטול"): st.rerun()

def show_admin_delete_table(df, all_fields_list):
    c_search, c_filter = st.columns([2, 1])
    with c_search: search = st.text_input("🔍 חיפוש למחיקה", "")
    with c_filter: cat = st.selectbox("📂 סינון למחיקה", ["הכל"] + all_fields_list)

    if not df.empty:
        if cat != "הכל": df = df[df['תחום עיסוק'].astype(str).str.contains(cat, na=False)]
        if search: df = df[df['שם הספק'].astype(str).str.contains(search, case=False, na=False) | df['טלפון'].astype(str).str.contains(search, case=False, na=False)]
        
        cols_order = ['שם הספק', 'תחום עיסוק', 'טלפון', 'אימייל', 'כתובת', 'שם איש קשר', 'תנאי תשלום', 'נוסף על ידי']
        final_cols = [c for c in cols_order if c in df.columns]
        df_disp = df[final_cols].copy()
        
        df_disp["מחיקה?"] = False

        st.warning("⚠️ סמן ספקים למחיקה בתיבה משמאל:")
        edited_df = st.data_editor(
            df_disp,
            column_config={
                "מחיקה?": st.column_config.CheckboxColumn("מחק", default=False, width="small"),
                "שם הספק": st.column_config.TextColumn(disabled=True),
                "תחום עיסוק": st.column_config.TextColumn(disabled=True),
            },
            hide_index=True,
            use_container_width=True
        )
        sel = edited_df[edited_df["מחיקה?"] == True]
        if not sel.empty:
            if st.button(f"🗑️ מחק {len(sel)} ספקים מסומנים", type="primary"):
                confirm_bulk_delete(sel["שם הספק"].tolist())
    else: st.info("אין נתונים")

def show_file_links(row):
    """פונקציית עזר להצגת קישורים"""
    files_cols = {
        '📄 הסכם חתום': 'link_agreement', 
        '🏦 אישור בנק': 'link_bank', 
        '⚖️ אישור מס וספרים': 'link_tax_books', 
        '🧾 חשבונית': 'link_invoice'
    }
    found = False
    st.markdown("##### מסמכים מצורפים:")
    cols = st.columns(len(files_cols))
    for i, (label, col_name) in enumerate(files_cols.items()):
        if col_name in row and str(row[col_name]).startswith('http'):
            cols[i].markdown(f"[{label}]({row[col_name]})", unsafe_allow_html=True)
            found = True
    if not found:
        st.write("אין מסמכים מצורפים.")

def show_suppliers_table_readonly(df, all_fields_list, is_admin=False):
    # תצוגה מיוחדת למנהל: חיפוש ופתיחת כרטיס ספק
    if is_admin:
        st.subheader("🔍 איתור וצפייה בפרטי ספק")
        
        # יצירת רשימה לחיפוש
        supplier_names = df['שם הספק'].unique().tolist()
        selected_supplier = st.selectbox("בחר ספק לצפייה בפרטים מלאים ומסמכים:", [""] + supplier_names)
        
        if selected_supplier:
            # שליפת השורה הרלוונטית
            row = df[df['שם הספק'] == selected_supplier].iloc[0]
            
            with st.container(border=True):
                c1, c2 = st.columns(2)
                with c1:
                    st.write(f"**שם הספק:** {row['שם הספק']}")
                    st.write(f"**תחום:** {row['תחום עיסוק']}")
                    st.write(f"**טלפון:** {row['טלפון']}")
                    st.write(f"**אימייל:** {row.get('אימייל', '')}")
                with c2:
                    st.write(f"**איש קשר:** {row.get('שם איש קשר', '')}")
                    st.write(f"**כתובת:** {row['כתובת']}")
                    st.write(f"**תנאי תשלום:** {row['תנאי תשלום']}")
                    st.write(f"**נוסף ע\"י:** {row.get('נוסף על ידי', '')}")
                
                st.divider()
                show_file_links(row)
        
        st.divider()
        st.subheader("📋 כל הספקים")

    # הטבלה הרגילה (לכולם)
    c_search, c_filter = st.columns([2, 1])
    with c_search: search = st.text_input("🔍 חיפוש חופשי בטבלה", "")
    with c_filter: cat = st.selectbox("📂 סינון", ["הכל"] + all_fields_list)

    if not df.empty:
        if cat != "הכל": df = df[df['תחום עיסוק'].astype(str).str.contains(cat, na=False)]
        if search: df = df[df['שם הספק'].astype(str).str.contains(search, case=False, na=False) | df['טלפון'].astype(str).str.contains(search, case=False, na=False)]
        
        cols = ['שם הספק', 'תחום עיסוק', 'טלפון', 'אימייל', 'כתובת', 'שם איש קשר', 'תנאי תשלום', 'נוסף על ידי']
        df_final = df[[c for c in cols if c in df.columns]]
        
        table_html = df_final.to_html(index=False, classes='rtl-table', border=0, escape=False).replace('\n', '')
        
        cards_html_list = []
        for _, row in df.iterrows():
            cards_html_list.append(f"""<div class="mobile-card"><details><summary><span>{row['שם הספק']} | {row['תחום עיסוק']}</span></summary><div class="card-content"><div><strong>📞:</strong> <a href="tel:{row['טלפון']}">{row['טלפון']}</a></div><div><strong>✉️:</strong> <a href="mailto:{row.get('אימייל','')}">{row.get('אימייל','')}</a></div><div><strong>📍:</strong> {row['כתובת']}</div><div><strong>👤:</strong> {row.get('שם איש קשר','')}</div><div><strong>💳:</strong> {row.get('תנאי תשלום','')}</div><div style="font-size:0.8em;color:#888;margin-top:5px">נוסף ע"י: {row.get('נוסף על ידי','')}</div></div></details></div>""")
        cards_html_full = "".join(cards_html_list)

        st.markdown(f'<div class="desktop-view">{table_html}</div><div class="mobile-view">{cards_html_full}</div>', unsafe_allow_html=True)
    else: st.info("אין נתונים")

# --- 8. ממשק ניהול משתמשים (מנהל) ---
def show_user_management():
    df_users = get_worksheet_data("users")
    df_pending = get_worksheet_data("pending_users")
    count_pending = len(df_pending) if not df_pending.empty else 0
    
    tabs = st.tabs([f"⏳ אישור ממתינים ({count_pending})", "👥 כל המשתמשים", "➕ יצירת משתמש"])
    
    with tabs[0]:
        if not df_pending.empty:
            for idx, row in df_pending.iterrows():
                with st.expander(f"{row['name']} ({row['username']})"):
                    st.write(f"בקשה: {row.get('date', 'N/A')}")
                    c1, c2 = st.columns(2)
                    if c1.button("אשר", key=f"app_u_{idx}"):
                        if add_row_to_sheet("users", [row['username'], row['password'], 'user', row['name']]):
                            delete_row_from_sheet("pending_users", "username", row['username'])
                            st.success("אושר!")
                            time.sleep(0.5); st.rerun()
                    if c2.button("דחה", key=f"rej_u_{idx}"):
                        delete_row_from_sheet("pending_users", "username", row['username'])
                        st.rerun()
        else: st.info("אין ממתינים.")

    with tabs[1]:
        if not df_users.empty:
            st.dataframe(df_users[['name', 'username', 'role']], use_container_width=True)
            st.divider()
            st.subheader("עריכת משתמש קיים")
            user_to_edit = st.selectbox("בחר משתמש:", df_users['username'].unique())
            if user_to_edit:
                user_data = df_users[df_users['username'] == user_to_edit].iloc[0]
                with st.form("edit_u"):
                    nn = st.text_input("שם", user_data['name'])
                    nr = st.selectbox("הרשאה", ["user", "admin"], index=0 if user_data['role']=='user' else 1)
                    np = st.text_input("סיסמה חדשה (השאר ריק אם אין שינוי)", type="password")
                    if st.form_submit_button("שמור שינויים"):
                        if update_user_details(user_to_edit, user_to_edit, nn, nr, np if np else None):
                            st.success("עודכן!"); time.sleep(1); st.rerun()
                if user_to_edit != st.session_state.get('username'):
                    if st.button("מחק משתמש 🗑️"):
                        if delete_row_from_sheet("users", "username", user_to_edit):
                            st.success("נמחק!"); time.sleep(1); st.rerun()
        else: st.info("אין משתמשים.")

    with tabs[2]:
        st.subheader("יצירת משתמש ידנית")
        with st.form("create_u"):
            ne = st.text_input("אימייל").lower().strip()
            nn = st.text_input("שם מלא")
            nr = st.selectbox("הרשאה", ["user", "admin"])
            np = st.text_input("סיסמה", type="password")
            if st.form_submit_button("צור משתמש"):
                if ne and nn and np:
                    if not df_users.empty and ne in df_users['username'].astype(str).str.lower().str.strip().values:
                        st.error("קיים")
                    else:
                        h = hash_password(np)
                        if h:
                            if add_row_to_sheet("users", [ne, h, nr, nn]):
                                st.success("נוצר!"); time.sleep(1); st.rerun()
                else: st.error("כל השדות חובה")

# --- 9. דף כניסה רגיל ---
def login_page():
    c1, c2, c3 = st.columns([1, 1.5, 1])
    with c2:
        st.title("🔐 כניסה למערכת")
        with st.expander("כלי למנהל (הצפנה)"):
            p = st.text_input("סיסמה להצפנה")
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
                        df_users['user_norm'] = df_users['username'].astype(str).str.lower().str.strip()
                        rec = df_users[df_users['user_norm'] == user]
                        if not rec.empty and check_password(pw, rec.iloc[0]['password']):
                            st.session_state['logged_in'] = True
                            st.session_state['username'] = user
                            st.session_state['name'] = rec.iloc[0]['name']
                            st.session_state['role'] = rec.iloc[0]['role']
                            update_active_user(user)
                            st.success("מחובר!")
                            time.sleep(0.5); st.rerun()
                        else: st.error("פרטים שגויים")
                    else: st.error("שגיאה בטעינת נתונים")

        with t2:
            with st.form("signup_form"):
                new_email = st.text_input("אימייל").lower().strip()
                new_pass = st.text_input("סיסמה", type="password")
                fname = st.text_input("שם מלא")
                if st.form_submit_button("הירשם"):
                    if not is_valid_email(new_email): st.error("אימייל לא תקין")
                    elif not validate_password_strength(new_pass): st.error("סיסמה חלשה (מינימום 6 תווים)")
                    else:
                        df_u = get_worksheet_data("users")
                        df_p = get_worksheet_data("pending_users")
                        exists = False
                        if not df_u.empty and new_email in df_u['username'].astype(str).str.lower().str.strip().values: exists = True
                        if not df_p.empty and new_email in df_p['username'].astype(str).str.lower().str.strip().values: exists = True
                        
                        if exists: st.error("משתמש קיים")
                        else:
                            hashed = hash_password(new_pass)
                            if hashed:
                                add_row_to_sheet("pending_users", [new_email, hashed, fname, str(datetime.now())])
                                st.success("נשלח לאישור")

# --- 10. ראשי ---
def main_app():
    user_role = st.session_state.get('role', 'user')
    user_name = st.session_state.get('name', 'User')
    current_email = st.session_state.get('username', '')
    update_active_user(current_email)
    
    fields, terms = get_settings_lists()
    df_supp = get_worksheet_data("suppliers")

    c1, c2, c3 = st.columns([6, 2, 1])
    c1.title(f"שלום, {user_name}")
    if c2.button("🔄 רענן"): st.cache_data.clear(); st.rerun()
    if c3.button("יציאה"): st.session_state['logged_in'] = False; st.rerun()

    with st.expander("📬 ההגשות שלי"):
        df_rej = get_worksheet_data("rejected_suppliers")
        my_rej = pd.DataFrame() 
        if not df_rej.empty:
            mask = df_rej['נוסף על ידי'].astype(str).str.contains(user_name, na=False) | df_rej['נוסף על ידי'].astype(str).str.contains(current_email, na=False)
            my_rej = df_rej[mask]
        if not my_rej.empty:
            st.error(f"יש {len(my_rej)} ספקים שנדחו.")
            st.dataframe(my_rej[['שם הספק', 'תאריך דחייה']], use_container_width=True)
        else: st.info("אין הודעות")

    st.markdown("---")

    if user_role == 'admin':
        df_pend_supp = get_worksheet_data("pending_suppliers")
        cnt_s = len(df_pend_supp) if not df_pend_supp.empty else 0

        # טאבים מעודכנים
        tabs = st.tabs(["📋 רשימת ספקים", f"⏳ אישור ספקים ({cnt_s})", f"👥 ניהול משתמשים", "➕ הוספה", "⚙️ הגדרות", "📥 יבוא", "🗑️ מחיקת ספקים"])
        
        # טאב צפייה עם יכולת פתיחת כרטיס
        with tabs[0]: 
            show_suppliers_table_readonly(df_supp, fields, is_admin=True)
        
        with tabs[1]:
            if cnt_s > 0:
                for idx, row in df_pend_supp.iterrows():
                    with st.expander(f"{row['שם הספק']}"):
                        c1, c2 = st.columns(2)
                        with c1:
                            st.write(f"**תחום:** {row['תחום עיסוק']}")
                            st.write(f"**טלפון:** {row['טלפון']}")
                            st.write(f"**אימייל:** {row.get('אימייל', '')}")
                        with c2:
                            st.write(f"**כתובת:** {row['כתובת']}")
                            st.write(f"**איש קשר:** {row.get('שם איש קשר', '')}")
                            st.write(f"**תנאי תשלום:** {row['תנאי תשלום']}")
                        
                        st.divider()
                        # תצוגת מסמכים לאישור
                        show_file_links(row)
                        st.divider()

                        is_dup, msg = check_duplicate_supplier(df_supp, row['שם הספק'], row['טלפון'], row.get('אימייל',''))
                        if is_dup: st.warning(msg)
                        
                        btn_c1, btn_c2 = st.columns(2)
                        
                        # הכנת שורה לאישור (כולל קבצים)
                        row_to_add = [row['שם הספק'], row['תחום עיסוק'], row['טלפון'], row['כתובת'], row['תנאי תשלום'], row.get('אימייל',''), row.get('שם איש קשר',''), row['נוסף על ידי']]
                        # הוספת עמודות קבצים (5 קישורים)
                        extra_cols = ['link_agreement', 'link_bank', 'link_tax_books', 'link_tax_books', 'link_invoice']
                        for ec in extra_cols:
                            row_to_add.append(row.get(ec, ''))

                        if btn_c1.button("אשר ספק ✅", key=f"s_ok_{idx}"):
                            add_row_to_sheet("suppliers", row_to_add)
                            delete_row_from_sheet("pending_suppliers", "שם הספק", row['שם הספק'])
                            st.rerun()
                        if btn_c2.button("דחה ספק ❌", key=f"s_no_{idx}"):
                            rej = row.values.tolist(); rej.append(str(datetime.now()))
                            add_row_to_sheet("rejected_suppliers", rej)
                            delete_row_from_sheet("pending_suppliers", "שם הספק", row['שם הספק'])
                            st.rerun()
            else: st.info("אין ספקים ממתינים")

        with tabs[2]: show_user_management()

        with tabs[3]:
            st.write("מילוי פרטי ספק חדש:")
            with st.form("a_add"):
                s_name = st.text_input("שם *")
                s_f = st.multiselect("תחום *", fields)
                s_p = st.text_input("טלפון *")
                s_e = st.text_input("אימייל *")
                s_c = st.text_input("איש קשר")
                s_a = st.text_input("כתובת *")
                s_pay = st.selectbox("תנאי *", terms)
                
                st.markdown("---")
                st.write("📂 העלאת מסמכים (חובה):")
                f1 = st.file_uploader("הסכם חתום *", type=['pdf','png','jpg','jpeg'])
                f2 = st.file_uploader("אישור ניהול חשבון *", type=['pdf','png','jpg','jpeg'])
                f3_combined = st.file_uploader("אישור ניכוי מס וניהול ספרים *", type=['pdf','png','jpg','jpeg'])
                f5 = st.file_uploader("דוגמת חשבונית *", type=['pdf','png','jpg','jpeg'])
                
                if st.form_submit_button("שמור"):
                    files_map = {'agreement': f1, 'bank': f2, 'tax_books': f3_combined, 'invoice': f5}
                    valid, msg = validate_supplier_form(df_supp, s_name, s_f, s_p, s_e, s_a, s_pay, files_map)
                    
                    if valid:
                        with st.spinner("מעלה קבצים..."):
                            l_ag = upload_file_to_drive(f1, s_name + "_agree")
                            l_bk = upload_file_to_drive(f2, s_name + "_bank")
                            l_tb = upload_file_to_drive(f3_combined, s_name + "_taxbooks")
                            l_in = upload_file_to_drive(f5, s_name + "_inv")
                            
                            links_part = [l_ag, l_bk, l_tb, l_tb, l_in]
                            
                            row_data = [s_name, ", ".join(s_f), s_p, s_a, s_pay, s_e, s_c, user_name] + links_part
                            add_row_to_sheet("suppliers", row_data)
                            st.success("נוסף בהצלחה!")
                            time.sleep(1); st.rerun()
                    else: st.error(msg)

        with tabs[4]:
            c1, c2 = st.columns(2)
            with c1:
                nf = st.text_input("תחום חדש")
                if st.button("הוסף תחום") and nf: fields.append(nf); update_settings_list("fields", fields); st.rerun()
                rf = st.selectbox("מחק תחום", [""]+fields)
                if st.button("מחק תחום") and rf: fields.remove(rf); update_settings_list("fields", fields); st.rerun()
            with c2:
                nt = st.text_input("תנאי חדש")
                if st.button("הוסף תנאי") and nt: terms.append(nt); update_settings_list("payment_terms", terms); st.rerun()
                rt = st.selectbox("מחק תנאי", [""]+terms)
                if st.button("מחק תנאי") and rt: terms.remove(rt); update_settings_list("payment_terms", terms); st.rerun()

        with tabs[5]:
            buf = generate_excel_template()
            st.download_button("📥 הורד תבנית", buf, "template.xlsx")
            up = st.file_uploader("העלה אקסל", type="xlsx")
            if up and st.button("טען"):
                try:
                    ndf = pd.read_excel(up).astype(str).replace('nan', '')
                    req = ['שם הספק', 'תחום עיסוק', 'טלפון', 'אימייל', 'כתובת', 'שם איש קשר', 'תנאי תשלום']
                    if not all(c in ndf.columns for c in req): st.error("כותרות שגויות")
                    else:
                        valid_r = []; errs = []
                        for idx, row in ndf.iterrows():
                            if not row['שם הספק'].strip(): errs.append(f"שורה {idx+2}: חסר שם"); continue
                            valid_r.append([row[c].strip() for c in req] + [user_name])
                        if errs: 
                            for e in errs: st.error(e)
                        else:
                            cl = get_client(); sh = cl.open(SHEET_NAME).worksheet("suppliers")
                            sh.append_rows(valid_r); st.success("נטען!"); st.cache_data.clear()
                except Exception as e: st.error(str(e))

        with tabs[6]: show_admin_delete_table(df_supp, fields)

    else:
        utabs = st.tabs(["🔎 חיפוש", "➕ הצעה"])
        with utabs[0]: show_suppliers_table_readonly(df_supp, fields)
        with utabs[1]:
            with st.form("u_a"):
                s_name = st.text_input("שם *")
                s_f = st.multiselect("תחום *", fields)
                s_p = st.text_input("טלפון *")
                s_e = st.text_input("אימייל *")
                s_c = st.text_input("איש קשר")
                s_a = st.text_input("כתובת *")
                s_pay = st.selectbox("תנאי *", terms)
                
                st.markdown("---")
                st.write("📂 העלאת מסמכים (חובה):")
                f1 = st.file_uploader("הסכם חתום *", type=['pdf','png','jpg','jpeg'])
                f2 = st.file_uploader("אישור ניהול חשבון *", type=['pdf','png','jpg','jpeg'])
                f3_combined = st.file_uploader("אישור ניכוי מס וניהול ספרים *", type=['pdf','png','jpg','jpeg'])
                f5 = st.file_uploader("דוגמת חשבונית *", type=['pdf','png','jpg','jpeg'])

                if st.form_submit_button("שלח"):
                    files_map = {'agreement': f1, 'bank': f2, 'tax_books': f3_combined, 'invoice': f5}
                    valid, msg = validate_supplier_form(df_supp, s_name, s_f, s_p, s_e, s_a, s_pay, files_map)
                    if valid:
                        with st.spinner("מעלה קבצים ושולח לאישור..."):
                            l_ag = upload_file_to_drive(f1, s_name + "_agree")
                            l_bk = upload_file_to_drive(f2, s_name + "_bank")
                            l_tb = upload_file_to_drive(f3_combined, s_name + "_taxbooks")
                            l_in = upload_file_to_drive(f5, s_name + "_inv")
                            
                            links = [l_ag, l_bk, l_tb, l_tb, l_in]
                            
                            row_data = [s_name, ", ".join(s_f), s_p, s_a, s_pay, s_e, s_c, user_name] + links + [str(datetime.now())]
                            
                            add_row_to_sheet("pending_suppliers", row_data)
                            st.success("נשלח לאישור!")
                    else: st.error(msg)

    cnt, names = get_online_users_count_and_names()
    names_html = "<br>".join(names) if names else "אין"
    tooltip = f'<div class="online-list"><strong>מחוברים:</strong><br>{names_html}</div>'
    st.markdown(f'<div class="online-container">{tooltip}<div class="online-badge">🟢 מחוברים: {cnt}</div></div>', unsafe_allow_html=True)

# --- 10. הרצה ---
set_css()
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if not st.session_state['logged_in']: login_page()
else: main_app()
