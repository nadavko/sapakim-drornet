import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import bcrypt
import re

# --- הגדרת עמוד רחב (חובה בהתחלה) ---
st.set_page_config(page_title="ניהול ספקים", layout="wide", initial_sidebar_state="expanded")

# --- הגדרות ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "ניהול ספקים"

# --- פונקציות עזר וולידציה ---
def hash_password(password):
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8')

def check_password(plain_text_password, hashed_password):
    try:
        return bcrypt.checkpw(plain_text_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except ValueError:
        return False

def is_valid_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None

def check_duplicate_supplier(df, name, phone, email):
    if df.empty:
        return False, ""
    name = str(name).strip()
    phone = str(phone).strip()
    email = str(email).strip().lower()
    
    if name in df['שם הספק'].astype(str).str.strip().values:
        return True, f"שגיאה: ספק בשם '{name}' כבר קיים."
    if phone in df['טלפון'].astype(str).str.strip().values:
        return True, f"שגיאה: טלפון '{phone}' כבר קיים."
    if email and email in df['אימייל'].astype(str).str.strip().str.lower().values:
        return True, f"שגיאה: אימייל '{email}' כבר קיים."
    return False, ""

# --- CSS עיצוב ---
def set_css():
    st.markdown("""
    <style>
        /* כיוון כללי */
        .stApp { direction: rtl; text-align: right; }
        
        /* הרחבת הקונטיינר הראשי */
        .block-container {
            max-width: 100%;
            padding-top: 2rem;
            padding-right: 2rem;
            padding-left: 2rem;
            padding-bottom: 2rem;
        }

        /* יישור אלמנטים כללי */
        h1, h2, h3, h4, h5, h6, p, div, span, label, .stMarkdown, .stButton, .stAlert, .stSelectbox, .stMultiSelect { text-align: right !important; }
        .stTextInput input, .stTextArea textarea, .stSelectbox, .stNumberInput input { direction: rtl; text-align: right; }
        .stTabs [data-baseweb="tab-list"] { flex-direction: row-reverse; justify-content: flex-end; }
        
        /* ---- תיקון אגרסיבי לטבלה של המנהל (st.data_editor) ---- */
        [data-testid="stDataFrame"], [data-testid="stDataEditor"] {
            direction: rtl !important;
        }
        /* כותרות */
        [data-testid="stDataFrame"] th, [data-testid="stDataEditor"] th {
            text-align: right !important;
            direction: rtl !important;
        }
        /* תאים */
        [data-testid="stDataFrame"] td, [data-testid="stDataEditor"] td {
            text-align: right !important;
            direction: rtl !important;
        }
        
        /* טבלה רגילה (HTML) למשתמש */
        .rtl-table { width: 100%; border-collapse: collapse; direction: rtl; margin-top: 10px; }
        .rtl-table th { background-color: #f0f2f6; text-align: right !important; padding: 10px; border-bottom: 2px solid #ddd; color: #333; font-weight: bold; white-space: nowrap; }
        .rtl-table td { text-align: right !important; padding: 10px; border-bottom: 1px solid #eee; color: #333; }

        /* כרטיסיות מובייל */
        .mobile-card { background-color: white; border: 1px solid #ddd; border-radius: 8px; margin-bottom: 12px; padding: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); direction: rtl; text-align: right !important; }
        .mobile-card summary { font-weight: bold; cursor: pointer; color: #000; list-style: none; outline: none; display: flex; justify-content: space-between; align-items: center; }
        .mobile-card summary::after { content: "+"; font-size: 1.2em; margin-right: 10px; color: #666; }
        .mobile-card details[open] summary::after { content: "-"; }
        .mobile-card .card-content { margin-top: 10px; padding-top: 10px; border-top: 1px solid #eee; font-size: 0.95em; color: #333; }
        .mobile-card a { color: #0068c9; text-decoration: none; font-weight: bold; }
        
        /* מונה משתמשים */
        .online-counter { position: fixed; bottom: 10px; left: 10px; background-color: #4CAF50; color: white; padding: 5px 10px; border-radius: 20px; font-size: 0.8em; z-index: 9999; box-shadow: 0 2px 5px rgba(0,0,0,0.2); }

        /* הגדרות רספונסיביות */
        .desktop-view { display: block; }
        .mobile-view { display: none; }
        
        @media only screen and (max-width: 768px) {
            .desktop-view { display: none; }
            .mobile-view { display: block; }
            [data-testid="stSidebar"] { display: none !important; }
            /* צמצום שוליים במובייל */
            .block-container { 
                padding-top: 1rem !important; 
                padding-left: 0.5rem !important;
                padding-right: 0.5rem !important;
            }
        }
    </style>
    """, unsafe_allow_html=True)

# --- חיבור לגוגל ---
def get_client():
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    client = gspread.authorize(creds)
    return client

def get_worksheet_data(worksheet_name):
    try:
        client = get_client()
        sheet = client.open(SHEET_NAME).worksheet(worksheet_name)
        data = sheet.get_all_records()
        return pd.DataFrame(data), sheet
    except Exception:
        return pd.DataFrame(), None

# --- ניהול משתמשים מחוברים ---
def update_active_user(username):
    current_time = datetime.now()
    if 'last_api_update' in st.session_state:
        if (current_time - st.session_state['last_api_update']).seconds < 60:
            return
    try:
        client = get_client()
        sheet = client.open(SHEET_NAME).worksheet("active_users")
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        timestamp_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
        if not df.empty and username in df['username'].astype(str).values:
            idx = df.index[df['username'] == username].tolist()[0] + 2
            sheet.update_cell(idx, 2, timestamp_str)
        else:
            sheet.append_row([username, timestamp_str])
        st.session_state['last_api_update'] = current_time
    except: pass

def get_online_users_count_and_names():
    try:
        df, _ = get_worksheet_data("active_users")
        if df.empty: return 0, []
        now = datetime.now()
        active_names = []
        for _, row in df.iterrows():
            try:
                last_seen = datetime.strptime(str(row['last_seen']), "%Y-%m-%d %H:%M:%S")
                if (now - last_seen).total_seconds() < 300: 
                    active_names.append(row['username'])
            except: continue
        return len(active_names), active_names
    except: return 0, []

# --- פעולות בסיס ---
def add_row_to_sheet(worksheet_name, row_data):
    client = get_client()
    sheet = client.open(SHEET_NAME).worksheet(worksheet_name)
    sheet.append_row(row_data)

def delete_row_from_sheet(worksheet_name, key_col, key_val):
    client = get_client()
    sheet = client.open(SHEET_NAME).worksheet(worksheet_name)
    data = sheet.get_all_records()
    for i, row in enumerate(data):
        if str(row[key_col]) == str(key_val):
            sheet.delete_rows(i + 2)
            return True
    return False

# --- הגדרות ---
def get_settings_lists():
    df, _ = get_worksheet_data("settings")
    if df.empty: return [], []
    fields = [x for x in df['fields'].tolist() if x]
    payment_terms = [x for x in df['payment_terms'].tolist() if x]
    return fields, payment_terms

def update_settings_list(column_name, new_list):
    client = get_client()
    sheet = client.open(SHEET_NAME).worksheet("settings")
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

# --- מחיקה מרובה עם אישור ---
@st.dialog("אישור מחיקה מרובה")
def confirm_bulk_delete(suppliers_to_delete):
    st.write(f"אתה עומד למחוק **{len(suppliers_to_delete)}** ספקים מהמערכת.")
    st.write("הפעולה היא בלתי הפיכה. האם להמשיך?")
    
    col1, col2 = st.columns(2)
    if col1.button("כן, מחק את המסומנים", type="primary"):
        progress_bar = st.progress(0)
        deleted_count = 0
        
        for i, supplier_name in enumerate(suppliers_to_delete):
            if delete_row_from_sheet("suppliers", "שם הספק", supplier_name):
                deleted_count += 1
            progress_bar.progress((i + 1) / len(suppliers_to_delete))
            
        if deleted_count > 0:
            st.success(f"{deleted_count} ספקים נמחקו בהצלחה!")
            time.sleep(1)
            st.rerun()
        else:
            st.error("לא הצלחנו למחוק. ייתכן שהם כבר נמחקו.")
            
    if col2.button("ביטול"):
        st.rerun()

# --- תצוגת טבלה למנהל (עם צ'קבוקסים) ---
def show_admin_table_with_checkboxes(df, all_fields_list):
    col_search, col_filter = st.columns([2, 1])
    with col_search: search = st.text_input("🔍 חיפוש (מנהל)", "")
    with col_filter: selected_category = st.selectbox("📂 סינון (מנהל)", ["הכל"] + all_fields_list)

    if not df.empty:
        # לוגיקת סינון
        if selected_category != "הכל":
            df = df[df['תחום עיסוק'].astype(str).str.contains(selected_category, na=False)]
        if search:
            df = df[df['שם הספק'].astype(str).str.contains(search, case=False, na=False) | df['טלפון'].astype(str).str.contains(search, case=False, na=False)]
        
        desired_cols = ['שם הספק', 'תחום עיסוק', 'טלפון', 'אימייל', 'כתובת', 'שם איש קשר', 'תנאי תשלום', 'נוסף על ידי']
        existing_cols = [c for c in desired_cols if c in df.columns]
        df_display = df[existing_cols].copy()
        
        df_display.insert(0, "סמן למחיקה", False)

        st.write("סמן בתיבה את הספקים למחיקה:")
        
        edited_df = st.data_editor(
            df_display,
            column_config={
                "סמן למחיקה": st.column_config.CheckboxColumn(
                    "מחיקה?",
                    help="סמן כדי למחוק ספק זה",
                    default=False,
                    width="small"
                ),
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

        selected_rows = edited_df[edited_df["סמן למחיקה"] == True]
        
        if not selected_rows.empty:
            st.divider()
            st.warning(f"נבחרו {len(selected_rows)} ספקים למחיקה.")
            if st.button("🗑️ לחץ כאן למחיקת הספקים המסומנים", type="primary"):
                confirm_bulk_delete(selected_rows["שם הספק"].tolist())

    else:
        st.info("אין נתונים.")

# --- תצוגת טבלה למשתמש רגיל ---
def show_suppliers_table(df, all_fields_list):
    col_search, col_filter = st.columns([2, 1])
    with col_search: search = st.text_input("🔍 חיפוש חופשי", "")
    with col_filter: selected_category = st.selectbox("📂 סינון", ["הכל"] + all_fields_list)

    if not df.empty:
        if selected_category != "הכל":
            df = df[df['תחום עיסוק'].astype(str).str.contains(selected_category, na=False)]
        if search:
            df = df[df['שם הספק'].astype(str).str.contains(search, case=False, na=False) | df['טלפון'].astype(str).str.contains(search, case=False, na=False)]
        
        desired_cols = ['שם הספק', 'תחום עיסוק', 'טלפון', 'אימייל', 'כתובת', 'שם איש קשר', 'תנאי תשלום', 'נוסף על ידי']
        final_cols = [c for c in desired_cols if c in df.columns]
        
        # HTML מחשב
        table_html = df[final_cols].to_html(index=False, classes='rtl-table', border=0, escape=False)
        
        # HTML טלפון
        cards = []
        for _, row in df.iterrows():
            card = f"""
            <div class="mobile-card">
                <details>
                    <summary><span>{row['שם הספק']} | {row['תחום עיסוק']}</span></summary>
                    <div class="card-content">
                        <div><strong>📞:</strong> <a href="tel:{row['טלפון']}">{row['טלפון']}</a></div>
                        <div><strong>✉️:</strong> <a href="mailto:{row.get('אימייל','')}">{row.get('אימייל','')}</a></div>
                        <div><strong>📍:</strong> {row['כתובת']}</div>
                        <div><strong>👤:</strong> {row.get('שם איש קשר','')}</div>
                        <div><strong>💳:</strong> {row.get('תנאי תשלום','')}</div>
                        <div style="font-size: 0.8em; color: #888; margin-top:5px;">נוסף ע"י: {row.get('נוסף על ידי','')}</div>
                    </div>
                </details>
            </div>"""
            cards.append(card)
        
        st.markdown(f"""<div class="desktop-view">{table_html}</div><div class="mobile-view">{"".join(cards)}</div>""", unsafe_allow_html=True)
    else:
        st.info("אין נתונים להצגה.")

# --- דף כניסה (מרכוז) ---
def login_page():
    # יצירת עמודות כדי למרכז את הטופס (1/3 רוחב משמאל, 1/3 באמצע, 1/3 מימין)
    # משתמשים בעמודות רק כדי למרכז כי כל העמוד הוא wide
    _, col_centered, _ = st.columns([1, 1.5, 1])
    
    with col_centered:
        st.title("🔐 כניסה למערכת")
        
        with st.expander("כלי למנהל: יצירת סיסמה"):
            p = st.text_input("סיסמה להצפנה")
            if st.button("הצפן"): st.code(hash_password(p))

        t1, t2 = st.tabs(["התחברות", "הרשמה"])
        with t1:
            with st.form("login_form"):
                user = st.text_input("אימייל").lower().strip()
                pw = st.text_input("סיסמה", type="password")
                st.checkbox("זכור אותי")
                if st.form_submit_button("התחבר"):
                    df_users, _ = get_worksheet_data("users")
                    if not df_users.empty:
                        df_users['username'] = df_users['username'].astype(str).str.lower().str.strip()
                        rec = df_users[df_users['username'] == user]
                        if not rec.empty and check_password(pw, rec.iloc[0]['password']):
                            st.session_state['logged_in'] = True
                            st.session_state['username'] = user
                            st.session_state['name'] = rec.iloc[0]['name']
                            st.session_state['role'] = rec.iloc[0]['role']
                            update_active_user(user)
                            st.success("מתחבר...")
                            time.sleep(0.5)
                            st.rerun()
                        else: st.error("פרטים שגויים")
                    else: st.error("שגיאה")

        with t2:
            with st.form("signup_form"):
                new_email = st.text_input("אימייל").lower().strip()
                new_pass = st.text_input("סיסמה", type="password")
                fname = st.text_input("שם מלא")
                if st.form_submit_button("הירשם"):
                    if not is_valid_email(new_email): st.error("אימייל לא תקין")
                    else:
                        df_u, _ = get_worksheet_data("users")
                        df_p, _ = get_worksheet_data("pending_users")
                        exists = False
                        if not df_u.empty and new_email in df_u['username'].astype(str).str.lower().str.strip().values: exists = True
                        if not df_p.empty and new_email in df_p['username'].astype(str).str.lower().str.strip().values: exists = True
                        if exists: st.error("קיים משתמש כזה")
                        else:
                            add_row_to_sheet("pending_users", [new_email, hash_password(new_pass), fname, str(datetime.now())])
                            st.success("בקשה נשלחה")

# --- ראשי ---
def main_app():
    user_role = st.session_state.get('role', 'user')
    user_name = st.session_state.get('name', 'User')
    current_user_email = st.session_state.get('username', '')
    update_active_user(current_user_email)
    
    fields_list, payment_list = get_settings_lists()
    df_suppliers, _ = get_worksheet_data("suppliers")

    c1, c2, c3 = st.columns([6, 2, 1])
    c1.title(f"שלום, {user_name}")
    if c2.button("🔄 רענן"):
        st.cache_data.clear()
        st.rerun()
    if c3.button("יציאה"):
        st.session_state['logged_in'] = False
        st.rerun()

    # הודעות דחייה
    with st.expander("📬 ההגשות שלי"):
        df_rejected, _ = get_worksheet_data("rejected_suppliers")
        my_rejections = pd.DataFrame() 
        if not df_rejected.empty:
            mask = df_rejected['נוסף על ידי'].astype(str).str.contains(user_name, na=False) | df_rejected['נוסף על ידי'].astype(str).str.contains(current_user_email, na=False)
            my_rejections = df_rejected[mask]
        
        if not my_rejections.empty:
            st.error(f"יש לך {len(my_rejections)} ספקים שנדחו.")
            st.dataframe(my_rejections[['שם הספק', 'תאריך דחייה']], use_container_width=True)
        else:
            st.info("אין הודעות דחייה.")

    st.markdown("---")

    if user_role == 'admin':
        df_pend_users, _ = get_worksheet_data("pending_users")
        c_users = len(df_pend_users) if not df_pend_users.empty else 0
        df_pend_supp, _ = get_worksheet_data("pending_suppliers")
        c_supp = len(df_pend_supp) if not df_pend_supp.empty else 0

        tabs = st.tabs(["📋 רשימת ספקים", f"⏳ אישור ספקים ({c_supp})", f"👥 אישור משתמשים ({c_users})", "➕ הוספה", "⚙️ הגדרות", "📥 יבוא"])
        
        # 1. רשימת ספקים (ממשק חדש עם צ'קבוקסים)
        with tabs[0]:
            show_admin_table_with_checkboxes(df_suppliers, fields_list)
        
        # 2. אישור ספקים
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

        # 3. אישור משתמשים
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

        # 4. הוספה
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
                    if s_name and s_fields and s_phone and s_email and s_addr:
                        if not is_valid_email(s_email): st.error("אימייל שגוי")
                        else:
                            dup, msg = check_duplicate_supplier(df_suppliers, s_name, s_phone, s_email)
                            if dup: st.error(msg)
                            else:
                                add_row_to_sheet("suppliers", [s_name, ", ".join(s_fields), s_phone, s_addr, s_pay, s_email, s_contact, user_name])
                                st.success("נוסף!")
                                time.sleep(1)
                                st.rerun()
                    else: st.error("חסרים פרטים")
        
        # 5. הגדרות
        with tabs[4]:
            st.subheader("ניהול רשימות")
            c_fields, c_terms = st.columns(2)
            with c_fields:
                st.write("**תחומי עיסוק**")
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
                st.write("**תנאי תשלום**")
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

        # 6. יבוא
        with tabs[5]:
            up = st.file_uploader("Excel", type="xlsx")
            if up and st.button("טען"):
                try:
                    d = pd.read_excel(up).astype(str)
                    cl = get_client()
                    sh = cl.open(SHEET_NAME).worksheet("suppliers")
                    sh.append_rows(d.values.tolist())
                    st.success("נטען")
                except: st.error("שגיאה")

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
                    if s_name and s_fields and s_phone and s_email and s_addr:
                        if not is_valid_email(s_email): st.error("אימייל שגוי")
                        else:
                            dup, msg = check_duplicate_supplier(df_suppliers, s_name, s_phone, s_email)
                            if dup: st.error(msg)
                            else:
                                add_row_to_sheet("pending_suppliers", [s_name, ", ".join(s_fields), s_phone, s_addr, s_pay, s_email, s_contact, user_name, str(datetime.now())])
                                st.success("נשלח!")
                    else: st.error("חסרים פרטים")

    count_online, names_online = get_online_users_count_and_names()
    st.markdown(f"""<div class="online-counter">🟢 מחוברים: {count_online}</div>""", unsafe_allow_html=True)
    if user_role == 'admin':
        with st.expander("👀 מי מחובר"): st.write(", ".join(names_online))

set_css()
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if not st.session_state['logged_in']: login_page()
else: main_app()
