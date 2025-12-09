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

# --- 1. הגדרת עמוד (חובה שורה ראשונה) ---
st.set_page_config(page_title="ניהול ספקים", layout="wide", initial_sidebar_state="expanded")

# --- 2. הגדרות וקבועים ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "ניהול ספקים"
BCRYPT_ROUNDS = 12

# הגדרת לוגים
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 3. פונקציות עזר (לוגיקה ואבטחה) ---

def normalize_text(text):
    if text is None: return ""
    return str(text).strip().lower()

def validate_password_strength(password):
    return len(password) >= 8

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

def validate_supplier_form(df, name, fields, phone, email, addr, pay):
    if not (name and fields and phone and email and addr and pay):
        return False, "נא למלא את כל שדות החובה"
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

# --- 4. CSS עיצוב ---
def set_css():
    st.markdown("""
    <style>
        .stApp { direction: rtl; text-align: right; }
        .block-container { max-width: 100%; padding: 2rem 2rem 3rem 2rem; }
        
        h1, h2, h3, h4, h5, h6, p, div, span, label, .stMarkdown, .stButton, .stAlert, .stSelectbox, .stMultiSelect { 
            text-align: right !important; 
        }
        .stTextInput input, .stTextArea textarea, .stSelectbox, .stNumberInput input { 
            direction: rtl; text-align: right; 
        }
        .stTabs [data-baseweb="tab-list"] { 
            flex-direction: row-reverse; justify-content: flex-end; 
        }
        
        /* טבלת מנהל */
        [data-testid="stDataEditor"] { direction: rtl; }
        [data-testid="stDataEditor"] div[role="columnheader"] { text-align: right !important; justify-content: flex-start !important; direction: rtl; }
        [data-testid="stDataEditor"] div[role="gridcell"] { text-align: right !important; justify-content: flex-end !important; direction: rtl; }

        /* טבלה רגילה */
        .rtl-table { width: 100%; border-collapse: collapse; direction: rtl; margin-top: 10px; }
        .rtl-table th { background-color: #f0f2f6; text-align: right !important; padding: 10px; border-bottom: 2px solid #ddd; color: #333; font-weight: bold; white-space: nowrap; }
        .rtl-table td { text-align: right !important; padding: 10px; border-bottom: 1px solid #eee; color: #333; }

        /* מובייל */
        .mobile-card { background-color: white; border: 1px solid #ddd; border-radius: 8px; margin-bottom: 12px; padding: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); direction: rtl; text-align: right !important; }
        .mobile-card summary { font-weight: bold; cursor: pointer; color: #000; list-style: none; outline: none; display: flex; justify-content: space-between; align-items: center; }
        .mobile-card summary::after { content: "+"; font-size: 1.2em; color: #666; margin-right: 10px;}
        .mobile-card details[open] summary::after { content: "-"; }
        .mobile-card .card-content { margin-top: 10px; padding-top: 10px; border-top: 1px solid #eee; font-size: 0.95em; color: #333; }
        .mobile-card a { color: #0068c9; text-decoration: none; font-weight: bold; }
        
        /* מונה מחוברים */
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

# --- 5. אינטגרציה עם Google Sheets ---

def get_client():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error("שגיאת התחברות ל-Google Sheets")
        return None

@st.cache_data(ttl=300)
def get_worksheet_data(worksheet_name):
    try:
        # Client פנימי לשימוש בקאש
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME).worksheet(worksheet_name)
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame()

def _get_sheet_object(worksheet_name):
    """פונקציית עזר לכתיבה (ללא קאש)"""
    try:
        client = get_client()
        return client.open(SHEET_NAME).worksheet(worksheet_name)
    except: return None

def update_active_user(username):
    current_time = datetime.now()
    if 'last_api_update' in st.session_state:
        if (current_time - st.session_state['last_api_update']).seconds < 60:
            return
    try:
        sheet = _get_sheet_object("active_users")
        if not sheet: return
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        ts_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
        username_norm = normalize_text(username)
        
        found = False
        if not df.empty:
            for idx, row in df.iterrows():
                if normalize_text(row['username']) == username_norm:
                    sheet.update_cell(idx + 2, 2, ts_str)
                    found = True
                    break
        if not found:
            sheet.append_row([username, ts_str])
        st.session_state['last_api_update'] = current_time
    except: pass

def get_online_users_count_and_names():
    try:
        df_active = get_worksheet_data("active_users")
        df_users = get_worksheet_data("users")
        if df_active.empty: return 0, []
        
        now = datetime.now()
        df_active['last_seen'] = pd.to_datetime(df_active['last_seen'], errors='coerce')
        active_mask = (now - df_active['last_seen']).dt.total_seconds() < 300
        df_active = df_active[active_mask].copy()
        
        if df_active.empty: return 0, []

        df_active['key'] = df_active['username'].astype(str).str.strip().str.lower()
        active_names = df_active['username'].tolist()
        
        if not df_users.empty:
            df_users['key'] = df_users['username'].astype(str).str.strip().str.lower()
            merged = pd.merge(df_active, df_users[['key', 'name']], on='key', how='left')
            merged['display'] = merged['name'].fillna(merged['username'])
            active_names = merged['display'].tolist()
            
        return len(active_names), active_names
    except: return 0, []

def add_row_to_sheet(worksheet_name, row_data):
    try:
        sheet = _get_sheet_object(worksheet_name)
        if sheet:
            sheet.append_row(row_data)
            st.cache_data.clear()
            return True
    except Exception as e:
        st.error(f"שגיאה: {e}")
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
    except Exception as e:
        st.error(f"שגיאה: {e}")
    return False

# --- פונקציות ניהול משתמשים (חדש) ---

def update_user_details(original_email, new_email, new_name, new_role, new_password=None):
    try:
        sheet = _get_sheet_object("users")
        if not sheet: return False
        data = sheet.get_all_records()
        
        # חיפוש שורה
        row_idx = -1
        for i, row in enumerate(data):
            if str(row['username']).strip().lower() == str(original_email).strip().lower():
                row_idx = i + 2
                break
        
        if row_idx == -1: return False
        
        # עדכון תאים (עמודות: 1=username, 2=password, 3=role, 4=name)
        # עדכון אימייל
        if new_email and new_email != original_email:
            sheet.update_cell(row_idx, 1, new_email)
        # עדכון תפקיד
        sheet.update_cell(row_idx, 3, new_role)
        # עדכון שם
        sheet.update_cell(row_idx, 4, new_name)
        # עדכון סיסמה אם סופקה
        if new_password:
            hashed = hash_password(new_password)
            if hashed:
                sheet.update_cell(row_idx, 2, hashed)
        
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"שגיאה בעדכון משתמש: {e}")
        return False

# --- 6. הגדרות מנהל ---
def get_settings_lists():
    df = get_worksheet_data("settings")
    if df.empty: return [], []
    fields = [x for x in df['fields'].tolist() if str(x).strip()]
    payment_terms = [x for x in df['payment_terms'].tolist() if str(x).strip()]
    return fields, payment_terms

def update_settings_list(column_name, new_list):
    try:
        sheet = _get_sheet_object("settings")
        if not sheet: return
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
    except: st.error("שגיאה בעדכון הגדרות")

# --- 7. קומפוננטות UI ---

@st.dialog("אישור מחיקה מרובה")
def confirm_bulk_delete(suppliers_to_delete):
    st.write(f"למחוק {len(suppliers_to_delete)} ספקים?")
    c1, c2 = st.columns(2)
    if c1.button("כן, מחק", type="primary"):
        prog = st.progress(0)
        cnt = 0
        for i, name in enumerate(suppliers_to_delete):
            if delete_row_from_sheet("suppliers", "שם הספק", name): cnt += 1
            prog.progress((i+1)/len(suppliers_to_delete))
        if cnt > 0:
            st.success("נמחקו!")
            time.sleep(1)
            st.rerun()
    if c2.button("ביטול"): st.rerun()

def show_admin_delete_table(df, all_fields_list):
    c1, c2 = st.columns([2, 1])
    search = c1.text_input("🔍 חיפוש למחיקה", "")
    cat = c2.selectbox("📂 סינון למחיקה", ["הכל"] + all_fields_list)

    if not df.empty:
        if cat != "הכל": df = df[df['תחום עיסוק'].astype(str).str.contains(cat, na=False)]
        if search: df = df[df['שם הספק'].astype(str).str.contains(search, case=False, na=False) | df['טלפון'].astype(str).str.contains(search, case=False, na=False)]
        
        cols = ['שם הספק', 'תחום עיסוק', 'טלפון', 'אימייל', 'כתובת', 'שם איש קשר', 'תנאי תשלום', 'נוסף על ידי']
        df_disp = df[[c for c in cols if c in df.columns]].copy()
        df_disp["מחיקה?"] = False

        st.warning("⚠️ סמן ספקים למחיקה:")
        edited = st.data_editor(
            df_disp,
            column_config={
                "מחיקה?": st.column_config.CheckboxColumn("מחק", default=False, width="small"),
                "שם הספק": st.column_config.TextColumn(disabled=True),
                "תחום עיסוק": st.column_config.TextColumn(disabled=True),
                # ניתן להוסיף עוד עמודות כ-Read only
            },
            hide_index=True, use_container_width=True
        )
        sel = edited[edited["מחיקה?"] == True]
        if not sel.empty:
            if st.button(f"🗑️ מחק {len(sel)} ספקים", type="primary"):
                confirm_bulk_delete(sel["שם הספק"].tolist())
    else: st.info("אין נתונים")

def show_suppliers_table_readonly(df, all_fields_list):
    c1, c2 = st.columns([2, 1])
    search = c1.text_input("🔍 חיפוש", "")
    cat = c2.selectbox("📂 סינון", ["הכל"] + all_fields_list)

    if not df.empty:
        if cat != "הכל": df = df[df['תחום עיסוק'].astype(str).str.contains(cat, na=False)]
        if search: df = df[df['שם הספק'].astype(str).str.contains(search, case=False, na=False) | df['טלפון'].astype(str).str.contains(search, case=False, na=False)]
        
        cols = ['שם הספק', 'תחום עיסוק', 'טלפון', 'אימייל', 'כתובת', 'שם איש קשר', 'תנאי תשלום', 'נוסף על ידי']
        df_final = df[[c for c in cols if c in df.columns]]
        
        # HTML מחשב
        html = df_final.to_html(index=False, classes='rtl-table', border=0, escape=False).replace('\n', '')
        
        # HTML טלפון
        cards = ""
        for _, row in df.iterrows():
            cards += f"""<div class="mobile-card"><details><summary><span>{row['שם הספק']} | {row['תחום עיסוק']}</span></summary><div class="card-content"><div><strong>📞:</strong> <a href="tel:{row['טלפון']}">{row['טלפון']}</a></div><div><strong>✉️:</strong> <a href="mailto:{row.get('אימייל','')}">{row.get('אימייל','')}</a></div><div><strong>📍:</strong> {row['כתובת']}</div><div><strong>👤:</strong> {row.get('שם איש קשר','')}</div><div><strong>💳:</strong> {row.get('תנאי תשלום','')}</div><div style="font-size:0.8em;color:#888;margin-top:5px">נוסף ע"י: {row.get('נוסף על ידי','')}</div></div></details></div>"""

        st.markdown(f'<div class="desktop-view">{html}</div><div class="mobile-view">{cards}</div>', unsafe_allow_html=True)
    else: st.info("אין נתונים")

# --- ממשק ניהול משתמשים החדש ---
def show_user_management():
    # שליפת נתונים
    df_users = get_worksheet_data("users")
    df_pending = get_worksheet_data("pending_users")
    
    count_pending = len(df_pending) if not df_pending.empty else 0
    
    # טאבים פנימיים
    tabs = st.tabs([f"⏳ אישור ממתינים ({count_pending})", "👥 כל המשתמשים", "➕ יצירת משתמש"])
    
    # 1. אישור ממתינים
    with tabs[0]:
        if not df_pending.empty:
            for idx, row in df_pending.iterrows():
                with st.expander(f"{row['name']} ({row['username']})"):
                    st.write(f"תאריך בקשה: {row.get('date', 'N/A')}")
                    c1, c2 = st.columns(2)
                    if c1.button("אשר", key=f"app_u_{idx}"):
                        if add_row_to_sheet("users", [row['username'], row['password'], 'user', row['name']]):
                            delete_row_from_sheet("pending_users", "username", row['username'])
                            st.success("אושר!")
                            time.sleep(0.5)
                            st.rerun()
                    if c2.button("דחה", key=f"rej_u_{idx}"):
                        delete_row_from_sheet("pending_users", "username", row['username'])
                        st.rerun()
        else:
            st.info("אין משתמשים ממתינים.")

    # 2. ניהול משתמשים (עריכה/מחיקה)
    with tabs[1]:
        if not df_users.empty:
            st.dataframe(df_users[['name', 'username', 'role']], use_container_width=True)
            
            st.divider()
            st.subheader("עריכת משתמש קיים")
            
            user_to_edit = st.selectbox("בחר משתמש לעריכה:", df_users['username'].unique())
            
            if user_to_edit:
                # שליפת נתוני המשתמש הנבחר
                user_data = df_users[df_users['username'] == user_to_edit].iloc[0]
                
                with st.form("edit_user_form"):
                    new_name = st.text_input("שם מלא", value=user_data['name'])
                    new_role = st.selectbox("הרשאה", ["user", "admin"], index=0 if user_data['role']=='user' else 1)
                    new_pass = st.text_input("סיסמה חדשה (השאר ריק אם אין שינוי)", type="password")
                    
                    c1, c2 = st.columns(2)
                    submitted = c1.form_submit_button("שמור שינויים", type="primary")
                    delete_btn = c2.form_submit_button("מחק משתמש 🗑️", type="secondary") # כפתור בתוך פורם הוא טריקי, עדיף מחוץ לו אבל ננסה
                    
                    if submitted:
                        if update_user_details(user_to_edit, user_to_edit, new_name, new_role, new_pass if new_pass else None):
                            st.success("הפרטים עודכנו בהצלחה!")
                            time.sleep(1)
                            st.rerun()
                    
                    if delete_btn:
                        # אישור מחיקה ידני בגלל מגבלות פורם
                        if user_to_edit == st.session_state.get('username'):
                            st.error("לא ניתן למחוק את עצמך.")
                        else:
                            if delete_row_from_sheet("users", "username", user_to_edit):
                                st.success("המשתמש נמחק.")
                                time.sleep(1)
                                st.rerun()
        else:
            st.info("אין משתמשים במערכת.")

    # 3. יצירת משתמש ישירה
    with tabs[2]:
        st.subheader("יצירת משתמש חדש (עוקף אישור)")
        with st.form("create_user_direct"):
            new_email = st.text_input("אימייל (שם משתמש)").lower().strip()
            new_name = st.text_input("שם מלא")
            new_role = st.selectbox("הרשאה", ["user", "admin"])
            new_pass = st.text_input("סיסמה", type="password")
            
            if st.form_submit_button("צור משתמש"):
                if not new_email or not new_name or not new_pass:
                    st.error("כל השדות חובה")
                elif not is_valid_email(new_email):
                    st.error("אימייל לא תקין")
                elif not validate_password_strength(new_pass):
                    st.error("סיסמה חייבת להיות לפחות 8 תווים")
                else:
                    # בדיקת כפילות
                    if not df_users.empty and new_email in df_users['username'].astype(str).str.lower().str.strip().values:
                        st.error("משתמש קיים")
                    else:
                        hashed = hash_password(new_pass)
                        if hashed:
                            if add_row_to_sheet("users", [new_email, hashed, new_role, new_name]):
                                st.success("המשתמש נוצר בהצלחה!")
                                time.sleep(1)
                                st.rerun()

# --- 8. מסכי התחברות והרשמה ---
def login_page():
    c1, c2, c3 = st.columns([1, 1.5, 1])
    with c2:
        st.title("🔐 כניסה למערכת")
        with st.expander("כלי להצפנת סיסמה"):
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
                            time.sleep(0.5)
                            st.rerun()
                        else: st.error("פרטים שגויים")
                    else: st.error("שגיאה בטעינת נתונים")

        with t2:
            with st.form("signup_form"):
                new_email = st.text_input("אימייל").lower().strip()
                new_pass = st.text_input("סיסמה", type="password")
                fname = st.text_input("שם מלא")
                if st.form_submit_button("הירשם"):
                    if not is_valid_email(new_email): st.error("אימייל לא תקין")
                    elif not validate_password_strength(new_pass): st.error("סיסמה חלשה (מינימום 8 תווים)")
                    else:
                        df_u = get_worksheet_data("users")
                        df_p = get_worksheet_data("pending_users")
                        exists = False
                        if not df_u.empty and new_email in df_u['username'].astype(str).str.lower().str.strip().values: exists=True
                        if not df_p.empty and new_email in df_p['username'].astype(str).str.lower().str.strip().values: exists=True
                        
                        if exists: st.error("משתמש קיים")
                        else:
                            hashed = hash_password(new_pass)
                            if hashed:
                                add_row_to_sheet("pending_users", [new_email, hashed, fname, str(datetime.now())])
                                st.success("נשלח לאישור")

# --- 9. אפליקציה ראשית ---
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
        if not df_rej.empty:
            mask = df_rej['נוסף על ידי'].astype(str).str.contains(user_name, na=False)
            my_rej = df_rej[mask]
            if not my_rej.empty:
                st.error(f"נדחו: {len(my_rej)}")
                st.dataframe(my_rej[['שם הספק', 'תאריך דחייה']], use_container_width=True)
            else: st.info("אין הודעות")
        else: st.info("אין הודעות")

    st.markdown("---")

    if user_role == 'admin':
        # ספירת ממתינים לצורך שם הטאב
        df_pend_users = get_worksheet_data("pending_users")
        count_users = len(df_pend_users) if not df_pend_users.empty else 0
        
        df_pend_supp = get_worksheet_data("pending_suppliers")
        count_supp = len(df_pend_supp) if not df_pend_supp.empty else 0

        # טאבים מעודכנים למנהל
        tabs = st.tabs(["📋 רשימת ספקים", f"⏳ אישור ספקים ({count_supp})", f"👥 ניהול משתמשים ({count_users})", "➕ הוספה", "⚙️ הגדרות", "📥 יבוא", "🗑️ מחיקת ספקים"])
        
        # 1. רשימה
        with tabs[0]: show_suppliers_table_readonly(df_supp, fields)
        
        # 2. אישור ספקים
        with tabs[1]:
            if count_supp > 0:
                for idx, row in df_pend_supp.iterrows():
                    with st.expander(f"{row['שם הספק']}"):
                        st.write(f"תחום: {row['תחום עיסוק']} | טלפון: {row['טלפון']}")
                        is_dup, msg = check_duplicate_supplier(df_supp, row['שם הספק'], row['טלפון'], row.get('אימייל',''))
                        if is_dup: st.warning(msg)
                        c1, c2 = st.columns(2)
                        if c1.button("אשר", key=f"ok_s_{idx}"):
                            add_row_to_sheet("suppliers", [row['שם הספק'], row['תחום עיסוק'], row['טלפון'], row['כתובת'], row['תנאי תשלום'], row.get('אימייל',''), row.get('שם איש קשר',''), row['נוסף על ידי']])
                            delete_row_from_sheet("pending_suppliers", "שם הספק", row['שם הספק'])
                            st.rerun()
                        if c2.button("דחה", key=f"no_s_{idx}"):
                            rej_row = row.values.tolist()
                            rej_row.append(str(datetime.now()))
                            add_row_to_sheet("rejected_suppliers", rej_row)
                            delete_row_from_sheet("pending_suppliers", "שם הספק", row['שם הספק'])
                            st.rerun()
            else: st.info("אין ספקים ממתינים")

        # 3. ניהול משתמשים (חדש!)
        with tabs[2]:
            show_user_management()

        # 4. הוספה
        with tabs[3]:
            with st.form("adm_add"):
                s_name = st.text_input("שם *")
                s_fields = st.multiselect("תחום *", fields)
                s_phone = st.text_input("טלפון *")
                s_email = st.text_input("אימייל *")
                s_contact = st.text_input("איש קשר")
                s_addr = st.text_input("כתובת *")
                s_pay = st.selectbox("תנאי תשלום *", terms)
                if st.form_submit_button("שמור"):
                    valid, msg = validate_supplier_form(df_supp, s_name, s_fields, s_phone, s_email, s_addr, s_pay)
                    if valid:
                        add_row_to_sheet("suppliers", [s_name, ", ".join(s_fields), s_phone, s_addr, s_pay, s_email, s_contact, user_name])
                        st.success("נוסף!")
                        time.sleep(1); st.rerun()
                    else: st.error(msg)

        # 5. הגדרות
        with tabs[4]:
            c1, c2 = st.columns(2)
            with c1:
                new_f = st.text_input("תחום חדש")
                if st.button("הוסף תחום"):
                    if new_f: 
                        fields.append(new_f)
                        update_settings_list("fields", fields)
                        st.rerun()
                rem_f = st.selectbox("מחק תחום", [""] + fields)
                if st.button("מחק תחום"):
                    if rem_f: 
                        fields.remove(rem_f)
                        update_settings_list("fields", fields)
                        st.rerun()
            with c2:
                new_t = st.text_input("תנאי חדש")
                if st.button("הוסף תנאי"):
                    if new_t:
                        terms.append(new_t)
                        update_settings_list("payment_terms", terms)
                        st.rerun()
                rem_t = st.selectbox("מחק תנאי", [""] + terms)
                if st.button("מחק תנאי"):
                    if rem_t:
                        terms.remove(rem_t)
                        update_settings_list("payment_terms", terms)
                        st.rerun()

        # 6. יבוא
        with tabs[5]:
            buf = generate_excel_template()
            st.download_button("📥 הורד תבנית", buf, "template.xlsx")
            up = st.file_uploader("העלה אקסל", type="xlsx")
            if up and st.button("טען"):
                try:
                    ndf = pd.read_excel(up).astype(str).replace('nan', '')
                    req_cols = ['שם הספק', 'תחום עיסוק', 'טלפון', 'אימייל', 'כתובת', 'שם איש קשר', 'תנאי תשלום']
                    if not all(c in ndf.columns for c in req_cols):
                        st.error("כותרות לא תואמות")
                    else:
                        valid_rows = []
                        errs = []
                        for idx, row in ndf.iterrows():
                            # בדיקה בסיסית
                            if not row['שם הספק'].strip(): 
                                errs.append(f"שורה {idx+2}: חסר שם")
                                continue
                            valid_rows.append([row[c].strip() for c in req_cols] + [user_name])
                        
                        if errs: 
                            for e in errs: st.error(e)
                        else:
                            # שימוש בקליינט לכתיבה
                            cl = get_client()
                            sh = cl.open(SHEET_NAME).worksheet("suppliers")
                            sh.append_rows(valid_rows)
                            st.success("נטען!")
                            st.cache_data.clear()
                except Exception as e: st.error(str(e))

        # 7. מחיקה
        with tabs[6]:
            show_admin_delete_table(df_supp, fields)

    else:
        # משתמש רגיל
        utabs = st.tabs(["🔎 חיפוש", "➕ הצעה"])
        with utabs[0]: show_suppliers_table_readonly(df_supp, fields)
        with utabs[1]:
            with st.form("u_add"):
                s_name = st.text_input("שם *")
                s_fields = st.multiselect("תחום *", fields)
                s_phone = st.text_input("טלפון *")
                s_email = st.text_input("אימייל *")
                s_contact = st.text_input("איש קשר")
                s_addr = st.text_input("כתובת *")
                s_pay = st.selectbox("תנאי תשלום *", terms)
                if st.form_submit_button("שלח"):
                    valid, msg = validate_supplier_form(df_supp, s_name, s_fields, s_phone, s_email, s_addr, s_pay)
                    if valid:
                        add_row_to_sheet("pending_suppliers", [s_name, ", ".join(s_fields), s_phone, s_addr, s_pay, s_email, s_contact, user_name, str(datetime.now())])
                        st.success("נשלח!")
                    else: st.error(msg)

    # Online indicator
    cnt, names = get_online_users_count_and_names()
    names_html = "<br>".join(names) if names else "אין"
    tooltip = ""
    if user_role == 'admin':
        tooltip = f'<div class="online-list"><strong>מחוברים:</strong><br>{names_html}</div>'
    
    st.markdown(f"""
    <div class="online-container">
        {tooltip}
        <div class="online-badge">🟢 מחוברים: {cnt}</div>
    </div>
    """, unsafe_allow_html=True)

# --- 10. הרצה ---
set_css()
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if not st.session_state['logged_in']: login_page()
else: main_app()
