import streamlit as st
import pypdf
from google import genai

# --- ১. পেজ কনফিগারেশন ---
st.set_page_config(page_title="Legal AI - Contract Analyzer", page_icon="📜", layout="wide")

st.title("📜 AI Contract & Legal Document Analyzer")
st.write("আপনার যেকোনো চুক্তিপত্র বা ডকুমেন্ট আপলোড করুন এবং AI থেকে তাৎক্ষণিক মূল সারসংক্ষেপ ও ঝুঁকিপূর্ণ শর্তগুলো জেনে নিন।")

# Secrets থেকে তথ্য লোড
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")
STRIPE_LINK = st.secrets.get("stripe_link", "#")

# --- সাইডবারে প্রিমিয়াম সাবস্ক্রিপশন ব্যানার ---
st.sidebar.title("⭐ Upgrade to Pro")
st.sidebar.write("মাসে আনলিমিটেড চুক্তিপত্র বিশ্লেষণ করতে সাবস্ক্রাইব করুন।")
st.sidebar.link_button("💳 Subscribe Now ($9/month)", STRIPE_LINK)

# --- ২. PDF ফাইল থেকে টেক্সট এক্সট্রাক্ট ---
def extract_text_from_pdf(pdf_file):
    reader = pypdf.PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text

# --- ৩. Gemini AI দিয়ে বিশ্লেষণ ---
def analyze_contract_with_gemini(contract_text, api_key):
    try:
        client = genai.Client(api_key=api_key)
        prompt = f"""You are an expert legal advisor. Analyze the following contract document carefully.
Provide:
1. Executive Summary (3 bullet points).
2. Key Legal Risks, Hidden Penalties, or Unfair Clauses (Highlight them clearly with warning flags ⚠️).
3. Important Dates & Financial Commitments.

Contract Text:
{contract_text}"""

       # ট্রাই করার জন্য প্রাইমারি ও ব্যাকআপ মডেলগুলোর তালিকা
    models_to_try = ['gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-1.5-pro']

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            return response.text  # সফল হলে রেজাল্ট রিটার্ন করবে
        except Exception as e:
            # যদি ৫০৩ বা হাই ডিমান্ড এরর দেয়, তবে পরের মডেলে সুইচ করবে
            if "503" in str(e) or "high demand" in str(e).lower():
                continue 
            else:
                return f"AI প্রসেসিংয়ে সমস্যা হয়েছে: {str(e)}"
                
    return "⚠️ গুগলের AI সার্ভার বর্তমানে অত্যন্ত ব্যস্ত আছে। অনুগ্রহ করে কয়েক সেকেন্ড পর আবার চেষ্টা করুন।"
# --- ৪. মূল অ্যাপ UI ---
if not GEMINI_KEY:
    st.warning("⚠️ Streamlit Cloud Secrets-এ `GEMINI_API_KEY` সেট করা নেই।")
else:
    uploaded_file = st.file_uploader("আপনার চুক্তিপত্রের PDF ফাইল আপলোড করুন", type=["pdf"])

    if uploaded_file is not None:
        with st.spinner("PDF পড়া হচ্ছে..."):
            contract_text = extract_text_from_pdf(uploaded_file)
            st.info(f"ফাইল সফলভাবে পড়া হয়েছে ({len(contract_text)} ক্যারেক্টার)")

        if st.button("AI দিয়ে বিশ্লেষণ করুন 🚀"):
            with st.spinner("Gemini AI চুক্তিপত্রটি বিশ্লেষণ করছে, কিছু সময় অপেক্ষা করুন..."):
                analysis_result = analyze_contract_with_gemini(contract_text, GEMINI_KEY)
                
                st.markdown("---")
                st.subheader("📊 анализа/বিশ্লেষণের ফলাফল:")
                st.write(analysis_result)
                
                st.download_button(
                    label="রিপোর্ট ডাউনলোড করুন",
                    data=analysis_result,
                    file_name="Contract_Analysis_Report.txt",
                    mime="text/plain"
                )
