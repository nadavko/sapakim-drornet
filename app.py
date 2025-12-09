import streamlit as st
import pandas as pd
import os

# שם קובץ הנתונים (הבסיס נתונים שלנו)
DATA_FILE = "suppliers_data.csv"

# פונקציה לטעינת הנתונים
def load_data():
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    else:
        # יצירת מבנה בסיסי אם הקובץ לא קיים
        return pd.DataFrame(columns=["שם הספק", "תחום עיסוק", "טלפון", "כתובת", "תנאי תשלום"])

# פונקציה לשמירת הנתונים
def save_data(df):
    df.to_csv(DATA_FILE, index=False)

# הגדרות עמוד
st.set_page_config(page_title="מערכת ניהול ספקים", layout="wide", initial_sidebar_state="expanded")

# --- כותרת ראשית ---
st.title("📦 מערכת ניהול ספקים")

# טעינת הנתונים
df = load_data()

# --- סרגל צד (ממשק ניהול) ---
st.sidebar.header("ממשק ניהול (למנהל בלבד)")
admin_mode = st.sidebar.checkbox("הפעל מצב עריכה/ניהול")

if admin_mode:
    st.sidebar.markdown("---")
    action = st.sidebar.radio("בחר פעולה:", ["הוספת ספק ידנית", "יבוא מאקסל", "מחיקת נתונים"])

    # 1. הוספת ספק ידנית
    if action == "הוספת ספק ידנית":
        st.subheader("הוספת ספק חדש")
        with st.form("add_supplier_form"):
            name = st.text_input("שם הספק")
            # ניתן להזין מספר תחומים מופרדים בפסיק
            field = st.text_input("תחום עיסוק (ניתן לרשום כמה מופרדים בפסיק)")
            phone = st.text_input("טלפון")
            address = st.text_input("כתובת")
            payment_terms = st.selectbox("תנאי תשלום", ["שוטף + 30", "שוטף + 60", "שוטף + 90", "מזומן", "אשראי", "אחר"])
            
            submitted = st.form_submit_button("שמור ספק")
            if submitted:
                if name and field:
                    new_data = pd.DataFrame({
                        "שם הספק": [name],
                        "תחום עיסוק": [field],
                        "טלפון": [phone],
                        "כתובת": [address],
                        "תנאי תשלום": [payment_terms]
                    })
                    df = pd.concat([df, new_data], ignore_index=True)
                    save_data(df)
                    st.success(f"הספק {name} נוסף בהצלחה!")
                    st.rerun() # רענון כדי להציג בטבלה
                else:
                    st.error("חובה להזין לפחות שם ספק ותחום עיסוק")

    # 2. יבוא מאקסל
    elif action == "יבוא מאקסל":
        st.subheader("יבוא ספקים מקובץ Excel")
        st.info("הקובץ חייב להכיל את העמודות: 'שם הספק', 'תחום עיסוק', 'טלפון', 'כתובת', 'תנאי תשלום'")
        uploaded_file = st.file_uploader("גרור לכאן קובץ אקסל", type=["xlsx", "xls"])
        
        if uploaded_file:
            if st.button("טען נתונים"):
                try:
                    excel_data = pd.read_excel(uploaded_file)
                    # וידוא שיש עמודות תואמות (אופציונלי, כרגע מוסיף הכל)
                    df = pd.concat([df, excel_data], ignore_index=True)
                    save_data(df)
                    st.success("הנתונים נטענו בהצלחה מהאקסל!")
                    st.rerun()
                except Exception as e:
                    st.error(f"שגיאה בטעינת הקובץ: {e}")

    # 3. מחיקת נתונים (לזהירות)
    elif action == "מחיקת נתונים":
        if st.button("מחק את כל המאגר (זהירות!)"):
            df = pd.DataFrame(columns=["שם הספק", "תחום עיסוק", "טלפון", "כתובת", "תנאי תשלום"])
            save_data(df)
            st.warning("כל הנתונים נמחקו.")
            st.rerun()

# --- תצוגה לעובדים (מסך ראשי) ---
st.markdown("---")
st.subheader("🔎 חיפוש וצפייה בספקים")

# מנגנון חיפוש
search_term = st.text_input("חפש לפי שם ספק או תחום עיסוק...", "")

if not df.empty:
    if search_term:
        # סינון הטבלה לפי החיפוש
        filtered_df = df[
            df['שם הספק'].astype(str).str.contains(search_term, case=False, na=False) |
            df['תחום עיסוק'].astype(str).str.contains(search_term, case=False, na=False)
        ]
    else:
        filtered_df = df

    # הצגת הטבלה בצורה אינטראקטיבית
    st.dataframe(
        filtered_df,
        use_container_width=True,
        hide_index=True
    )
    
    # הצגה ככרטיסיות (יותר נוח בטלפון)
    st.markdown("### תצוגת כרטיסיות (מותאם לנייד)")
    for index, row in filtered_df.iterrows():
        with st.expander(f"📌 {row['שם הספק']} - {row['תחום עיסוק']}"):
            st.write(f"**טלפון:** {row['טלפון']}")
            st.write(f"**כתובת:** {row['כתובת']}")
            st.write(f"**תנאי תשלום:** {row['תנאי תשלום']}")
            # כפתור חיוג מהיר בטלפון
            st.markdown(f"[📞 חייג לספק](tel:{row['טלפון']})")

else:
    st.info("עדיין אין ספקים במערכת. השתמש בממשק הניהול בצד ימין כדי להוסיף.")