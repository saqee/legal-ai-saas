import streamlit as st
import pypdf
import stripe
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
STRIPE_SECRET_KEY = st.secrets.get("STRIPE_SECRET_KEY", "")

stripe.api_key = STRIPE_SECRET_KEY

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_supabase()

st.title("📜 AI Contract & Legal Document Analyzer")

# --- ২. সেশন ও ইউআরএল প্যারামিটার উদ্ধার ---
query_params = st.query_params

# ইউআরএল-এ ইমেইল থাকলে তা সরাসরি সেশনে সেভ করা (সেশন লস্ট ফিক্স)
# NOTE: এটা শুধু login/signup সেশন রিকভারির জন্য — payment/Pro স্ট্যাটাসের জন্য কখনো ব্যবহার হবে না।
url_email = query_params.get("session_email")
if url_email:
    st.session_state.user_email = url_email.strip().lower()

current_user = st.session_state.get("user_email")

# --- ৩. ডাটাবেস আপডেট হেল্পার ফাংশন ---
def make_user_pro_in_db(email):
    try:
        if not email:
            st.session_state["_debug_last_error"] = "make_user_pro_in_db: email empty ছিল"
            return False
        email = email.strip().lower()
        res = supabase.table("user_analyses").update({"is_subscribed": True}).eq("user_email", email).execute()
        # Supabase update() কোনো matching row না পেলেও error দেয় না, খালি res.data = []
        if not res.data:
            st.session_state["_debug_last_error"] = (
                f"make_user_pro_in_db: '{email}' ইমেইলে user_analyses টেবিলে কোনো row ম্যাচ করেনি, "
                f"তাই update হয়নি (কিন্তু error ও আসেনি)।"
            )
            return False
        return True
    except Exception as e:
        st.session_state["_debug_last_error"] = f"make_user_pro_in_db exception: {e}"
        return False

def is_session_already_processed(session_id):
    """একই Stripe session_id দিয়ে বারবার Pro-activation/log আটকাতে।"""
    try:
        res = supabase.table("processed_payments").select("session_id").eq("session_id", session_id).execute()
        return len(res.data) > 0
    except Exception as e:
        st.session_state["_debug_last_error"] = f"is_session_already_processed exception (টেবিল আছে তো?): {e}"
        # ফেইল-সেফ: চেক না করতে পারলে ধরে নিই এখনো প্রসেস হয়নি, কিন্তু নিচে ইনসার্ট আবার ট্রাই হবে
        return False

def mark_session_processed(session_id, email):
    try:
        supabase.table("processed_payments").insert({"session_id": session_id, "user_email": email}).execute()
    except Exception as e:
        st.session_state["_debug_last_error"] = f"mark_session_processed exception: {e}"

# --- ৪. পেমেন্ট শেষে রিডাইরেক্ট লজিক (SERVER-SIDE VERIFIED) ---
# গুরুত্বপূর্ণ পরিবর্তন: এখন আর URL-এর ?payment=success&user_email=... কে trust করা হয় না।
# Stripe checkout success_url এ শুধু session_id পাঠানো হবে:
#   https://yourapp.streamlit.app/?payment=success&session_id={CHECKOUT_SESSION_ID}
# তারপর সেই session_id Stripe API দিয়ে সার্ভার-সাইডে verify করা হয়, এবং email/payment_status
# Stripe-এর নিজস্ব response থেকে নেওয়া হয় — URL parameter থেকে না।
if query_params.get("payment") == "success":
    session_id = query_params.get("session_id")

    if not session_id:
        st.error("⚠️ Payment session সনাক্ত করা যায়নি। সমস্যা হলে সাপোর্টে যোগাযোগ করুন।")
    elif not STRIPE_SECRET_KEY:
        st.error("⚠️ সার্ভার কনফিগারেশন ত্রুটি (Stripe secret key missing)।")
    elif is_session_already_processed(session_id):
        # এই সেশন আগেই প্রসেস হয়ে গেছে — আবার Pro করার/লগ করার দরকার নেই।
        pass
    else:
        try:
            checkout_session = stripe.checkout.Session.retrieve(session_id)

            if checkout_session.payment_status == "paid":
                verified_email = (checkout_session.customer_details.email or "").strip().lower()

                if verified_email:
                    # যদি লগইন করা user আর যে email দিয়ে Stripe checkout করা হয়েছে তা আলাদা হয়,
                    # তাহলে DB-তে ঠিক row-টাই আপডেট হয় কিন্তু বর্তমানে লগইন থাকা user
                    # (current_user) সেটা এখনই Pro হিসেবে দেখবে না।
                    if current_user and current_user != verified_email:
                        st.warning(
                            f"⚠️ আপনি লগইন করেছেন **{current_user}** দিয়ে, কিন্তু Stripe checkout করেছেন "
                            f"**{verified_email}** দিয়ে। এই দুই ইমেইল আলাদা হওয়ায় '{verified_email}' "
                            f"অ্যাকাউন্টটি Pro হবে, '{current_user}' না। একই ইমেইল দিয়ে লগইন ও চেকআউট করুন।"
                        )

                    st.session_state.user_email = verified_email
                    current_user = verified_email

                    if make_user_pro_in_db(verified_email):
                        mark_session_processed(session_id, verified_email)
                        st.toast("🎉 প্রিমিয়াম সাবস্ক্রিপশন সফলভাবে অ্যাক্টিভেট হয়েছে!", icon="⭐")
                        st.rerun()
                    else:
                        st.error(f"⚠️ '{verified_email}' কে Pro বানানো যায়নি। নিচে debug details দেখুন।")
                else:
                    st.error("⚠️ Stripe থেকে ইমেইল পাওয়া যায়নি (Checkout session-এ email collect করা আছে তো?)।")
            else:
                st.warning(f"⚠️ পেমেন্ট এখনো সম্পন্ন হয়নি বা ব্যর্থ হয়েছে (status: {checkout_session.payment_status})।")
        except Exception as e:
            st.session_state["_debug_last_error"] = f"stripe.checkout.Session.retrieve exception: {e}"
            st.error(f"⚠️ Payment verify করা যায়নি: {str(e)}")

    if st.session_state.get("_debug_last_error"):
        with st.expander("🔧 Debug details (dev only — পরে সরিয়ে ফেলুন)"):
            st.code(st.session_state["_debug_last_error"])

