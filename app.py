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

# --- עיצוב לימין (RTL) - הגרסה המלאה והמתוקנת ---
def set_rtl_css():
    st.markdown("""
    <style>
        /* 1. הופכים את הכיוון הראשי של האפליקציה (כדי שהתפריט יהיה בימין) */
        .stApp {
            direction: rtl;
            text-align: right;
        }

        /* 2. תיקון קריטי לנייד: הסתרת "ידית הגרירה" שיוצרת את הקו האפור באמצע המסך */
        [data-testid="stSidebarResizeHandle"] {
            display: none;
        }

        /* 3. יישור טקסטים גורף לימין (כולל מסך הכניסה) */
        h1, h2, h3, h4, h5, h6, p, div, span, label, .stMarkdown, .stButton, .stAlert, .stSelectbox {
            text-align: right !important;
        }

        /* 4. סידור הלשוניות (Tabs) במסך הכניסה שיהיו מימין לשמאל */
        .stTabs [data-baseweb="tab-list"] {
            flex-direction: row-reverse;
            justify-content: flex-end;
        }
        
        /* 5. יישור שדות קלט (שלא יכתבו הפוך) */
        .stTextInput input, .stTextArea textarea, .stSelectbox, .stNumberInput input {
            direction: rtl;
            text-align: right;
        }
        
        /* 6. התאמת התפריט הצידי */
        [data-testid="stSidebar"] {
            direction: rtl;
            text-align: right;
            border-right: none; /* ביטול קו בצד ימין */
            border-left: 1px solid #f0f2f6; /* העברת הקו לצד שמאל */
        }
        
        /* 7. כפתורי רדיו וצ'קבוקס */
        .stRadio, .stCheckbox {
            direction: rtl;
            text-align: right;
        }
        .stRadio > div {
            flex-direction: row-reverse;
            justify-content: flex-end;
        }
        
        /* הסתרת סרגל כלים של אלמנטים */
        [data-testid="stElementToolbar"] {
            display: none;
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
            sheet.delete_row(i + 2)
            return True
    return False

# --- תצוגת טבלה (רספונסיבית ונקייה) ---
def show_suppliers_table(df):
    st.subheader("רשימת ספקים")
    search = st.text_input("חיפוש חופשי...", "")
    
    if not df.empty:
        if search:
            df = df[
                df['שם הספק'].astype(str).str.contains(search, case=False, na=False) |
                df['תחום עיסוק'].astype(str).str.contains(search, case=False, na=False)
            ]
        
        # 1. עיצוב CSS פנימי לטבלה
        st.markdown("""
        <style>
            /* מחשב */
            .rtl-table { width: 100%; border-collapse: collapse; direction: rtl; margin-top: 10px; }
            .rtl-table th { background-color: #f0f2f6; text-align: right !important; padding: 10px; border-bottom: 2px solid #ddd; color: #333; font-weight: bold; }
            .rtl-table td { text-align: right !important; padding: 10px; border-bottom: 1px solid #eee; color: #333; }
            
            /* נייד */
            .mobile-card { background-color: white; border: 1px solid #ddd; border-radius: 8px; margin-bottom: 12px; padding: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); direction: rtl; text-align: right !important; }
            .mobile-card summary { font-weight: bold; cursor: pointer; color: #000; list-style: none; outline: none; display: flex; justify-content: space-between; align-items: center; }
            .mobile-card summary::after { content: "+"; font-size: 1.2em; margin-right: 10px; }
            .mobile-card details[open] summary::after { content: "-"; }
            .mobile-card .card-content { margin-top: 10px; padding-top: 10px; border-top: 1px solid #eee; font-size: 0.95em; color: #333; }
            .mobile-card a { color: #0068c9; text-decoration: none; font-weight: bold; }

            /* תצוגה */
            .desktop-view { display: block; }
            .mobile-view { display: none; }
            @media only screen and (max-width: 768px) {
                .desktop-view { display: none; }
                .mobile-view { display: block; }
            }
        </style>
        """, unsafe_allow_html=True)

        # 2. HTML מחשב
        table_html = df.to_html(index=False, classes='rtl-table', border=0, escape=False)
        
        # 3. HTML נייד (בנייה שטוחה)
        cards = []
        for _, row in df.iterrows():
            card = f"""<div class="mobile-card"><details><summary><span>{row['שם הספק']} | {row['תחום עיסוק']}</span></summary><div class="card-content"><div><strong>טלפון:</strong> <a href="tel:{row['טלפון']}">{row['טלפון']}</a></div><div><strong>כתובת:</strong> {row['כתובת']}</div><div><strong>תנאי תשלום:</strong> {row['תנאי תשלום']}</div></div></details></div>"""
            cards.append(card)
        all_cards = "".join(cards)

        # 4. הדפסה (עם ניקוי רווחים למניעת שגיאות תצוגה)
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
            st.info("העתק את הקוד והדבק ב-Google Sheets")

    tab1, tab2 = st.tabs(["התחברות", "הרשמה למערכת"])

    with tab1:
        with st.form("login_form"):
            user = st.text_input("אימייל")
            pw = st.text_input("סיסמה", type="password")
            submitted = st.form_submit_button("התחבר")
            
            if submitted:
                df_users, _ = get_worksheet_data("users")
                if not df_users.empty:
                    user_record = df_users[df_users['username'] == user]
                    if not user_record.empty:
                        stored_hash = user_record.iloc[0]['password']
                        if check_password(pw, stored_hash):
                            st.session_state['logged_in'] = True
                            st.session_state['username'] = user
                            st.session_state['name'] = user_record.iloc[0]['name']
                            st.session_state['role'] = user_record.iloc[0]['role']
                            st.success(f"ברוך הבא, {st.session_state['name']}!")
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
            new_email = st.text_input("אימייל")
            new_pass = st.text_input("סיסמה", type="password")
            full_name = st.text_input("שם מלא")
            if st.form_submit_button("הירשם"):
                df_users, _ = get_worksheet_data("users")
                if not df_users.empty and new_email in df_users['username'].values:
                    st.warning("משתמש קיים")
                else:
                    hashed_pw = hash_password(new_pass)
                    add_row_to_sheet("pending_users", [new_email, hashed_pw, full_name, str(datetime.now())])
                    st.success("הבקשה נשלחה לאישור מנהל.")

# --- אפליקציה ראשית ---
def main_app():
    user_role = st.session_state.get('role', 'user')
    user_name = st.session_state.get('name', 'User')
    
    # תפריט צד
    st.sidebar.markdown(f"**שלום {user_name}**")
    if st.sidebar.button("יציאה"):
        st.session_state['logged_in'] = False
        st.rerun()

    st.title("📦 ניהול ספקים")
    df_suppliers, _ = get_worksheet_data("suppliers")

    if user_role == 'admin':
        st.sidebar.header("ניהול")
        admin_action = st.sidebar.radio("פעולות:", ["צפייה בספקים", "אישור ספקים", "אישור משתמשים", "הוספה/יבוא", "מחיקת ספק"])
        
        if admin_action == "צפייה בספקים":
            show_suppliers_table(df_suppliers)

        elif admin_action == "אישור משתמשים":
            st.subheader("אישור משתמשים")
            df_pending, _ = get_worksheet_data("pending_users")
            if not df_pending.empty:
                for idx, row in df_pending.iterrows():
                    st.info(f"בקשה: {row['name']} ({row['username']})")
                    c1, c2 = st.columns([1,4])
                    if c1.button("אשר", key=f"ok_{idx}"):
                        add_row_to_sheet("users", [row['username'], row['password'], 'user', row['name']])
                        delete_row_from_sheet("pending_users", "username", row['username'])
                        st.success("אושר!")
                        time.sleep(0.5)
                        st.rerun()
                    if c2.button("דחה", key=f"no_{idx}"):
                        delete_row_from_sheet("pending_users", "username", row['username'])
                        st.rerun()
            else:
                st.write("אין בקשות.")

        elif admin_action == "אישור ספקים":
            st.subheader("אישור ספקים")
            df_pending_supp, _ = get_worksheet_data("pending_suppliers")
            if not df_pending_supp.empty:
                for idx, row in df_pending_supp.iterrows():
                    with st.expander(f"{row['שם הספק']} (מאת {row['נוסף על ידי']})"):
                        st.write(f"{row['תחום עיסוק']} | {row['טלפון']}")
                        c1, c2 = st.columns(2)
                        if c1.button("אשר", key=f"app_s_{idx}"):
                            add_row_to_sheet("suppliers", [row['שם הספק'], row['תחום עיסוק'], row['טלפון'], row['כתובת'], row['תנאי תשלום'], row['נוסף על ידי']])
                            delete_row_from_sheet("pending_suppliers", "שם הספק", row['שם הספק'])
                            st.success("אושר!")
                            st.rerun()
                        if c2.button("מחק", key=f"rej_s_{idx}"):
                            delete_row_from_sheet("pending_suppliers", "שם הספק", row['שם הספק'])
                            st.rerun()
            else:
                st.write("אין ספקים בהמתנה.")

        elif admin_action == "הוספה/יבוא":
            st.subheader("הוספת ספק (מנהל)")
            type_add = st.radio("סוג", ["ידני", "אקסל"], horizontal=True)
            if type_add == "ידני":
                with st.form("admin_add"):
                    name = st.text_input("שם")
                    field = st.text_input("תחום")
                    phone = st.text_input("טלפון")
                    addr = st.text_input("כתובת")
                    pay = st.selectbox("תשלום", ["שוטף+30", "שוטף+60", "שוטף+90", "מזומן", "אשראי"])
                    if st.form_submit_button("הוסף"):
                        add_row_to_sheet("suppliers", [name, field, phone, addr, pay, user_name])
                        st.success("נוסף!")
            else:
                uploaded = st.file_uploader("קובץ אקסל")
                if uploaded and st.button("טען"):
                    d = pd.read_excel(uploaded).astype(str)
                    client = get_client()
                    sheet = client.open(SHEET_NAME).worksheet("suppliers")
                    sheet.append_rows(d.values.tolist())
                    st.success("נטען!")

        elif admin_action == "מחיקת ספק":
            supp_del = st.selectbox("בחר למחיקה", df_suppliers['שם הספק'].unique() if not df_suppliers.empty else [])
            if st.button("מחק"):
                delete_row_from_sheet("suppliers", "שם הספק", supp_del)
                st.success("נמחק")
                time.sleep(0.5)
                st.rerun()

    else:
        # ממשק משתמש רגיל
        tab_view, tab_add = st.tabs(["צפייה", "הוספה"])
        with tab_view:
            show_suppliers_table(df_suppliers)
        with tab_add:
            st.subheader("הצעת ספק חדש")
            with st.form("user_add"):
                name = st.text_input("שם")
                field = st.text_input("תחום")
                phone = st.text_input("טלפון")
                addr = st.text_input("כתובת")
                pay = st.selectbox("תשלום", ["שוטף+30", "שוטף+60", "שוטף+90", "מזומן", "אשראי"])
                if st.form_submit_button("שלח לאישור"):
                    add_row_to_sheet("pending_suppliers", [name, field, phone, addr, pay, user_name, str(datetime.now())])
                    st.success("נשלח לאישור.")

# --- הרצה ---
set_rtl_css()
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    login_page()
else:
    main_app()
