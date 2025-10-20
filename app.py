import os
from datetime import date
import json
import bcrypt
import smtplib
from email.mime.text import MIMEText
import streamlit as st
import pandas as pd

# -----------------------
# APP CONFIG
# -----------------------
st.set_page_config(page_title="Employment Portal", page_icon="🧑‍💼", layout="wide")

# -----------------------
# RATING ENGINE
# -----------------------
def rate_applicant(cover_letter, salary, position, cv_uploaded, completeness):
    score = 0
    # Completeness (30%)
    score += completeness * 30

    # Cover Letter Quality (30%)
    if cover_letter:
        length = len(cover_letter.split())
        if length > 150:
            score += 30
        elif length > 80:
            score += 22
        elif length > 40:
            score += 15
        else:
            score += 5
        keywords = ["experience", "team", "lead", "develop", "analyze", "project", "result"]
        keyword_hits = sum(1 for k in keywords if k.lower() in cover_letter.lower())
        score += min(keyword_hits * 2, 10)
    # Salary Expectation (20%)
    avg_salary = {
        "Business Analyst": 12000,
        "Software Engineer": 15000,
        "Project Manager": 18000,
        "Data Scientist": 16000,
        "Administrative Assistant": 8000,
        "Other": 10000
    }
    expected = avg_salary.get(position, 10000)
    diff_ratio = salary / expected if expected else 1
    if 0.8 <= diff_ratio <= 1.2:
        score += 20
    elif diff_ratio < 0.8:
        score += 15
    else:
        score += 10

    # CV Upload (10%)
    score += 10 if cv_uploaded else 0
    return round(min(score, 100), 2)

def rating_remark(rating):
    if rating >= 85:
        return "🌟 Excellent Candidate"
    elif rating >= 70:
        return "✅ Strong Candidate"
    elif rating >= 50:
        return "⚖️ Average Candidate"
    else:
        return "⚠️ Below Standard"

# -----------------------
# PASSWORD STORAGE BACKENDS
# -----------------------
class PasswordStoreBase:
    name = "base"
    supports_change = False
    def verify(self, raw_password: str) -> bool: raise NotImplementedError
    def change(self, old_password: str, new_password: str) -> bool: raise NotImplementedError
    def help_text(self) -> str: return ""

# 1) Supabase backend (persistent & cloud-friendly)
class SupabasePasswordStore(PasswordStoreBase):
    name = "supabase"
    supports_change = True
    def __init__(self):
        self.url = st.secrets.get("SUPABASE_URL")
        self.key = st.secrets.get("SUPABASE_KEY")
        self.table = st.secrets.get("SUPABASE_TABLE", "settings")
        self.row_key = st.secrets.get("SUPABASE_PW_KEY", "admin_password_hash")
        if not (self.url and self.key):
            raise RuntimeError("Supabase secrets not configured.")
        try:
            from supabase import create_client, Client
            self.client = create_client(self.url, self.key)
        except Exception as e:
            raise RuntimeError(f"Supabase client not available: {e}")

        # Ensure a row exists
        res = self.client.table(self.table).select("*").eq("key", self.row_key).execute()
        if len(res.data) == 0:
            default_hash = bcrypt.hashpw(b"experts2025", bcrypt.gensalt()).decode()
            self.client.table(self.table).insert({"key": self.row_key, "value": default_hash}).execute()

    def _get_hash(self):
        res = self.client.table(self.table).select("value").eq("key", self.row_key).single().execute()
        return res.data["value"]

    def verify(self, raw_password: str) -> bool:
        hashed = self._get_hash()
        return bcrypt.checkpw(raw_password.encode(), hashed.encode())

    def change(self, old_password: str, new_password: str) -> bool:
        if not self.verify(old_password):
            return False
        new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        self.client.table(self.table).update({"value": new_hash}).eq("key", self.row_key).execute()
        return True

    def help_text(self) -> str:
        return "Using Supabase for persistent admin password. Changes persist across redeploys."

# 2) Local JSON backend (great for local dev)
class LocalJsonPasswordStore(PasswordStoreBase):
    name = "local_json"
    supports_change = True
    def __init__(self, file_path="password_store.json"):
        self.file_path = file_path
        if not os.path.exists(self.file_path):
            default_hash = bcrypt.hashpw(b"experts2025", bcrypt.gensalt()).decode()
            json.dump({"admin_password": default_hash}, open(self.file_path, "w"))
    def _get_hash(self):
        return json.load(open(self.file_path))["admin_password"]
    def verify(self, raw_password: str) -> bool:
        return bcrypt.checkpw(raw_password.encode(), self._get_hash().encode())
    def change(self, old_password: str, new_password: str) -> bool:
        if not self.verify(old_password):
            return False
        new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        json.dump({"admin_password": new_hash}, open(self.file_path, "w"))
        return True
    def help_text(self) -> str:
        return f"Using local file {self.file_path} (persists on your machine)."

