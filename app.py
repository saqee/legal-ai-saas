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

# --- ২. সেশন পুনরুদ্ধার (URL Query Parameter Sync) ---
query_params = st.query_params

# যদি URL-এ user অথবা session_email থাকে, সেটা দিয়ে সেশন অটো-লগইন করবে
if "user_email" not in st.session_state or not st.session_state.user_email:
    if "user" in query_params:
        st.session_state.user_email = query_params["user"].strip().lower()
    elif "session_email" in query_params:
        st.session_state.user_email = query_params["session_email"].strip().lower()

current_user = st.session_state.get("user_email")

# --- ৩. পেমেন্ট সাকসেস আপডেট (UPDATE DB) ---
if query_params.get("payment") == "success" and current_user:
    try:
        # ডাটাবেসে is_subscribed = True করা
        supabase.table("user_analyses").update({"is_subscribed": True}).eq("user_email", current_user).execute()
        st.success("🎉 আপনার প্রিমিয়াম সাবস্ক্রিপশন সফলভাবে অ্যাক্টিভেট হয়েছে!")
    except Exception as e:
        print(f"Subscription Update Error: {e}")

# --- ৪. হেল্পার ফাংশনসমূহ ---
def check_user_subscription_status(email):
    try:
        res = supabase.table("user_analyses").select("is_subscribed").eq("user_email", email).eq("is_subscribed", True).execute()
        return len(res.data) > 0
    except Exception as e:
        print(f"Sub check error: {e}")
        return False

def get_user_usage_count(email):
    try:
        response = supabase.table("user_analyses").select("id", count="exact").eq("user_email", email).execute()
        return response.count
    except Exception as e:
        print(f"Usage count error: {e}")
        return 0

def log_user_activity(email, file_name):
    try:
        data = {"user_email": email, "file_name": file_name}
        supabase.table("user_analyses").insert(data).execute()
    except Exception as e:
        print(f"Supabase logging failed: {e}")

# --- ৫. ইউজার লগইন / রেজিস্ট্রেশন (Sidebar) ---
st.sidebar.title("👤 User Account")

if not current_user:
    auth_mode = st.sidebar.radio("Choose Action", ["Login", "Sign Up"])
    email = st.sidebar.text_input("Email")
    password = st.sidebar.text_input("Password", type="password")

    if auth_mode == "Sign Up":
        if st.sidebar.button("Create Account"):
            try:
                res = supabase.auth.sign_up({"email": email, "password": password})
                st.session_state.user_email = email.strip().lower()
                st.query_params["session_email"] = email.strip().lower()
                st.sidebar.success("অ্যাকাউন্ট তৈরি হয়েছে!")
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Error: {str(e)}")

    elif auth_mode == "Login":
        if st.sidebar.button("Log In"):
            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.user_email = res.user.email.strip().lower()
                st.query_params["session_email"] = res.user.email.strip().lower()
                st.sidebar.success(f"Welcome, {st.session_state.user_email}")
                st.rerun()
            except Exception as e:
                st.sidebar.error("ইমেইল বা পাসওয়ার্ড ভুল হয়েছে।")
else:
    is_admin = (current_user == ADMIN_EMAIL)
    is_subscribed = check_user_subscription_status(current_user)
    
    if is_admin:
        st.sidebar.success("👑 Admin Account (Unlimited)")
    elif is_subscribed:
        st.sidebar.success("⭐ Pro Subscribed Member")
    else:
        st.sidebar.write(f"Logged in as: **{current_user}**")
        
    if st.sidebar.button("Log Out"):
        st.session_state.user_email = None
        st.query_params.clear()
        st.rerun()

# --- ৬. Gemini AI Logic (With Multiple Model Fallback) ---
def extract_text_from_pdf(pdf_file):
    reader = pypdf.PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text

def analyze_contract_with_gemini(contract_text, api_key):
    try:
        client = genai.Client(api_key=api_key)
        prompt = f"""You are an expert legal advisor. Analyze the contract:
1. Executive Summary (3 bullet points)
2. Key Legal Risks & Hidden Penalties (⚠️)
3. Important Dates & Financial Commitments

Contract Text: {contract_text}"""

        models_to_try = ['gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-1.5-pro']
        for model_name in models_to_try:
            try:
                response = client.models.generate_content(model=model_name, contents=prompt)
                return response.text
            except Exception as model_err:
                if "503" in str(model_err) or "high demand" in str(model_err).lower():
                    continue
                else:
                    return f"AI Error: {str(model_err)}"
        return "⚠️ গুগলের AI সার্ভার ব্যস্ত, কিছুক্ষণ পর আবার চেষ্টা করুন।"
    except Exception as e:
        return f"API Client Error: {str(e)}"

# --- ৭. মূল অ্যাপের লজিক ---
if not st.session_state.get("user_email"):
    st.info("👈 সার্ভিসটি ব্যবহার করতে সাইডবার থেকে **Login** অথবা **Sign Up** করুন।")
else:
    current_user = st.session_state.user_email
    is_admin = (current_user == ADMIN_EMAIL)
    is_subscribed = check_user_subscription_status(current_user)
    usage_count = get_user_usage_count(current_user)
    
    # ফ্রি লিমিট চেক
    if not is_admin and not is_subscribed and usage_count >= 1:
        st.warning("⚠️ আপনার ১টি ফ্রি ফাইল ব্যবহারের কোটা শেষ হয়ে গেছে!")
        st.error("আনলিমিটেড চুক্তিপত্র বিশ্লেষণ করতে প্রিমিয়াম সাবস্ক্রিপশন লিঙ্ক থেকে পেমেন্ট সম্পন্ন করুন।")
        
        st.markdown("---")
        st.subheader("⭐ Upgrade to Pro")
        st.write("সাবস্ক্রাইব করলে পাবেন আনলিমিটেড এনালাইসিস।")
        
        # ডায়নামিক স্ট্রাইপ লিঙ্ক: ইউজারের ইমেইল প্রি-ফিল করা
        stripe_dynamic_url = f"{STRIPE_LINK}?prefilled_email={current_user}"
        st.link_button("💳 Subscribe Now ($9/month)", stripe_dynamic_url, use_container_width=True)
        
    else:
        if not is_admin and not is_subscribed:
            st.info(f"📊 আপনি **{usage_count}/1** টি ফ্রি ফাইল ব্যবহার করেছেন।")
        elif is_subscribed:
            st.success("🎉 আপনি একজন Pro গ্রাহক (Unlimited Access)!")
            
        uploaded_file = st.file_uploader("আপনার চুক্তিপত্রের PDF ফাইল আপলোড করুন", type=["pdf"])

        if uploaded_file is not None:
            with st.spinner("PDF পড়া হচ্ছে..."):
                contract_text = extract_text_from_pdf(uploaded_file)
                st.info(f"ফাইল সফলভাবে পড়া হয়েছে ({len(contract_text)} ক্যারেক্টার)")

            if st.button("AI দিয়ে বিশ্লেষণ করুন 🚀"):
                with st.spinner("Gemini AI বিশ্লেষণ করছে..."):
                    analysis_result = analyze_contract_with_gemini(contract_text, GEMINI_KEY)
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