# --- ৫. অন্যান্য হেল্পার ফাংশন ---
def check_user_subscription_status(email):
    if not email:
        return False
    try:
        res = supabase.table("user_analyses").select("is_subscribed").eq("user_email", email).eq("is_subscribed", True).execute()
        return len(res.data) > 0
    except Exception as e:
        print(f"Sub check error: {e}")
        return False

def get_user_usage_count(email):
    if not email:
        return 0
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

# --- ৬. সাইডবার লগইন সিস্টেম ---
st.sidebar.title("👤 User Account")

if not current_user:
    auth_mode = st.sidebar.radio("Choose Action", ["Login", "Sign Up"])
    email = st.sidebar.text_input("Email")
    password = st.sidebar.text_input("Password", type="password")

    if auth_mode == "Sign Up":
        if st.sidebar.button("Create Account"):
            try:
                res = supabase.auth.sign_up({"email": email, "password": password})
                user_e = email.strip().lower()
                st.session_state.user_email = user_e
                st.query_params["session_email"] = user_e
                st.sidebar.success("অ্যাকাউন্ট তৈরি হয়েছে!")
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Error: {str(e)}")

    elif auth_mode == "Login":
        if st.sidebar.button("Log In"):
            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                user_e = res.user.email.strip().lower()
                st.session_state.user_email = user_e
                st.query_params["session_email"] = user_e
                st.sidebar.success(f"Welcome, {user_e}")
                st.rerun()
            except Exception as e:
                st.sidebar.error("ইমেইল বা পাসওয়ার্ড ভুল হয়েছে।")
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

# --- ৭. Gemini AI Logic ---
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

# --- ৮. মূল অ্যাপের লজিক ---
if not st.session_state.get("user_email"):
    st.info("👈 সার্ভিসটি ব্যবহার করতে সাইডবার থেকে **Login** অথবা **Sign Up** করুন।")
else:
    current_user = st.session_state.user_email
    is_admin = (current_user == ADMIN_EMAIL)
    is_subscribed = check_user_subscription_status(current_user)
    usage_count = get_user_usage_count(current_user)

    if not is_admin and not is_subscribed and usage_count >= 1:
        st.warning("⚠️ আপনার ১টি ফ্রি ফাইল ব্যবহারের কোটা শেষ হয়ে গেছে!")
        st.error("আনলিমিটেড চুক্তিপত্র বিশ্লেষণ করতে প্রিমিয়াম সাবস্ক্রিপশন সম্পন্ন করুন।")

        st.markdown("---")
        st.subheader("⭐ Upgrade to Pro ($9/month)")

        stripe_url_with_user = f"{STRIPE_LINK}?prefilled_email={current_user}"
        st.link_button("💳 Pay via Stripe ($9)", stripe_url_with_user, use_container_width=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.caption("পেমেন্ট সফল হলে Stripe নিজেই আপনাকে ফিরিয়ে এনে অ্যাকাউন্ট Pro করে দেবে। "
                   "যদি স্বয়ংক্রিয়ভাবে না হয়, একটু পর পেজ রিফ্রেশ করুন — নিচের বাটনে ম্যানুয়ালি Pro করা যাবে না, "
                   "যাচাইয়ের জন্য পেমেন্ট রেকর্ড লাগবে।")

    else:
        if not is_admin and not is_subscribed:
            st.info(f"📊 আপনি **{usage_count}/1** টি ফ্রি ফাইল ব্যবহার করেছেন।")
        elif is_subscribed:
            st.success("🎉 আপনি একজন Pro গ্রাহক (Unlimited Access)!")

        uploaded_file = st.file_uploader("আপনার চুক্তিপত্রের PDF ফাইল আপলোড করুন", type=["pdf"])

        if uploaded_file is not None:
            with st.spinner("PDF পড়া হচ্ছে..."):
                contract_text = extract_text_from_pdf(uploaded_file)
                st.info(f"ফাইল সফলভাবে পড়া হয়েছে ({len(contract_text)} ক্যারেক্টার)")

            if st.button("AI দিয়ে বিশ্লেষণ করুন 🚀"):
                with st.spinner("Gemini AI বিশ্লেষণ করছে..."):
                    analysis_result = analyze_contract_with_gemini(contract_text, GEMINI_KEY)
                    log_user_activity(current_user, uploaded_file.name)

                    st.markdown("---")
                    st.subheader("📊 বিশ্লেষণের ফলাফল:")
                    st.write(analysis_result)

                    st.download_button(
                        label="রিপোর্ট ডাউনলোড করুন",
                        data=analysis_result,
                        file_name="Contract_Analysis_Report.txt",
                        mime="text/plain"
                    )
