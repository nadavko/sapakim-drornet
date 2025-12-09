import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import bcrypt  # הספרייה החדשה להצפנה

# --- הגדרות ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "ניהול ספקים"

# --- פונקציות עזר להצפנה ---
def hash_password(password):
    """מקבל סיסמה רגילה ומחזיר סיסמה מוצפנת"""
    # המרת הסיסמה לביטים, יצירת מלח (Salt) והצפנה
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8') # המרה חזרה למחרוזת לשמירה בגיליון

def check_password(plain_text_password, hashed_password):
    """בודק אם הסיסמה שהוזנה תואמת לסיסמה המוצפנת"""
    try:
        return bcrypt.checkpw(plain_text_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except ValueError:
        return False

# --- עיצוב לימין (RTL) ---
def set_rtl_css():
    st.markdown("""
    <style>
        .stApp { direction: rtl; text-align: right; }
        h1, h2, h3, h4, h5, h6, .stMarkdown, .stButton, .stTextInput, .stSelectbox { text-align: right !important; }
        [data-testid="stSidebar"] { text-align: right; }
        .stTextInput input, .stTextArea textarea, .stSelectbox { direction: rtl; text-align: right; }
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

# --- דף התחברות והרשמה ---
def login_page():
    st.title("🔐 כניסה למערכת")
    
    # כלי עזר זמני ליצירת סיסמה מוצפנת ראשונית למנהל (מוסתר)
    with st.expander("כלי למנהל: יצירת Hash לסיסמה (לשימוש ידני ראשוני)"):
        pass_to_hash = st.text_input("הכנס סיסמה להצפנה")
        if st.button("הצפן"):
            st.code(hash_password(pass_to_hash))
            st.info("העתק את הקוד הזה והדבק אותו בעמודת password בגיליון Google Sheets בשורה של המנהל.")

    tab1, tab2 = st.tabs(["התחברות", "הרשמה למערכת"])

    with tab1:
        with st.form("login_form"):
            user = st.text_input("אימייל")
            pw = st.text_input("סיסמה", type="password")
            submitted = st.form_submit_button("התחבר")
            
            if submitted:
                df_users, _ = get_worksheet_data("users")
                if not df_users.empty:
                    # חיפוש המשתמש לפי אימייל
                    user_record = df_users[df_users['username'] == user]
                    
                    if not user_record.empty:
                        stored_hash = user_record.iloc[0]['password']
                        role = user_record.iloc[0]['role']
                        name = user_record.iloc[0]['name']
                        
                        # בדיקת הסיסמה מול ההצפנה
                        if check_password(pw, stored_hash):
                            st.session_state['logged_in'] = True
                            st.session_state['username'] = user
                            st.session_state['name'] = name
                            st.session_state['role'] = role
                            st.success(f"ברוך הבא, {name}!")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error("סיסמה שגויה")
                    else:
                        st.error("משתמש לא נמצא")
                else:
                    st.error("שגיאת מערכת: מסד הנתונים ריק")

    with tab2:
        st.subheader("בקשת הצטרפות")
        with st.form("signup_form"):
            new_email = st.text_input("אימייל")
            new_pass = st.text_input("סיסמה", type="password")
            full_name = st.text_input("שם מלא")
            signup_submit = st.form_submit_button("הירשם")
            
            if signup_submit:
                if new_email and new_pass and full_name:
                    # בדיקה אם קיים
                    df_users, _ = get_worksheet_data("users")
                    if not df_users.empty and new_email in df_users['username'].values:
                        st.warning("משתמש קיים")
                    else:
                        # --- כאן מתבצעת ההצפנה לפני השליחה להמתנה ---
                        hashed_pw = hash_password(new_pass)
                        
                        row = [new_email, hashed_pw, full_name, str(datetime.now())]
                        add_row_to_sheet("pending_users", row)
                        st.success("הבקשה נשלחה לאישור מנהל.")
                else:
                    st.error("מלא את כל השדות")

# --- האפליקציה הראשית ---
def main_app():
    user_role = st.session_state.get('role', 'user')
    user_name = st.session_state.get('name', 'User')
    
    st.sidebar.markdown(f"**שלום {user_name}**")
    if st.sidebar.button("יציאה"):
        st.session_state['logged_in'] = False
        st.rerun()

    st.title("📦 ניהול ספקים")
    df_suppliers, _ = get_worksheet_data("suppliers")

    # --- ממשק מנהל ---
    if user_role == 'admin':
        st.sidebar.header("ניהול")
        admin_action = st.sidebar.radio("פעולות:", 
            ["צפייה בספקים", "אישור ספקים", "אישור משתמשים", "הוספה/יבוא", "מחיקת ספק"])
        
        if admin_action == "אישור משתמשים":
            st.subheader("אישור משתמשים חדשים")
            df_pending, _ = get_worksheet_data("pending_users")
            if not df_pending.empty:
                for idx, row in df_pending.iterrows():
                    # מציגים רק את השם, הסיסמה כבר מוצפנת ואין טעם להציג אותה
                    st.info(f"בקשה: {row['name']} ({row['username']})")
                    c1, c2 = st.columns([1,4])
                    if c1.button("אשר", key=f"ok_{idx}"):
                        # מעבירים את הסיסמה המוצפנת כמו שהיא לטבלה הראשית
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

        # שאר הפונקציות של המנהל (ספקים, יבוא וכו') נשארות זהות לקוד הקודם...
        # (כדי לחסוך מקום לא העתקתי שוב את כל הלוגיקה של הספקים, תעתיק מהקוד הקודם את ה-elif האחרים)
        elif admin_action == "צפייה בספקים":
             show_suppliers_table(df_suppliers)
             
        # ... המשך הקוד של המנהל (אותו דבר כמו בתשובה הקודמת)

    else:
        # ממשק משתמש רגיל (נשאר אותו דבר)
        tab_view, tab_add = st.tabs(["צפייה", "הוספה"])
        with tab_view:
            show_suppliers_table(df_suppliers)
        with tab_add:
            # טופס הוספה (אותו דבר כמו בתשובה הקודמת)
            st.write("טופס הוספת ספק...")

# --- פונקציה מעודכנת להצגת טבלה מימין לשמאל ---
def show_suppliers_table(df):
    st.subheader("רשימת ספקים")
    search = st.text_input("חיפוש חופשי...", "")
    
    if not df.empty:
        # סינון הנתונים
        if search:
            df = df[
                df['שם הספק'].astype(str).str.contains(search, case=False, na=False) |
                df['תחום עיסוק'].astype(str).str.contains(search, case=False, na=False)
            ]
        
        # --- השינוי המרכזי: המרה ל-HTML כדי לשלוט בכיוון ---
        # הסתרת האינדקס (המספר 0 בצד) כי זה פחות רלוונטי למשתמש
        html_table = df.to_html(index=False, classes='rtl-table', border=0)
        
        # הוספת עיצוב CSS ספציפי לטבלה הזו
        st.markdown("""
        <style>
            .rtl-table {
                width: 100%;
                border-collapse: collapse;
                direction: rtl; /* כיוון הטבלה */
            }
            .rtl-table th {
                background-color: #f0f2f6;
                color: #31333F;
                text-align: right; /* יישור כותרות לימין */
                padding: 10px;
                border-bottom: 2px solid #ddd;
                font-weight: bold;
            }
            .rtl-table td {
                text-align: right; /* יישור תוכן לימין */
                padding: 10px;
                border-bottom: 1px solid #eee;
                color: #31333F;
            }
            .rtl-table tr:hover {
                background-color: #f9f9f9; /* אפקט ריחוף עדין */
            }
        </style>
        """, unsafe_allow_html=True)
        
        # הצגת הטבלה
        st.markdown(html_table, unsafe_allow_html=True)
        
        # כרטיסיות לנייד (נשאר אותו דבר)
        st.markdown("### 📱 כרטיסיות (לנייד)")
        for _, row in df.iterrows():
            with st.expander(f"{row['שם הספק']} - {row['תחום עיסוק']}"):
                st.write(f"📞 {row['טלפון']}")
                st.write(f"📍 {row['כתובת']}")
                st.write(f"💳 {row['תנאי תשלום']}")
                st.markdown(f"[חייג לספק](tel:{row['טלפון']})")
    else:
        st.info("אין נתונים להצגה")

# --- הרצה ---
set_rtl_css()
if not st.session_state.get('logged_in', False):
    login_page()
else:
    main_app()

