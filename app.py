import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time

# --- הגדרות חיבור לגוגל ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "ניהול ספקים"

# --- פונקציות עזר לאבטחה ---
def check_login():
    """בדיקה האם המשתמש מחובר, ואם לא - הצגת מסך התחברות"""
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    if not st.session_state['logged_in']:
        # מסך התחברות
        st.title("🔒 מערכת ניהול ספקים - הזדהות")
        
        with st.form("login_form"):
            username = st.text_input("שם משתמש")
            password = st.text_input("סיסמה", type="password")
            submit = st.form_submit_button("התחבר")
            
            if submit:
                # בדיקה מול רשימת המשתמשים המורשים (המוגדרת ב-Secrets)
                valid_users = st.secrets["auth"]["users"]
                
                # בדיקה אם המשתמש קיים והסיסמה נכונה
                # המבנה ב-Secrets צריך להיות רשימה של מילונים או מילון פשוט
                if username in valid_users and valid_users[username] == password:
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = username
                    st.success("התחברת בהצלחה! טוען מערכת...")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("שם משתמש או סיסמה שגויים")
        return False # לא מחובר
    return True # מחובר

def get_google_sheet_client():
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    client = gspread.authorize(creds)
    return client

def load_data():
    try:
        client = get_google_sheet_client()
        sheet = client.open(SHEET_NAME).sheet1
        data = sheet.get_all_records()
        if data:
            return pd.DataFrame(data)
        else:
            return pd.DataFrame(columns=["שם הספק", "תחום עיסוק", "טלפון", "כתובת", "תנאי תשלום"])
    except Exception as e:
        st.error(f"שגיאה בטעינת נתונים: {e}")
        return pd.DataFrame(columns=["שם הספק", "תחום עיסוק", "טלפון", "כתובת", "תנאי תשלום"])

def save_data(df):
    try:
        client = get_google_sheet_client()
        sheet = client.open(SHEET_NAME).sheet1
        sheet.clear()
        sheet.append_row(df.columns.tolist())
        sheet.append_rows(df.values.tolist())
    except Exception as e:
        st.error(f"שגיאה בשמירה: {e}")

# --- התוכנית הראשית ---
st.set_page_config(page_title="מערכת ספקים", layout="wide")

# שלב 1: חסימת גישה למי שלא מחובר
if not check_login():
    st.stop()  # עוצר את ריצת הקוד כאן אם המשתמש לא מחובר

# --- מכאן והלאה הקוד רץ רק למשתמשים מחוברים ---

# הצגת שם המשתמש המחובר בסרגל הצד
st.sidebar.info(f"מחובר כ: {st.session_state['username']}")
if st.sidebar.button("התנתק"):
    st.session_state['logged_in'] = False
    st.rerun()

st.title("📦 מערכת ניהול ספקים")

# טעינת נתונים (קורית רק אחרי לוגין)
df = load_data()

# ממשק ניהול (זמין לכולם כרגע, אפשר להגביל רק למנהל אם תרצה)
st.sidebar.header("ממשק ניהול")
admin_mode = st.sidebar.checkbox("הפעל מצב עריכה")

if admin_mode:
    st.sidebar.markdown("---")
    action = st.sidebar.radio("בחר פעולה:", ["הוספת ספק ידנית", "יבוא מאקסל", "מחיקת נתונים"])

    if action == "הוספת ספק ידנית":
        with st.form("add_supplier"):
            name = st.text_input("שם הספק")
            field = st.text_input("תחום עיסוק")
            phone = st.text_input("טלפון")
            address = st.text_input("כתובת")
            payment = st.selectbox("תנאי תשלום", ["שוטף + 30", "שוטף + 60", "שוטף + 90", "מזומן", "אשראי"])
            if st.form_submit_button("שמור"):
                new_row = pd.DataFrame([{"שם הספק": name, "תחום עיסוק": field, "טלפון": phone, "כתובת": address, "תנאי תשלום": payment}])
                df = pd.concat([df, new_row], ignore_index=True)
                save_data(df)
                st.success("נשמר!")
                st.rerun()

    elif action == "יבוא מאקסל":
        f = st.file_uploader("בחר קובץ אקסל")
        if f and st.button("טען"):
            try:
                new_data = pd.read_excel(f).astype(str)
                df = pd.concat([df, new_data], ignore_index=True)
                save_data(df)
                st.success("נטען!")
                st.rerun()
            except Exception as e:
                st.error(f"תקלה: {e}")

    elif action == "מחיקת נתונים":
        if st.button("מחק הכל"):
            save_data(pd.DataFrame(columns=["שם הספק", "תחום עיסוק", "טלפון", "כתובת", "תנאי תשלום"]))
            st.warning("נמחק.")
            st.rerun()

# תצוגה
st.markdown("---")
search = st.text_input("חיפוש...")
if not df.empty:
    res = df
    if search:
        res = df[df['שם הספק'].str.contains(search, case=False, na=False) | df['תחום עיסוק'].str.contains(search, case=False, na=False)]
    
    st.dataframe(res, use_container_width=True, hide_index=True)
    
    st.markdown("### כרטיסיות")
    for _, r in res.iterrows():
        with st.expander(f"{r['שם הספק']}"):
            st.write(f"עיסוק: {r['תחום עיסוק']}")
            st.write(f"טלפון: {r['טלפון']}")
            st.write(f"תשלום: {r['תנאי תשלום']}")
