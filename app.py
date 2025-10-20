import streamlit as st
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from datetime import date

# ---------- PAGE SETUP ----------
st.set_page_config(page_title="Employment Portal", page_icon="🧑‍💼", layout="centered")

# ---------- FUNCTIONS ----------
def rate_applicant(cover_letter, salary, position, cv_uploaded, completeness):
    score = 0
    score += completeness * 30  # Completeness (30%)

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
    else:
        score += 0

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

def send_email_notification(applicant_data):
    """Send HR email notification (edit with your email credentials)"""
    sender_email = "ghassanjo43@gmail.com"
    sender_password = "123456"   # use app-specific password if Gmail
    recipient_email = "ghassan.muammar@gmail.com"

    subject = f"New Application: {applicant_data['Full Name']} ({applicant_data['Position']})"
    body = f"""
    New Employment Application Received

    Name: {applicant_data['Full Name']}
    Email: {applicant_data['Email']}
    Phone: {applicant_data['Phone']}
    Position: {applicant_data['Position']}
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
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
        print("Email sent successfully!")
    except Exception as e:
        print("Email error:", e)

# ---------- PAGE NAVIGATION ----------
page = st.sidebar.selectbox("Navigation", ["📋 Applicant Form", "🔒 Admin Dashboard"])

# ---------- PAGE 1: APPLICANT FORM ----------
if page == "📋 Applicant Form":
    st.title("🧾 Employment Application Form")
    st.write("Please complete the form below to apply for a position at **Experts Group FZE**.")

    # --- Personal Info ---
    st.header("👤 Personal Information")
    full_name = st.text_input("Full Name")
    email = st.text_input("Email Address")
    phone = st.text_input("Phone Number")
    address = st.text_area("Address")

    # --- Job Details ---
    st.header("💼 Job Details")
    position = st.selectbox("Position Applied For", [
        "Business Analyst", "Software Engineer", "Project Manager",
        "Data Scientist", "Administrative Assistant", "Other"
    ])
    availability = st.date_input("Available Start Date", min_value=date.today())
    salary = st.number_input("Expected Monthly Salary (AED)", min_value=0, step=500)

    # --- Additional Info ---
    st.header("📝 Additional Information")
    cover_letter = st.text_area("Short Cover Letter", placeholder="Tell us why you're a great fit...")
    cv_file = st.file_uploader("Upload Your CV (PDF or Word)", type=["pdf", "docx"])

    # --- Submit ---
    if st.button("Submit Application"):
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
            if rating >= 85:
                remark = "🌟 Excellent Candidate"
            elif rating >= 70:
                remark = "✅ Strong Candidate"
            elif rating >= 50:
                remark = "⚖️ Average Candidate"
            else:
                remark = "⚠️ Below Standard"

            submission = {
                "Full Name": full_name,
                "Email": email,
                "Phone": phone,
                "Address": address,
                "Position": position,
                "Availability": availability.strftime("%Y-%m-%d"),
                "Expected Salary (AED)": salary,
                "Cover Letter": cover_letter,
                "File Name": cv_file.name,
                "Rating (%)": rating,
                "Evaluation": remark
            }

            df = pd.DataFrame([submission])
            df.to_csv("applications.csv", mode="a", index=False, header=False)

            # Send email to HR
            send_email_notification(submission)

            st.success(f"✅ Thank you, {full_name}! Your application has been submitted successfully.")
            st.write("Our HR team will contact you if your profile matches our requirements.")
            st.balloons()

# ---------- PAGE 2: ADMIN DASHBOARD ----------
elif page == "🔒 Admin Dashboard":
    st.title("🔐 HR Admin Dashboard")

    admin_password = st.text_input("Enter Admin Password", type="password")
    if admin_password == "experts2025":
        st.success("Access granted ✅")
        try:
            df = pd.read_csv("applications.csv", header=None)
            df.columns = [
                "Full Name", "Email", "Phone", "Address", "Position", "Availability",
                "Expected Salary (AED)", "Cover Letter", "File Name", "Rating (%)", "Evaluation"
            ]
            st.dataframe(df)
            st.download_button("⬇️ Download CSV", df.to_csv(index=False), "applications.csv")
        except FileNotFoundError:
            st.warning("No applications have been submitted yet.")
    elif admin_password:
        st.error("Incorrect password.")
