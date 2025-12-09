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
        /* --- הגדרות כלליות (RTL) --- */
        .stApp {
            direction: rtl;
            text-align: right;
        }
        
        /* יישור כל הטקסטים לימין */
        h1, h2, h3, h4, h5, h6, p, div, span, label, .stMarkdown, .stButton, .stAlert, .stSelectbox {
            text-align: right !important;
        }

        /* יישור שדות קלט */
        .stTextInput input, .stTextArea textarea, .stSelectbox, .stNumberInput input {
            direction: rtl;
            text-align: right;
        }
        
        /* יישור כפתורי רדיו וצ'קבוקס */
        .stRadio, .stCheckbox {
            direction: rtl;
            text-align: right;
        }
        .stRadio > div {
            flex-direction: row-reverse;
            justify-content: flex-end;
        }

        /* --- הגדרות למחשב (Desktop) --- */
        [data-testid="stSidebar"] {
            direction: rtl;
            text-align: right;
            border-left: 1px solid #ddd;
        }

        /* טבלה למחשב */
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
        }
        .rtl-table td { 
            text-align: right !important; 
            padding: 10px; 
            border-bottom: 1px solid #eee; 
            color: #333; 
        }

        /* --- הגדרות לטלפון (Mobile) --- */
        /* כרטיסיות */
        .mobile-card { 
            background-color: white; 
            border: 1px solid #ddd; 
            border-radius: 8px; 
            margin-bottom: 12px; 
            padding: 10px; 
            box-shadow: 0 2px 4px rgba(0,0,0,0.05); 
            direction: rtl; 
            text-align: right !important; 
        }
        .mobile-card summary { 
            font-weight: bold; 
            cursor: pointer; 
            color: #000; 
            list-style: none; 
            outline: none; 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
        }
        .mobile-card summary::after { 
            content: "+"; 
            font-size: 1.2em; 
            margin-right: 10px; 
            color: #666;
        }
        .mobile-card details[open] summary::after { 
            content: "-"; 
        }
        .mobile-card .card-content { 
            margin-top: 10px; 
            padding-top: 10px; 
            border-top: 1px solid #eee; 
            font-size: 0.95em; 
            color: #333; 
        }
        .mobile-card a { color: #0068c9; text-decoration: none; font-weight: bold; }

        /* הסתרת אלמנטים מיותרים */
        [data-testid="stElementToolbar"] { display: none; }
        
        /* --- שליטה בתצוגה (רספונסיביות) --- */
        .desktop-view { display: block; }
        .mobile-view { display: none; }

        /* --- ה-FIX הגדול: הסתרת תפריט צד בטלפון --- */
        @media only screen and (max-width: 768px) {
            /* החלפת תצוגה לכרטיסיות */
            .desktop-view { display: none; }
            .mobile-view { display: block; }

            /* העלמת ה-Sidebar וכל מה שקשור אליו בטלפון */
            [data-testid="stSidebar"] { display: none !important; }
            [data-testid="stSidebarCollapsedControl"] { display: none !important; }
            [data-testid="stSidebarResizeHandle"] { display: none !important; }
            
            /* התאמת ריווחים בטלפון */
            .block-container {
                padding-top: 2rem !important;
                padding-left: 1rem !important;
                padding-right: 1rem !important;
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

# --- תצוגת טבלה (ללא CSS פנימי שמתנגש) ---
def show_suppliers_table(df):
    st.subheader("רשימת ספקים")
    search = st.text_input("חיפוש חופשי...", "")
    
    if not df.empty:
        if search:
            df = df[
                df['שם הספק'].astype(str).str.contains(search, case=False, na=False) |
                df['תחום עיסוק'].astype(str).str.contains(search, case=False, na=False)
            ]
        
        # בניית HTML למחשב
        table_html = df.to_html(index=False, classes='rtl-table', border=0, escape=False)
        
        # בניית HTML לטלפון
        cards = []
        for _, row in df.iterrows():
            # שימוש ב-f-string בשורה אחת כדי למנוע בעיות רווחים
            card = f"""<div class="mobile-card"><details><summary><span>{row['שם הספק']} | {row['תחום עיסוק']}</span></summary><div class="card-content"><div><strong>טלפון:</strong> <a href="tel:{row['טלפון']}">{row['טלפון']}</a></div><div><strong>כתובת:</strong> {row['כתובת']}</div><div><strong>תנאי תשלום:</strong> {row['תנאי תשלום']}</div></div></details></div>"""
            cards.append(card)
        all_cards = "".join(cards)

        # הדפסה משולבת
        final_html = f"""<div class="desktop-view">{table_html}</div><div class="mobile-view">{all_cards}</div>"""
        st.markdown(final_html.replace('\n', ' '), unsafe_allow_html=True)
    else:
        st.info("אין נתונים להצגה")

# --- דף כניסה ---
def login_page():
    st.title("🔐 כניסה למערכת")
    
    # הסתרת כלי המנהל בטלפון (דרך ה-CSS הכללי זה כבר יקרה אם זה בתוך sidebar, אבל כאן זה בראשי)
    # נשאיר את זה פשוט
    with st.expander("כלי למנהל: יצירת Hash לסיסמה"):
        pass_to_hash = st.text_input("הכנס סיסמה להצפנה")
        if st.button("הצפן"):
            st.code(hash_password(pass_to_hash))

    tab1, tab2 = st.tabs(["התחברות", "הרשמה למערכת"])

    with tab1:
        with st.form("login_form"):
            # שימוש ב lower ו strip לטיפול באותיות גדולות/קטנות
            user = st.text_input("אימייל").lower().strip()
            pw = st.text_input("סיסמה", type="password")
            submitted = st.form_submit_button("התחבר")
            
            if submitted:
                df_users, _ = get_worksheet_data("users")
                if not df_users.empty:
                    # המרה ל-lower גם בבדיקה מול הנתונים
                    df_users['username'] = df_users['username'].astype(str).str.lower().str.strip()
                    user_record = df_users[df_users['username'] == user]
                    
                    if not user_record.empty:
                        stored_hash = user_record.iloc[0]['password']
                        if check_password(pw, stored_hash):
                            st.session_state['logged_in'] = True
                            st.session_state['username'] = user
                            st.session_state['name'] = user_record.iloc[0]['name']
                            st.session_state['role'] = user_record.iloc[0]['role']
                            st.success(f"ברוך הבא!")
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
                # בדיקה מול בסיס הנתונים (גם שם הכל כבר באותיות קטנות או שנמיר)
                existing_users = []
                if not df_users.empty:
                     existing_users = df_users['username'].astype(str).str.lower().str.strip().values
                
                if new_email in existing_users:
                    st.warning("משתמש זה כבר קיים במערכת")
                else:
                    hashed_pw = hash_password(new_pass)
                    add_row_to_sheet("pending_users", [new_email, hashed_pw, full_name, str(datetime.now())])
                    st.success("הבקשה נשלחה לאישור מנהל.")

# --- אפליקציה ראשית ---
def main_app():
    user_role = st.session_state.get('role', 'user')
    user_name = st.session_state.get('name', 'User')
    
    # --- תפריט צד (יוסתר בטלפון אוטומטית ע"י ה-CSS) ---
    st.sidebar.markdown(f"### שלום {user_name}")
    
    # כל הפעולות הועברו לסרגל הצד
    # בטלפון - הסרגל מוסתר -> אין פעולות -> רק צפייה
    
    # כפתור יציאה
    if st.sidebar.button("יציאה מהמערכת"):
        st.session_state['logged_in'] = False
        st.rerun()
        
    st.sidebar.markdown("---")
    
    # אזור הוספה (זמין לכולם, אבל רק במחשב כי זה בסיידבר)
    st.sidebar.subheader("➕ הוספת ספק")
    with st.sidebar.form("add_supplier_sidebar"):
        s_name = st.text_input("שם")
        s_field = st.text_input("תחום")
        s_phone = st.text_input("טלפון")
        s_addr = st.text_input("כתובת")
        s_pay = st.selectbox("תשלום", ["שוטף+30", "שוטף+60", "שוטף+90", "מזומן", "אשראי"])
        
        if st.form_submit_button("הוסף"):
            if user_role == 'admin':
                add_row_to_sheet("suppliers", [s_name, s_field, s_phone, s_addr, s_pay, user_name])
                st.sidebar.success("נוסף בהצלחה!")
            else:
                add_row_to_sheet("pending_suppliers", [s_name, s_field, s_phone, s_addr, s_pay, user_name, str(datetime.now())])
                st.sidebar.success("נשלח לאישור מנהל")

    # אזור ניהול (רק למנהל, רק במחשב)
    if user_role == 'admin':
        st.sidebar.markdown("---")
        st.sidebar.subheader("🛠️ ניהול מנהל")
        admin_mode = st.sidebar.radio("בחר כלי:", ["אישור משתמשים", "אישור ספקים", "מחיקת ספק", "יבוא אקסל"])
        
        # לוגיקה של הכלים שמוצגת מתחת לבחירה בסרגל הצד
        if admin_mode == "אישור משתמשים":
            df_pending, _ = get_worksheet_data("pending_users")
            if not df_pending.empty:
                st.sidebar.info(f"יש {len(df_pending)} בקשות")
                for idx, row in df_pending.iterrows():
                    st.sidebar.text(f"{row['name']}")
                    if st.sidebar.button("אשר", key=f"u_ok_{idx}"):
                        add_row_to_sheet("users", [row['username'], row['password'], 'user', row['name']])
                        delete_row_from_sheet("pending_users", "username", row['username'])
                        st.rerun()
            else:
                st.sidebar.text("אין משתמשים חדשים")

        elif admin_mode == "אישור ספקים":
            df_pend_supp, _ = get_worksheet_data("pending_suppliers")
            if not df_pend_supp.empty:
                st.sidebar.info(f"יש {len(df_pend_supp)} ספקים")
                for idx, row in df_pend_supp.iterrows():
                    with st.sidebar.expander(f"{row['שם הספק']}"):
                        st.write(row['תחום עיסוק'])
                        if st.button("אשר", key=f"s_ok_{idx}"):
                            add_row_to_sheet("suppliers", [row['שם הספק'], row['תחום עיסוק'], row['טלפון'], row['כתובת'], row['תנאי תשלום'], row['נוסף על ידי']])
                            delete_row_from_sheet("pending_suppliers", "שם הספק", row['שם הספק'])
                            st.rerun()
                        if st.button("דחה", key=f"s_no_{idx}"):
                            delete_row_from_sheet("pending_suppliers", "שם הספק", row['שם הספק'])
                            st.rerun()
            else:
                st.sidebar.text("אין ספקים לאישור")
        
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
             # כדי למחוק צריך לראות את הרשימה, אז ניתן למנהל לבחור מהרשימה הראשית אבל המחיקה תהיה מכאן
             # או פשוט תיבת טקסט למחיקה
             del_name = st.sidebar.text_input("הכנס שם ספק מדויק למחיקה")
             if st.sidebar.button("מחק ספק"):
                 if delete_row_from_sheet("suppliers", "שם הספק", del_name):
                     st.sidebar.success("נמחק")
                     time.sleep(1)
                     st.rerun()
                 else:
                     st.sidebar.error("לא נמצא")

    # --- תצוגה ראשית (מה שכולם רואים, ובטלפון זה הדבר היחיד שרואים) ---
    st.title("📦 ניהול ספקים")
    
    # טעינת ספקים והצגה
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
