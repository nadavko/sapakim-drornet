import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import bcrypt
import re

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

# --- CSS ---
def set_css():
    st.markdown("""
    <style>
        .stApp { direction: rtl; text-align: right; }
        h1, h2, h3, h4, h5, h6, p, div, span, label, .stMarkdown, .stButton, .stAlert, .stSelectbox, .stMultiSelect { text-align: right !important; }
        .stTextInput input, .stTextArea textarea, .stSelectbox, .stNumberInput input { direction: rtl; text-align: right; }
        .stTabs [data-baseweb="tab-list"] { flex-direction: row-reverse; justify-content: flex-end; }
        .stRadio, .stCheckbox { direction: rtl; text-align: right; }
        .stRadio > div { flex-direction: row-reverse; justify-content: flex-end; }
        .stMultiSelect span { direction: rtl; }
        [data-testid="stSidebar"] { direction: rtl; text-align: right; border-left: 1px solid #ddd; }
        
        /* טבלה */
        .rtl-table { width: 100%; border-collapse: collapse; direction: rtl; margin-top: 10px; }
        .rtl-table th { background-color: #f0f2f6; text-align: right !important; padding: 10px; border-bottom: 2px solid #ddd; color: #333; font-weight: bold; white-space: nowrap; }
        .rtl-table td { text-align: right !important; padding: 10px; border-bottom: 1px solid #eee; color: #333; }

        /* מובייל */
        .mobile-card { background-color: white; border: 1px solid #ddd; border-radius: 8px; margin-bottom: 12px; padding: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); direction: rtl; text-align: right !important; }
        .mobile-card summary { font-weight: bold; cursor: pointer; color: #000; list-style: none; outline: none; display: flex; justify-content: space-between; align-items: center; }
        .mobile-card summary::after { content: "+"; font-size: 1.2em; margin-right: 10px; color: #666; }
        .mobile-card details[open] summary::after { content: "-"; }
        .mobile-card .card-content { margin-top: 10px; padding-top: 10px; border-top: 1px solid #eee; font-size: 0.95em; color: #333; }
        .mobile-card a { color: #0068c9; text-decoration: none; font-weight: bold; }

        [data-testid="stElementToolbar"] { display: none; }
        .desktop-view { display: block; }
        .mobile-view { display: none; }

        @media only screen and (max-width: 768px) {
            .desktop-view { display: none; }
            .mobile-view { display: block; }
            [data-testid="stSidebar"] { display: none !important; }
            [data-testid="stSidebarCollapsedControl"] { display: none !important; }
            [data-testid="stSidebarResizeHandle"] { display: none !important; }
            .block-container { padding-top: 1rem !important; }
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

# --- ניהול רשימות ---
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

# --- תצוגת טבלה ---
def show_suppliers_table(df, all_fields_list):
    # אזור סינון וחיפוש
    col_search, col_filter = st.columns([2, 1])
    
    with col_search:
        search = st.text_input("🔍 חיפוש חופשי (שם, טלפון...)", "")
    
    with col_filter:
        filter_options = ["הכל"] + all_fields_list
        selected_category = st.selectbox("📂 סינון לפי תחום עיסוק", filter_options)

    if not df.empty:
        # סינון
        if selected_category != "הכל":
            df = df[df['תחום עיסוק'].astype(str).str.contains(selected_category, na=False)]

        if search:
            df = df[
                df['שם הספק'].astype(str).str.contains(search, case=False, na=False) |
                df['טלפון'].astype(str).str.contains(search, case=False, na=False)
            ]
        
        # --- תיקון סדר העמודות (תנאי תשלום לפני נוסף ע"י) ---
        desired_order = ['שם הספק', 'תחום עיסוק', 'טלפון', 'אימייל', 'כתובת', 'שם איש קשר', 'תנאי תשלום', 'נוסף על ידי']
        
        existing_cols = [c for c in desired_order if c in df.columns]
        df_display = df[existing_cols]

        # בניית HTML למחשב
        table_html = df_display.to_html(index=False, classes='rtl-table', border=0, escape=False)
        
        # בניית HTML לטלפון
        cards = []
        for _, row in df.iterrows():
            contact_name = row.get('שם איש קשר', '')
            email = row.get('אימייל', '')
            added_by = row.get('נוסף על ידי', '')
            payment_terms = row.get('תנאי תשלום', '')
            
            card = f"""
            <div class="mobile-card">
                <details>
                    <summary><span>{row['שם הספק']} | {row['תחום עיסוק']}</span></summary>
                    <div class="card-content">
                        <div><strong>📞 טלפון:</strong> <a href="tel:{row['טלפון']}">{row['טלפון']}</a></div>
                        <div><strong>✉️ אימייל:</strong> <a href="mailto:{email}">{email}</a></div>
                        <div><strong>📍 כתובת:</strong> {row['כתובת']}</div>
                        <div><strong>👤 איש קשר:</strong> {contact_name}</div>
                        <div><strong>💳 תנאי תשלום:</strong> {payment_terms}</div>
                        <div style="font-size: 0.8em; color: #888; margin-top:5px;">נוסף ע"י: {added_by}</div>
                    </div>
                </details>
            </div>"""
            cards.append(card)
        all_cards = "".join(cards)

        final_html = f"""<div class="desktop-view">{table_html}</div><div class="mobile-view">{all_cards}</div>"""
        st.markdown(final_html.replace('\n', ' '), unsafe_allow_html=True)
    else:
        st.info("אין נתונים להצגה (נסה לשנות את הסינון).")

# --- דף כניסה ---
def login_page():
    st.title("🔐 כניסה למערכת")
    with st.expander("כלי למנהל: יצירת Hash לסיסמה"):
        pass_to_hash = st.text_input("הכנס סיסמה להצפנה")
        if st.button("הצפן"):
            st.code(hash_password(pass_to_hash))

    tab1, tab2 = st.tabs(["התחברות", "הרשמה למערכת"])

    with tab1:
        with st.form("login_form"):
            user = st.text_input("אימייל").lower().strip()
            pw = st.text_input("סיסמה", type="password")
            if st.form_submit_button("התחבר"):
                df_users, _ = get_worksheet_data("users")
                if not df_users.empty:
                    df_users['username'] = df_users['username'].astype(str).str.lower().str.strip()
                    user_record = df_users[df_users['username'] == user]
                    if not user_record.empty:
                        if check_password(pw, user_record.iloc[0]['password']):
                            st.session_state['logged_in'] = True
                            st.session_state['username'] = user
                            st.session_state['name'] = user_record.iloc[0]['name']
                            st.session_state['role'] = user_record.iloc[0]['role']
                            st.success("ברוך הבא!")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error("סיסמה שגויה")
                    else:
                        st.error("משתמש לא נמצא")
                else:
                    st.error("שגיאת מערכת")

    with tab2:
        st.subheader("בקשת הצטרפות")
        with st.form("signup_form"):
            new_email = st.text_input("אימייל").lower().strip()
            new_pass = st.text_input("סיסמה", type="password")
            full_name = st.text_input("שם מלא")
            if st.form_submit_button("הירשם"):
                if not is_valid_email(new_email):
                    st.error("כתובת אימייל לא תקינה")
                else:
                    df_users, _ = get_worksheet_data("users")
                    existing = []
                    if not df_users.empty:
                         existing = df_users['username'].astype(str).str.lower().str.strip().values
                    if new_email in existing:
                        st.warning("קיים במערכת")
                    else:
                        hashed_pw = hash_password(new_pass)
                        add_row_to_sheet("pending_users", [new_email, hashed_pw, full_name, str(datetime.now())])
                        st.success("הבקשה נשלחה לאישור.")

# --- אפליקציה ראשית ---
def main_app():
    user_role = st.session_state.get('role', 'user')
    user_name = st.session_state.get('name', 'User')
    
    # טעינת נתונים
    fields_list, payment_list = get_settings_lists()
    df_suppliers, _ = get_worksheet_data("suppliers")

    col_header, col_exit = st.columns([4, 1])
    with col_header:
        st.title(f"שלום, {user_name}")
    with col_exit:
        if st.button("יציאה", key="logout_btn"):
            st.session_state['logged_in'] = False
            st.rerun()

    st.markdown("---")

    # --- מנהל ---
    if user_role == 'admin':
        tabs = st.tabs(["📋 רשימת ספקים", "⏳ אישור ספקים", "👥 אישור משתמשים", "➕ הוספת ספק", "⚙️ הגדרות", "📥 יבוא אקסל", "🗑️ מחיקה"])
        
        with tabs[0]:
            show_suppliers_table(df_suppliers, fields_list)

        with tabs[1]:
            st.subheader("ספקים שממתינים לאישור")
            df_pend_supp, _ = get_worksheet_data("pending_suppliers")
            if not df_pend_supp.empty:
                for idx, row in df_pend_supp.iterrows():
                    with st.expander(f"{row['שם הספק']} (נוסף ע\"י {row.get('נוסף על ידי', 'Unknown')})"):
                        st.write(f"תחום: {row['תחום עיסוק']}")
                        st.write(f"איש קשר: {row.get('שם איש קשר', '')} | טלפון: {row['טלפון']}")
                        
                        is_dup, err_msg = check_duplicate_supplier(df_suppliers, row['שם הספק'], row['טלפון'], row.get('אימייל', ''))
                        if is_dup:
                            st.warning(f"שים לב: {err_msg}")

                        c1, c2 = st.columns(2)
                        if c1.button("אשר ספק", key=f"adm_app_{idx}"):
                            add_row_to_sheet("suppliers", [
                                row['שם הספק'], row['תחום עיסוק'], row['טלפון'], 
                                row['כתובת'], row['תנאי תשלום'], row.get('אימייל', ''), 
                                row.get('שם איש קשר', ''), row['נוסף על ידי']
                            ])
                            delete_row_from_sheet("pending_suppliers", "שם הספק", row['שם הספק'])
                            st.success("אושר!")
                            time.sleep(1)
                            st.rerun()
                        if c2.button("דחה", key=f"adm_rej_{idx}"):
                            delete_row_from_sheet("pending_suppliers", "שם הספק", row['שם הספק'])
                            st.rerun()
            else:
                st.info("אין ספקים ממתינים לאישור.")

        with tabs[2]:
            st.subheader("משתמשים שממתינים לאישור")
            df_pending_users, _ = get_worksheet_data("pending_users")
            if not df_pending_users.empty:
                for idx, row in df_pending_users.iterrows():
                    st.info(f"בקשה מ: {row['name']} ({row['username']})")
                    c1, c2 = st.columns(2)
                    if c1.button("אשר", key=f"usr_ok_{idx}"):
                        add_row_to_sheet("users", [row['username'], row['password'], 'user', row['name']])
                        delete_row_from_sheet("pending_users", "username", row['username'])
                        st.success("משתמש אושר!")
                        time.sleep(1)
                        st.rerun()
            else:
                st.info("אין משתמשים חדשים.")

        with tabs[3]:
            st.subheader("הוספת ספק חדש")
            with st.form("admin_add_form"):
                s_name = st.text_input("שם הספק *")
                s_fields = st.multiselect("תחומי עיסוק *", fields_list)
                s_phone = st.text_input("טלפון *")
                s_email = st.text_input("אימייל *")
                s_contact = st.text_input("שם איש קשר (אופציונלי)")
                s_addr = st.text_input("כתובת *")
                s_pay = st.selectbox("תנאי תשלום *", payment_list)
                
                if st.form_submit_button("שמור ספק"):
                    if s_name and s_fields and s_phone and s_email and s_addr and s_pay:
                        if not is_valid_email(s_email):
                            st.error("❌ אימייל לא תקין")
                        else:
                            is_dup, msg = check_duplicate_supplier(df_suppliers, s_name, s_phone, s_email)
                            if is_dup:
                                st.error(f"❌ {msg}")
                            else:
                                fields_str = ", ".join(s_fields)
                                row_data = [s_name, fields_str, s_phone, s_addr, s_pay, s_email, s_contact, user_name]
                                add_row_to_sheet("suppliers", row_data)
                                st.success("✅ נוסף בהצלחה!")
                                time.sleep(1)
                                st.rerun()
                    else:
                        st.error("נא למלא את כל שדות החובה")

        with tabs[4]:
            st.subheader("ניהול רשימות בחירה")
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

        with tabs[5]:
            st.subheader("יבוא נתונים")
            uploaded = st.file_uploader("קובץ Excel", type=["xlsx"])
            if uploaded and st.button("טען קובץ"):
                try:
                    d = pd.read_excel(uploaded).astype(str)
                    client = get_client()
                    sheet = client.open(SHEET_NAME).worksheet("suppliers")
                    sheet.append_rows(d.values.tolist())
                    st.success("הנתונים נטענו!")
                except Exception as e:
                    st.error("שגיאה בטעינת הקובץ")

        with tabs[6]:
            st.subheader("מחיקת ספק")
            del_name = st.text_input("הכנס שם ספק מדויק למחיקה")
            if st.button("מחק לצמיתות"):
                if delete_row_from_sheet("suppliers", "שם הספק", del_name):
                    st.success("הספק נמחק.")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("ספק לא נמצא.")

    # --- משתמש רגיל ---
    else:
        tabs_user = st.tabs(["🔎 רשימת ספקים", "➕ הצעת ספק חדש"])
        
        with tabs_user[0]:
            show_suppliers_table(df_suppliers, fields_list)
            
        with tabs_user[1]:
            st.subheader("טופס הצעת ספק")
            with st.form("user_add_form"):
                s_name = st.text_input("שם הספק *")
                s_fields = st.multiselect("תחומי עיסוק *", fields_list)
                s_phone = st.text_input("טלפון *")
                s_email = st.text_input("אימייל *")
                s_contact = st.text_input("שם איש קשר (אופציונלי)")
                s_addr = st.text_input("כתובת *")
                s_pay = st.selectbox("תנאי תשלום *", payment_list)
                
                if st.form_submit_button("שלח לאישור"):
                    if s_name and s_fields and s_phone and s_email and s_addr and s_pay:
                        if not is_valid_email(s_email):
                            st.error("❌ אימייל לא תקין")
                        else:
                            is_dup, msg = check_duplicate_supplier(df_suppliers, s_name, s_phone, s_email)
                            if is_dup:
                                st.error(f"❌ {msg}")
                            else:
                                fields_str = ", ".join(s_fields)
                                row_data = [s_name, fields_str, s_phone, s_addr, s_pay, s_email, s_contact, user_name, str(datetime.now())]
                                add_row_to_sheet("pending_suppliers", row_data)
                                st.success("✅ הבקשה נשלחה לאישור מנהל")
                    else:
                        st.error("נא למלא את כל שדות החובה")

# --- הרצה ---
set_css()
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    login_page()
else:
    main_app()