# 3) Secrets backend (simple & secure, but read-only)
class SecretsPasswordStore(PasswordStoreBase):
    name = "secrets"
    supports_change = False
    def __init__(self):
        # if you store a hash, set ADMIN_PASSWORD_HASH; if you store plain, set ADMIN_PASSWORD
        self.plain = st.secrets.get("admin_password")
        self.hashed = st.secrets.get("admin_password_hash")
        if not (self.plain or self.hashed):
            raise RuntimeError("No admin_password or admin_password_hash in secrets.")
    def verify(self, raw_password: str) -> bool:
        if self.plain:
            return raw_password == self.plain
        return bcrypt.checkpw(raw_password.encode(), self.hashed.encode())
    def change(self, old_password: str, new_password: str) -> bool:
        return False  # not possible at runtime on Streamlit Cloud
    def help_text(self) -> str:
        return ("Using Streamlit Secrets. To change the password, open your app on Streamlit Cloud "
                "→ **Edit secrets** and update `admin_password` (or `admin_password_hash`).")

def get_password_store():
    # Priority: Supabase (if configured) → Secrets → Local JSON
    try:
        if "SUPABASE_URL" in st.secrets and "SUPABASE_KEY" in st.secrets:
            return SupabasePasswordStore()
    except Exception:
        pass
    try:
        if "admin_password" in st.secrets or "admin_password_hash" in st.secrets:
            return SecretsPasswordStore()
    except Exception:
        pass
    return LocalJsonPasswordStore()

PW_STORE = get_password_store()

