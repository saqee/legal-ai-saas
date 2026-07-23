import streamlit as st
import pypdf
from google import genai
from supabase import create_client, Client

# --- ১. পেজ কনফিগারেশন ---
st.set_page_config(page_title="Legal AI - Contract Analyzer", page_icon="📜", layout="wide")

# Secrets থেকে তথ্য লোড
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")
ADMIN_EMAIL = st.secrets.get("ADMIN_EMAIL", "").strip().lower()
STRIPE_LINK = st.secrets.get("stripe_link", "#")

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_supabase()

st.title("📜 AI Contract & Legal Document Analyzer")

# --- ২. ইউজার লগইন / রেজিস্ট্রেশন (Sidebar) ---
st.sidebar.title("👤 User Account")

if "user_email" not in st.session_state:
    st.session_state.user_email = None

if not st.session_state.user_email:
    auth_mode = st.sidebar.radio("Choose Action", ["Login", "Sign Up"])
    email = st.sidebar.text_input("Email")
    password = st.sidebar.text_input("Password", type="password")

    if auth_mode == "Sign Up":
        if st.sidebar.button("Create Account"):
            try:
                res = supabase.auth.sign_up({"email": email, "password": password})
                st.sidebar.success("অ্যাকাউন্ট তৈরি হয়েছে! এখন Login করুন।")
            except Exception as e:
                st.sidebar.error(f"Error: {str(e)}")

    elif auth_mode == "Login":
        if st.sidebar.button("Log In"):
            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.user_email = res.user.email.strip().lower()
                st.sidebar.success(f"Welcome, {st.session_state.user_email}")
                st.rerun()
            except Exception as e:
                st.sidebar.error("ইমেইল বা পাসওয়ার্ড ভুল হয়েছে।")
else:
    is_admin = (st.session_state.user_email == ADMIN_EMAIL)
    
    if is_admin:
        st.sidebar.success("👑 Admin Account (Unlimited Access)")
    else:
        st.sidebar.write(f"Logged in as: **{st.session_state.user_email}**")
        
    if st.sidebar.button("Log Out"):
        st.session_state.user_email = None
        st.rerun()

# --- ৩. ইউজার কয়টি ফাইল বিশ্লেষণ করেছে তা পরীক্ষা করার ফাংশন ---
def get_user_usage_count(email):
    try:
        response = supabase.table("user_analyses").select("id", count="exact").eq("user_email", email).execute()
        return response.count
    except Exception as e:
        print(f"Usage count error: {e}")
        return 0

# --- ৪. কাজের ইতিহাস Supabase-এ সেভ করার ফাংশন ---
def log_user_activity(email, file_name):
    try:
        data = {"user_email": email, "file_name": file_name}
        supabase.table("user_analyses").insert(data).execute()
    except Exception as e:
        print(f"Supabase logging failed: {e}")

# --- ৫. PDF Extraction & Gemini Logic (With Multiple Model Fallback) ---
def extract_text_from_pdf(pdf_file):
    reader = pypdf.PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text

def analyze_contract_with_gemini(contract_text, api_key):
    try:
        client = genai.Client(api_key=api_key)
        
        prompt = f"""You are an expert legal advisor. Analyze the following contract document carefully:
1. Executive Summary (3 bullet points).
2. Key Legal Risks & Hidden Penalties (Highlight with warning flags ⚠️).
3. Important Dates & Financial Commitments.

Contract Text:
{contract_text}"""

        # ৫০৩ এরর এড়াতে ব্যাকআপ মডেলের তালিকা
        models_to_try = ['gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-1.5-pro']

        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                return response.text  # সফল হলে আউটপুট রিটার্ন করবে
            except Exception as model_err:
                # ৫০৩ বা হাই ডিমান্ড এরর পেলে পরের মডেলে ট্রাই করবে
                if "503" in str(model_err) or "high demand" in str(model_err).lower():
                    continue
                else:
                    return f"AI প্রসেসিংয়ে সমস্যা হয়েছে: {str(model_err)}"

        return "⚠️ গুগলের AI সার্ভার বর্তমানে অত্যন্ত ব্যস্ত আছে। অনুগ্রহ করে কয়েক সেকেন্ড পর আবার চেষ্টা করুন।"

    except Exception as e:
        return f"এপিআই ক্লায়েন্ট তৈরিতে সমস্যা হয়েছে: {str(e)}"

# --- ৬. মূল অ্যাপের লজিক (Limit Check & Subscription) ---
if not st.session_state.user_email:
    st.info("👈 সার্ভিসটি ব্যবহার করতে দয়া করে সাইডবার থেকে **Login** অথবা **Sign Up** করুন।")
else:
    current_user = st.session_state.user_email
    is_admin = (current_user == ADMIN_EMAIL)
    usage_count = get_user_usage_count(current_user)
    
    # ফ্রি লিমিট চেক (সাধারণ ইউজারের জন্য ১টি ফাইল ফ্রি)
    if not is_admin and usage_count >= 1:
        st.warning("⚠️ আপনার ১টি ফ্রি ফাইল ব্যবহারের কোটা শেষ হয়ে গেছে!")
        st.error("আনলিমিটেড চুক্তিপত্র বিশ্লেষণ করতে দয়া করে প্রিমিয়াম সাবস্ক্রিপশন কিনুন।")
        
        st.markdown("---")
        st.subheader("⭐ Upgrade to Pro")
        st.write("সাবস্ক্রাইব করলে পাবেন আনলিমিটেড এনালাইসিস এবং প্রফেশনাল সাপোর্ট।")
        st.link_button("💳 Subscribe Now ($9/month)", STRIPE_LINK, use_container_width=True)
        
    else:
        # লিমিট থাকলে অথবা Admin হলে এই সেকশন দেখাবে
        if not is_admin:
            st.info(f"📊 আপনি এখন পর্যন্ত **{usage_count}/1** টি ফ্রি ফাইল ব্যবহার করেছেন।")
        
        uploaded_file = st.file_uploader("আপনার চুক্তিপত্রের PDF ফাইল আপলোড করুন", type=["pdf"])

        if uploaded_file is not None:
            with st.spinner("PDF পড়া হচ্ছে..."):
                contract_text = extract_text_from_pdf(uploaded_file)
                st.info(f"ফাইল সফলভাবে পড়া হয়েছে ({len(contract_text)} ক্যারেক্টার)")

            if st.button("AI দিয়ে বিশ্লেষণ করুন 🚀"):
                with st.spinner("Gemini AI চুক্তিপত্রটি বিশ্লেষণ করছে, কিছু সময় অপেক্ষা করুন..."):
                    analysis_result = analyze_contract_with_gemini(contract_text, GEMINI_KEY)
                    
                    # Supabase-এ ফাইল এনালাইসিসের তথ্য সেভ করা
                    log_user_activity(current_user, uploaded_file.name)
                    
                    st.markdown("---")
                    st.subheader("📊 анализа/বিশ্লেষণের ফলাফল:")
                    st.write(analysis_result)
                    
                    st.download_button(
                        label="রিপোর্ট ডাউনলোড করুন",
                        data=analysis_result,
                        file_name="Contract_Analysis_Report.txt",
                        mime="text/plain"
                    )
