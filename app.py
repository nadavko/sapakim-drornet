import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import bcrypt

# --- הגדרות ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "ניהול ספקים"

# --- פונקציות עזר להצפנה ---
def hash_password(password):
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8')

def check_password(plain_text_password, hashed_password):
    try:
        return bcrypt.checkpw(plain_text_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except ValueError:
        return False

# --- פונקציית עיצוב (CSS) ---
def set_css():
    st.markdown("""
    <style>
        .stApp { direction: rtl; text-align: right; }
        h1, h2, h3, h4, h5, h6, p, div, span, label, .stMarkdown, .stButton, .stAlert, .stSelectbox, .stMultiSelect { text-align: right !important; }
        .stTextInput input, .stTextArea textarea, .stSelectbox, .stNumberInput input { direction: rtl; text-align: right; }
        .stRadio, .stCheckbox { direction: rtl; text-align: right; }
        .stRadio > div { flex-direction: row-reverse; justify-content: flex-end; }
        
        /* תגיות בבחירה מרובה */
        .stMultiSelect span { direction: rtl; }

        /* הגדרות מחשב */
        [data-testid="stSidebar"] { direction: rtl; text-align: right; border-left: 1px solid #ddd; }
        
        /* טבלה */
        .rtl-table { width: 100%; border-collapse: collapse; direction: rtl; margin-top: 10px; }
        .rtl-table th { background-color: #f0f2f6; text-align: right !important; padding: 10px; border-bottom: 2px solid #ddd; color: #333; font-weight: bold; }
        .rtl-table td { text-align: right !important; padding: 10px; border-bottom: 1px solid #eee; color: #333; }

        /* כרטיסיות מובייל */
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
            .block-container { padding-top: 2rem !important; padding-left: 1rem !important; padding-right: 1rem !important; }
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

# --- פונקציות לניהול הגדרות (רשימות) ---
def get_settings_lists():
    """טוען את רשימות התחומים ותנאי התשלום מהלשונית settings"""
    df, _ = get_worksheet_data("settings")
    if df.empty:
        return [], []
    
    # סינון ערכים ריקים וניקוי
    fields = [x for x in df['fields'].tolist() if x]
    payment_terms = [x for x in df['payment_terms'].tolist() if x]
    return fields, payment_terms

def update_settings_list(column_name, new_list):
    """מעדכן את העמודה המלאה בגיליון ההגדרות"""
    client = get_client()
    sheet = client.open(SHEET_NAME).worksheet("settings")
    
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    
    other_col = 'payment_terms' if column_name == 'fields' else 'fields'
    other_list = [x for x in df[other_col].tolist() if x] if not df.empty and other_col in df.columns else []
    
    # איזון אורכים
    max_len = max(len(new_list), len(other_list))
    new_list += [''] * (max_len - len(new_list))
    other_list += [''] * (max_len - len(other_list))
    
    new_df = pd.DataFrame({
        column_name: new_list,
        other_col: other_list
    })
    
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
            # --- התיקון נמצא כאן: delete_rows במקום delete_row ---
            sheet.delete_rows(i + 2)
            return True
    return False

# --- תצוגת טבלה ---
def show_suppliers_table(df):
    st.subheader("רשימת ספקים")
    search = st.text_input("חיפוש חופשי...", "")
    
    if not df.empty:
        if search:
            df = df[
                df['שם הספק'].astype(str).str.contains(search, case=False, na=False) |
                df['תחום עיסוק'].astype(str).str.contains(search, case=False, na=False)
            ]
        
        # HTML מחשב
        table_html = df.to_html(index=False, classes='rtl-table', border=0, escape=False)
        
        # HTML טלפון
        cards = []
        for _, row in df.iterrows():
            # טיפול בערכים ריקים שאולי יגרמו לשגיאה
            contact_name = row.get('שם איש קשר', '')
            email = row.get('אימייל', '')
            
            card = f"""
            <div class="mobile-card">
                <details>
                    <summary><span>{row['שם הספק']} | {row['תחום עיסוק']}</span></summary>
                    <div class="card-content">
                        <div><strong>איש קשר:</strong> {contact_name}</div>
                        <div><strong>טלפון:</strong> <a href="tel:{row['טלפון']}">{row['טלפון']}</a></div>
                        <div><strong>אימייל:</strong> <a href="mailto:{email}">{email}</a></div>
                        <div><strong>כתובת:</strong> {row['כתובת']}</div>
                        <div><strong>תנאי תשלום:</strong> {row['תנאי תשלום']}</div>
                    </div>
                </details>
            </div>"""
            cards.append(card)
        all_cards = "".join(cards)

        final_html = f"""<div class="desktop-view">{table_html}</div><div class="mobile-view">{all_cards}</div>"""
        st.markdown(final_html.replace('\n', ' '), unsafe_allow_html=True)
    else:
        st.info("אין נתונים להצגה")

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
    
    # טעינת רשימות מהגדרות
    fields_list, payment_list = get_settings_lists()

    st.sidebar.markdown(f"### שלום {user_name}")
    if st.sidebar.button("יציאה מהמערכת"):
        st.session_state['logged_in'] = False
        st.rerun()
        
    st.sidebar.markdown("---")
    
    # --- הוספת ספק (עם שדות חדשים ווולידציה) ---
    st.sidebar.subheader("➕ הוספת ספק")
    with st.sidebar.form("add_supplier_sidebar"):
        s_name = st.text_input("שם הספק *")
        s_fields = st.multiselect("תחומי עיסוק *", fields_list)
        s_phone = st.text_input("טלפון *")
        s_email = st.text_input("אימייל *")
        s_contact = st.text_input("שם איש קשר (אופציונלי)")
        s_addr = st.text_input("כתובת *")
        s_pay = st.selectbox("תנאי תשלום *", payment_list)
        
        if st.form_submit_button("הוסף"):
            if s_name and s_fields and s_phone and s_email and s_addr and s_pay:
                fields_str = ", ".join(s_fields)
                row_data = [s_name, fields_str, s_phone, s_addr, s_pay, s_email, s_contact, user_name]
                
                if user_role == 'admin':
                    add_row_to_sheet("suppliers", row_data)
                    st.sidebar.success("נוסף בהצלחה!")
                else:
                    row_data.append(str(datetime.now()))
                    add_row_to_sheet("pending_suppliers", row_data)
                    st.sidebar.success("נשלח לאישור מנהל")
            else:
                st.sidebar.error("נא למלא את כל שדות החובה (*)")

    # --- כלי ניהול (Admin Only) ---
    if user_role == 'admin':
        st.sidebar.markdown("---")
        st.sidebar.subheader("🛠️ ניהול מנהל")
        admin_mode = st.sidebar.radio("בחר כלי:", ["אישור משתמשים", "אישור ספקים", "ניהול רשימות", "מחיקת ספק", "יבוא אקסל"])
        
        if admin_mode == "אישור משתמשים":
            df_pending, _ = get_worksheet_data("pending_users")
            if not df_pending.empty:
                for idx, row in df_pending.iterrows():
                    st.sidebar.text(f"{row['name']}")
                    if st.sidebar.button("אשר", key=f"u_ok_{idx}"):
                        add_row_to_sheet("users", [row['username'], row['password'], 'user', row['name']])
                        delete_row_from_sheet("pending_users", "username", row['username'])
                        st.rerun()
            else:
                st.sidebar.text("אין בקשות")

        elif admin_mode == "אישור ספקים":
            df_pend_supp, _ = get_worksheet_data("pending_suppliers")
            if not df_pend_supp.empty:
                for idx, row in df_pend_supp.iterrows():
                    with st.sidebar.expander(f"{row['שם הספק']}"):
                        st.write(f"תחום: {row['תחום עיסוק']}")
                        st.write(f"איש קשר: {row.get('שם איש קשר', '')}")
                        if st.button("אשר", key=f"s_ok_{idx}"):
                            add_row_to_sheet("suppliers", [
                                row['שם הספק'], row['תחום עיסוק'], row['טלפון'], 
                                row['כתובת'], row['תנאי תשלום'], row.get('אימייל', ''), 
                                row.get('שם איש קשר', ''), row['נוסף על ידי']
                            ])
                            delete_row_from_sheet("pending_suppliers", "שם הספק", row['שם הספק'])
                            st.rerun()
                        if st.button("דחה", key=f"s_no_{idx}"):
                            delete_row_from_sheet("pending_suppliers", "שם הספק", row['שם הספק'])
                            st.rerun()
            else:
                st.sidebar.text("אין ספקים לאישור")
        
        elif admin_mode == "ניהול רשימות":
            st.sidebar.write("**עריכת רשימות בחירה**")
            with st.sidebar.expander("תחומי עיסוק"):
                new_field = st.text_input("הוסף תחום חדש")
                if st.button("הוסף תחום"):
                    if new_field and new_field not in fields_list:
                        fields_list.append(new_field)
                        update_settings_list("fields", fields_list)
                        st.rerun()
                field_to_remove = st.selectbox("מחק תחום קיים", [""] + fields_list)
                if st.button("מחק תחום"):
                    if field_to_remove:
                        fields_list.remove(field_to_remove)
                        update_settings_list("fields", fields_list)
                        st.rerun()

            with st.sidebar.expander("תנאי תשלום"):
                new_term = st.text_input("הוסף תנאי תשלום")
                if st.button("הוסף תנאי"):
                    if new_term and new_term not in payment_list:
                        payment_list.append(new_term)
                        update_settings_list("payment_terms", payment_list)
                        st.rerun()
                term_to_remove = st.selectbox("מחק תנאי קיים", [""] + payment_list)
                if st.button("מחק תנאי"):
                    if term_to_remove:
                        payment_list.remove(term_to_remove)
                        update_settings_list("payment_terms", payment_list)
                        st.rerun()

        elif admin_mode == "יבוא אקסל":
             uploaded = st.sidebar.file_uploader("קובץ Excel")
             if uploaded and st.sidebar.button("טען"):
                 try:
                     d = pd.read_excel(uploaded).astype(str)
                     client = get_client()
                     sheet = client.open(SHEET_NAME).worksheet("suppliers")
                     sheet.append_rows(d.values.tolist())
                     st.sidebar.success("נטען!")
                 except Exception as e:
                     st.sidebar.error("שגיאה בקובץ")

        elif admin_mode == "מחיקת ספק":
             del_name = st.sidebar.text_input("הכנס שם ספק מדויק למחיקה")
             if st.sidebar.button("מחק ספק"):
                 if delete_row_from_sheet("suppliers", "שם הספק", del_name):
                     st.sidebar.success("נמחק")
                     time.sleep(1)
                     st.rerun()
                 else:
                     st.sidebar.error("לא נמצא")

    # --- תצוגה ראשית ---
    st.title("📦 ניהול ספקים")
    
    df_suppliers, _ = get_worksheet_data("suppliers")
    show_suppliers_table(df_suppliers)

# --- הרצה ---
set_css()
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    login_page()
else:
    main_app()