# -----------------------
# EMAIL SENDER
# -----------------------
def send_email_notification(applicant_data):
    sender_email     = st.secrets.get("SMTP_SENDER_EMAIL", os.getenv("SMTP_SENDER_EMAIL", ""))
    sender_password  = st.secrets.get("SMTP_SENDER_PASSWORD", os.getenv("SMTP_SENDER_PASSWORD", ""))
    smtp_host        = st.secrets.get("SMTP_HOST", os.getenv("SMTP_HOST", "smtp.gmail.com"))
    smtp_port        = int(st.secrets.get("SMTP_PORT", os.getenv("SMTP_PORT", "465")))
    recipient_email  = st.secrets.get("HR_RECIPIENT_EMAIL", os.getenv("HR_RECIPIENT_EMAIL", ""))

    if not (sender_email and sender_password and recipient_email):
        st.info("📧 Email not configured (missing SMTP secrets). Skipping email send.")
        return

    subject = f"New Application: {applicant_data['Full Name']} ({applicant_data['Position']})"
    body = f"""
New Employment Application Received

Name: {applicant_data['Full Name']}
Email: {applicant_data['Email']}
Phone: {applicant_data['Phone']}
Position: {applicant_data['Position']}
Available From: {applicant_data['Availability']}
Expected Salary: {applicant_data['Expected Salary (AED)']} AED

Rating: {applicant_data['Rating (%)']}%
Evaluation: {applicant_data['Evaluation']}

Cover Letter:
{applicant_data['Cover Letter']}

CV File: {applicant_data['File Name']}
"""

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = recipient_email

    try:
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                server.login(sender_email, sender_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.send_message(msg)
    except Exception as e:
        st.error(f"Email error: {e}")

# -----------------------
# DATA STORAGE (CSV)
# -----------------------
CSV_FILE = "applications.csv"

def append_submission(submission: dict):
    df = pd.DataFrame([submission])
    # Add header if file doesn't exist
    write_header = not os.path.exists(CSV_FILE)
    df.to_csv(CSV_FILE, mode="a", index=False, header=write_header)

def read_submissions():
    if not os.path.exists(CSV_FILE):
        return None
    df = pd.read_csv(CSV_FILE)
    return df

# -----------------------
# UI: SIDEBAR NAV
# -----------------------
st.sidebar.title("Navigation")
page = st.sidebar.radio("", ["📋 Applicant Form", "🔒 Admin Dashboard"])

# -----------------------
# PAGE: APPLICANT FORM
# -----------------------
if page == "📋 Applicant Form":
    st.title("🧾 Employment Application Form")
    st.write("Please complete the form to apply for a position at **Experts Group FZE**.")

    with st.form("app_form", clear_on_submit=False):
        # Personal
        st.subheader("👤 Personal Information")
        full_name = st.text_input("Full Name*")
        email = st.text_input("Email Address*")
        phone = st.text_input("Phone Number")
        address = st.text_area("Address")

        # Job
        st.subheader("💼 Job Details")
        position = st.selectbox("Position Applied For", [
            "Business Analyst", "Software Engineer", "Project Manager",
            "Data Scientist", "Administrative Assistant", "Other"
        ])
        availability = st.date_input("Available Start Date", min_value=date.today())
        salary = st.number_input("Expected Monthly Salary (AED)", min_value=0, step=500)

        # Additional
        st.subheader("📝 Additional Information")
        cover_letter = st.text_area("Short Cover Letter", placeholder="Tell us why you're a great fit...")
        cv_file = st.file_uploader("Upload Your CV (PDF or Word)*", type=["pdf", "docx"])

        submitted = st.form_submit_button("Submit Application")

    if submitted:
        missing = []
        if not full_name.strip(): missing.append("Full Name")
        if not email.strip(): missing.append("Email Address")
        if cv_file is None: missing.append("CV Upload")

        if missing:
            st.warning(f"⚠️ Please complete: {', '.join(missing)}.")
        else:
            filled_fields = sum([
                bool(full_name.strip()), bool(email.strip()), bool(phone.strip()), bool(address.strip()),
                bool(position), bool(availability), bool(salary), bool(cover_letter.strip()), bool(cv_file)
            ])
            completeness = filled_fields / 9

            rating = rate_applicant(cover_letter, salary, position, bool(cv_file), completeness)
            remark = rating_remark(rating)

            submission = {
                "Full Name": full_name,
                "Email": email,
                "Phone": phone,
                "Address": address,
                "Position": position,
                "Availability": availability.strftime("%Y-%m-%d"),
                "Expected Salary (AED)": salary,
                "Cover Letter": cover_letter,
                "File Name": cv_file.name if cv_file else "",
                "Rating (%)": rating,
                "Evaluation": remark
            }

            # Save & notify
            append_submission(submission)
            send_email_notification(submission)

            # Applicant confirmation (NO rating shown)
            st.success(f"✅ Thank you, {full_name}! Your application has been submitted successfully.")
            st.caption("Our HR team will contact you if your profile matches our requirements.")
            st.balloons()

# -----------------------
# PAGE: ADMIN DASHBOARD
# -----------------------
elif page == "🔒 Admin Dashboard":
    st.title("🔐 HR Admin Dashboard")

    # Login
    if "auth_ok" not in st.session_state:
        st.session_state.auth_ok = False

    col1, col2 = st.columns([1,2])
    with col1:
        st.write(f"🔒 Password backend: **{PW_STORE.name}**")
        st.caption(PW_STORE.help_text())

    pwd = st.text_input("Enter Admin Password", type="password")
    if st.button("Login") and pwd:
        if PW_STORE.verify(pwd):
            st.session_state.auth_ok = True
            st.success("Access granted ✅")
        else:
            st.error("Incorrect password ❌")

    if st.session_state.auth_ok:
        st.markdown("### 📂 Applications")
        df = read_submissions()
        if df is None or df.empty:
            st.info("No applications have been submitted yet.")
        else:
            # Ensure proper columns if headerless prior
            expected_cols = ["Full Name","Email","Phone","Address","Position","Availability",
                             "Expected Salary (AED)","Cover Letter","File Name","Rating (%)","Evaluation"]
            if list(df.columns) != expected_cols and len(df.columns) == len(expected_cols):
                df.columns = expected_cols
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Download CSV", df.to_csv(index=False), "applications.csv")

        st.markdown("---")
        st.markdown("### 🔑 Change Admin Password")

        if not PW_STORE.supports_change:
            st.info("This backend is read-only at runtime. To change the admin password, open your app on Streamlit Cloud → **Edit secrets** and update `admin_password`.")
        else:
            with st.form("change_pw"):
                old_pw = st.text_input("Current Password", type="password")
                new_pw1 = st.text_input("New Password", type="password")
                new_pw2 = st.text_input("Confirm New Password", type="password")
                submit_pw = st.form_submit_button("Change Password")
                if submit_pw:
                    if not old_pw or not new_pw1 or not new_pw2:
                        st.warning("Please fill in all fields.")
                    elif new_pw1 != new_pw2:
                        st.error("❌ New passwords do not match.")
                    elif len(new_pw1) < 6:
                        st.warning("Password should be at least 6 characters.")
                    else:
                        ok = PW_STORE.change(old_pw, new_pw1)
                        if ok:
                            st.success("✅ Password changed successfully! It will persist with this backend.")
                        else:
                            st.error("❌ Current password is incorrect.")

        st.markdown("---")
        st.caption("© 2025 Experts Group FZE | HR Admin")
