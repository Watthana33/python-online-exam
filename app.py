import streamlit as st
import random
import json
import pandas as pd
from datetime import datetime
import os
import gspread
import time
import streamlit.components.v1 as components

# --- การตั้งค่าระบบพื้นฐาน ---
st.set_page_config(page_title="ระบบสอบออนไลน์", page_icon="🎓", layout="centered", initial_sidebar_state="expanded")

QUESTIONS_FILE = 'questions.json'
CREDENTIALS_FILE = 'service_account.json'
SHEET_NAME = 'PythonExamScores'
STUDENTS_FILE = 'students.csv'
CONFIG_FILE = 'config.json'

# --- ซ่อนเมนู Streamlit และตกแต่ง UI ให้สวยงามน่าใช้งาน ---
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    .stApp { background-color: #f8fafc; }
    .card { background-color: white; padding: 30px; border-radius: 15px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); margin-bottom: 25px; border-top: 5px solid #3b82f6; }
    .main-title { font-size: 36px; font-weight: 900; color: #0f172a; text-align: center; margin-top: 20px; }
    .sub-title { font-size: 18px; color: #64748b; text-align: center; margin-bottom: 30px; }
    .stButton>button { background-color: #3b82f6; color: white; border-radius: 8px; padding: 10px 20px; font-weight: bold; transition: 0.3s; border: none; }
    .stButton>button:hover { background-color: #2563eb; transform: translateY(-2px); }
    .result-pass { color: #15803d; font-size: 30px; font-weight: bold; text-align: center; padding: 20px; background-color: #dcfce7; border-radius: 12px; margin: 20px 0; }
    .result-fail { color: #b91c1c; font-size: 30px; font-weight: bold; text-align: center; padding: 20px; background-color: #fee2e2; border-radius: 12px; margin: 20px 0; }
</style>
""", unsafe_allow_html=True)

# --- Functions (เพิ่ม Cache เพื่อแก้ปัญหาระบบหน่วง) ---
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"duration_minutes": 50, "max_attempts": 5, "questions_per_exam": 50, "admin_password": "Password1234!"}

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

@st.cache_data
def load_questions():
    with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

@st.cache_data
def get_allowed_students():
    if os.path.exists(STUDENTS_FILE):
        df = pd.read_csv(STUDENTS_FILE)
        df['student_id'] = df['student_id'].astype(str)
        return df
    return None

@st.cache_resource
def init_google_sheet():
    # วิธีที่ 1: ดึงจาก Streamlit Secrets (สำหรับบน Cloud)
    try:
        if "gcp_service_account" in st.secrets:
            # ตรวจสอบว่าเป็น string (JSON) หรือ Dictionary (TOML)
            secret_val = st.secrets["gcp_service_account"]
            if isinstance(secret_val, str):
                creds_dict = json.loads(secret_val)
            else:
                creds_dict = dict(secret_val)
            
            client = gspread.service_account_from_dict(creds_dict)
            return client.open(SHEET_NAME).sheet1
    except Exception as e:
        print(f"Error loading secrets: {e}")
        pass

    # วิธีที่ 2: ดึงจากไฟล์ service_account.json (สำหรับรันทดสอบในเครื่อง)
    if not os.path.exists(CREDENTIALS_FILE): return None
    try:
        client = gspread.service_account(filename=CREDENTIALS_FILE)
        return client.open(SHEET_NAME).sheet1
    except Exception: return None

def get_attempts(sheet, student_id):
    if sheet is None:
        if os.path.exists("local_scores.csv"):
            df = pd.read_csv("local_scores.csv")
            df['student_id'] = df['student_id'].astype(str)
            return len(df[df['student_id'] == str(student_id)])
        return 0
    else:
        try:
            records = sheet.get_all_records()
            if records:
                df = pd.DataFrame(records)
                if 'student_id' in df.columns:
                    df['student_id'] = df['student_id'].astype(str)
                    return len(df[df['student_id'] == str(student_id)])
            return 0
        except Exception: return 0

def save_score(sheet, student_id, first_name, last_name, score, total):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    record = [timestamp, str(student_id), first_name, last_name, score, total]
    if sheet is None:
        df = pd.DataFrame([record], columns=["timestamp", "student_id", "first_name", "last_name", "score", "total"])
        if os.path.exists("local_scores.csv"):
            df.to_csv("local_scores.csv", mode='a', header=False, index=False, encoding='utf-8')
        else:
            df.to_csv("local_scores.csv", index=False, encoding='utf-8')
    else:
        try: sheet.append_row(record)
        except Exception: pass

config = load_config()

# --- Initialize Session State ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'is_admin' not in st.session_state: st.session_state.is_admin = False
if 'exam_finished' not in st.session_state: st.session_state.exam_finished = False

sheet = init_google_sheet()

# --- ระบบ Admin ล้วนๆ (ผ่าน Sidebar เพื่อความปลอดภัย) ---
with st.sidebar:
    st.markdown("### 🔐 สำหรับผู้ดูแลระบบ")
    admin_pass_input = st.text_input("Admin Password", type="password")
    if st.button("เข้าสู่โหมด Admin", use_container_width=True):
        if admin_pass_input == config.get("admin_password", "Password1234!"):
            st.session_state.logged_in = True
            st.session_state.is_admin = True
            st.rerun()
        else:
            st.error("รหัสผ่านไม่ถูกต้อง")

st.markdown('<div class="main-title">🎓 ระบบทดสอบออนไลน์</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">วิชาการเขียนโปรแกรม Python เบื้องต้น</div>', unsafe_allow_html=True)

# --- View: Admin Mode ---
if st.session_state.logged_in and st.session_state.is_admin:
    st.markdown('<div class="card"><h3>🛡️ ระบบจัดการสำหรับผู้ดูแลระบบ (Admin)</h3></div>', unsafe_allow_html=True)
    st.info("สถานะการเชื่อมต่อฐานข้อมูล: " + ("✅ เชื่อมต่อ Google Sheets สำเร็จ" if sheet else "⚠️ ใช้ฐานข้อมูลสำรอง (CSV) ภายในเครื่อง"))
    
    col_settings, col_students = st.columns([1, 1])
    with col_settings:
        st.subheader("⚙️ ตั้งค่าระบบสอบ")
        new_duration = st.number_input("เวลาสอบ (นาที)", min_value=1, value=config.get("duration_minutes", 50))
        new_attempts = st.number_input("จำนวนครั้งที่ให้สอบได้สูงสุด", min_value=1, value=config.get("max_attempts", 5))
        new_q_count = st.number_input("จำนวนข้อสอบที่จะให้ทำ (ข้อ)", min_value=1, max_value=150, value=config.get("questions_per_exam", 50))
        new_admin_pass = st.text_input("เปลี่ยนรหัสผ่าน Admin", value=config.get("admin_password", "Password1234!"), type="password")
        
        if st.button("💾 บันทึกการตั้งค่า"):
            config["duration_minutes"] = new_duration
            config["max_attempts"] = new_attempts
            config["questions_per_exam"] = new_q_count
            config["admin_password"] = new_admin_pass
            save_config(config)
            st.success("บันทึกการตั้งค่าเรียบร้อยแล้ว (การตั้งค่ามีผลทันที)")
            
    with col_students:
        st.subheader("📋 รายชื่อผู้มีสิทธิ์สอบ")
        df_students = get_allowed_students()
        if df_students is not None: st.dataframe(df_students)
        else: st.warning("ไม่พบไฟล์ students.csv")
            
    st.subheader("📊 ประวัติคะแนนสอบ (local_scores.csv)")
    if os.path.exists("local_scores.csv"):
        df_scores = pd.read_csv("local_scores.csv")
        st.dataframe(df_scores)
    else: st.info("ยังไม่มีข้อมูลการสอบในระบบ")
            
    if st.button("🚪 ออกจากระบบผู้ดูแล"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()

# --- View: Login (Student) ---
elif not st.session_state.logged_in:
    q_to_show = config.get('questions_per_exam', 50)
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("#### 📝 คำชี้แจงก่อนสอบ")
    st.markdown(f"- ระบบจะสุ่มชุดข้อสอบให้ท่านทำจำนวน **{q_to_show} ข้อ**")
    st.markdown(f"- เวลาในการทำข้อสอบ: **{config['duration_minutes']} นาที**")
    st.markdown("- เกณฑ์การผ่าน: **60% ขึ้นไป**")
    st.markdown("- **ต้องทำข้อสอบให้ครบทุกข้อ จึงจะสามารถส่งได้**")
    st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("🔑 ลงชื่อเข้าสอบ")
    student_id = st.text_input("รหัสนักศึกษา (Student ID)", placeholder="เช่น 640001")
    first_name = st.text_input("ชื่อจริง (First Name)", placeholder="ไม่ต้องใส่คำนำหน้า")
    last_name = st.text_input("นามสกุล (Last Name)")
    
    if st.button("🚀 เข้าสู่ระบบเพื่อเริ่มสอบ", use_container_width=True):
        if not student_id or not first_name or not last_name:
            st.error("❌ กรุณากรอกข้อมูลให้ครบถ้วน")
        else:
            df_students = get_allowed_students()
            is_allowed = False
            if df_students is not None:
                match = df_students[(df_students['student_id'] == student_id) & 
                                    (df_students['first_name'] == first_name) & 
                                    (df_students['last_name'] == last_name)]
                if not match.empty: is_allowed = True
            
            if not is_allowed:
                st.error("❌ ไม่พบข้อมูลนักศึกษาในระบบ หรือกรอกชื่อ/สกุลไม่ตรงกับฐานข้อมูล")
            else:
                attempts = get_attempts(sheet, student_id)
                if attempts >= config["max_attempts"]:
                    st.error(f"❌ คุณทำการสอบครบจำนวน {config['max_attempts']} ครั้งแล้ว ไม่สามารถเข้าสอบได้อีก")
                else:
                    st.session_state.student_id = student_id
                    st.session_state.first_name = first_name
                    st.session_state.last_name = last_name
                    st.session_state.logged_in = True
                    st.session_state.is_admin = False
                    
                    # โหลดคลังข้อสอบทั้งหมด 3 ชุด
                    all_sets = load_questions()
                    selected_set_key = random.choice(list(all_sets.keys()))
                    selected_questions = all_sets[selected_set_key]
                    
                    # สุ่มข้อสอบตามจำนวนที่ Admin กำหนด (questions_per_exam)
                    actual_q_count = min(config.get('questions_per_exam', 50), len(selected_questions))
                    selected_questions = random.sample(selected_questions, actual_q_count)
                    
                    # สุ่มตัวเลือกในแต่ละข้อ
                    for q in selected_questions:
                        random.shuffle(q['options'])
                        
                    st.session_state.questions = selected_questions
                    st.session_state.current_q_idx = 0
                    st.session_state.user_answers = {}
                    
                    # ตั้งเวลาสิ้นสุด
                    end_time = datetime.now().timestamp() + (config['duration_minutes'] * 60)
                    st.session_state.end_time = end_time
                    st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# --- View: Exam (Student) ---
elif st.session_state.logged_in and not st.session_state.exam_finished and not st.session_state.is_admin:
    
    current_time = datetime.now().timestamp()
    if current_time >= st.session_state.end_time:
        st.session_state.exam_finished = True
        st.warning("⚠️ หมดเวลาทำข้อสอบ ระบบได้ส่งคำตอบของคุณโดยอัตโนมัติ")
        score = 0
        for i, q in enumerate(st.session_state.questions):
            ans = st.session_state.user_answers.get(i)
            if ans == q['answer']: score += 1
        st.session_state.score = score
        save_score(sheet, st.session_state.student_id, st.session_state.first_name, st.session_state.last_name, score, len(st.session_state.questions))
        st.rerun()

    time_left_seconds = max(0, st.session_state.end_time - current_time)
    
    timer_html = f"""
    <div id="countdown" style="font-size:22px; font-weight:800; color:#ef4444; background:#fee2e2; padding:8px 20px; border-radius:10px; text-align:center; margin-bottom:20px;">
        กำลังโหลดเวลา...
    </div>
    <script>
        var endTime = {st.session_state.end_time * 1000};
        var x = setInterval(function() {{
            var now = new Date().getTime();
            var distance = endTime - now;
            if (distance < 0) {{
                clearInterval(x);
                document.getElementById("countdown").innerHTML = "⚠️ หมดเวลา! (กรุณากดปุ่มเพื่อส่งข้อสอบ)";
            }} else {{
                var minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
                var seconds = Math.floor((distance % (1000 * 60)) / 1000);
                var m = minutes < 10 ? "0" + minutes : minutes;
                var s = seconds < 10 ? "0" + seconds : seconds;
                document.getElementById("countdown").innerHTML = "⏳ เวลาที่เหลือ: " + m + ":" + s + " นาที";
            }}
        }}, 1000);
    </script>
    """
    components.html(timer_html, height=70)

    q_idx = st.session_state.current_q_idx
    q_total = len(st.session_state.questions)
    current_q = st.session_state.questions[q_idx]
    
    st.markdown(f'<div style="text-align: right; color: #64748b; margin-bottom: 10px;">👤 ผู้เข้าสอบ: {st.session_state.first_name} {st.session_state.last_name} ({st.session_state.student_id})</div>', unsafe_allow_html=True)
    st.progress((q_idx) / q_total)
    st.caption(f"📝 ข้อที่ {q_idx + 1} จาก {q_total}")
    
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(f"<h3>{current_q['question']}</h3>", unsafe_allow_html=True)
    
    default_index = None
    if q_idx in st.session_state.user_answers:
        previous_answer = st.session_state.user_answers[q_idx]
        if previous_answer in current_q['options']:
            default_index = current_q['options'].index(previous_answer)
            
    selected_option = st.radio("เลือกคำตอบที่ถูกต้อง:", current_q['options'], index=default_index, label_visibility="collapsed")
    if selected_option is not None:
        st.session_state.user_answers[q_idx] = selected_option
        
    st.markdown('</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns([1, 1])
    with col1:
        if q_idx > 0:
            if st.button("⬅️ ย้อนกลับ", use_container_width=True):
                st.session_state.current_q_idx -= 1
                st.rerun()
                
    with col2:
        if q_idx < q_total - 1:
            if st.button("ถัดไป ➡️", use_container_width=True):
                st.session_state.current_q_idx += 1
                st.rerun()
        else:
            if st.button("✅ ส่งข้อสอบ", use_container_width=True):
                if len(st.session_state.user_answers) < q_total:
                    st.error("⚠️ ไม่สามารถส่งข้อสอบได้ เนื่องจากคุณยังทำข้อสอบไม่ครบทุกข้อ กรุณากดย้อนกลับไปทำข้อที่ข้ามไว้")
                else:
                    score = 0
                    for i, q in enumerate(st.session_state.questions):
                        ans = st.session_state.user_answers.get(i)
                        if ans == q['answer']: score += 1
                            
                    st.session_state.score = score
                    st.session_state.exam_finished = True
                    save_score(sheet, st.session_state.student_id, st.session_state.first_name, st.session_state.last_name, score, q_total)
                    st.rerun()

# --- View: Result (Student) ---
elif st.session_state.exam_finished and not st.session_state.is_admin:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("📊 ผลการประเมินของคุณ")
    st.write(f"**ชื่อ-สกุล:** {st.session_state.first_name} {st.session_state.last_name}")
    st.write(f"**รหัสนักศึกษา:** {st.session_state.student_id}")
    
    score = st.session_state.score
    total = len(st.session_state.questions)
    percentage = (score / total) * 100 if total > 0 else 0
    
    st.metric(label="คะแนนที่ทำได้", value=f"{score} / {total} ({percentage:.2f}%)")
    
    if percentage >= 60:
        st.markdown('<div class="result-pass">✅ ยินดีด้วย! คุณสอบผ่าน</div>', unsafe_allow_html=True)
        st.balloons()
        btn_text = "🚪 กลับสู่หน้าหลัก"
    else:
        st.markdown('<div class="result-fail">❌ คุณไม่ผ่าน กรุณาเตรียมตัวและสอบใหม่</div>', unsafe_allow_html=True)
        btn_text = "🔄 ทำข้อสอบใหม่อีกครั้ง"
        
    st.markdown('</div>', unsafe_allow_html=True)
    
    if st.button(btn_text, use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
