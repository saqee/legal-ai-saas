import streamlit as st
import pypdf
from google import genai

# --- ১. পেজ কনফিগারেশন ---
st.set_page_config(page_title="Legal AI - Contract Analyzer", page_icon="📜", layout="wide")

st.title("📜 AI Contract & Legal Document Analyzer")
st.write("আপনার যেকোনো চুক্তিপত্র বা ডকুমেন্ট আপলোড করুন এবং AI থেকে তাৎক্ষণিক মূল সারসংক্ষেপ ও ঝুঁকিপূর্ণ শর্তগুলো জেনে নিন।")

# Secrets থেকে Gemini API Key লোড করা
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

# --- ২. PDF ফাইল থেকে টেক্সট এক্সট্রাক্ট করার ফাংশন ---
def extract_text_from_pdf(pdf_file):
    reader = pypdf.PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text

# --- ৩. Gemini AI দিয়ে বিশ্লেষণ করা ---
def analyze_contract_with_gemini(contract_text, api_key):
    try:
        # Google GenAI Client ক্রিয়েট করা
        client = genai.Client(api_key=api_key)
        
        prompt = f"""You are an expert legal advisor. Analyze the following contract document carefully.
Provide:
1. Executive Summary (3 bullet points).
2. Key Legal Risks, Hidden Penalties, or Unfair Clauses (Highlight them clearly with warning flags ⚠️).
3. Important Dates & Financial Commitments.

Contract Text:
{contract_text}"""

        # Gemini Flash মডেল কল করা (খুবই দ্রুত ও ফ্রি)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text
    except Exception as e:
        return f"AI প্রসেসিংয়ে সমস্যা হয়েছে: {str(e)}"

# --- ৪. ফাইল আপলোড UI ---
if not GEMINI_KEY:
    st.warning("⚠️ `.streamlit/secrets.toml` ফাইলে `GEMINI_API_KEY` পাওয়া যায়নি। Google AI Studio থেকে ফ্রি কী বানিয়ে বসিয়ে দিন।")
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
                st.subheader("📊 বিশ্লেষণের ফলাফল:")
                st.write(analysis_result)
                
                # রিপোর্ট ডাউনলোড বাটন
                st.download_button(
                    label="রিপোর্ট ডাউনলোড করুন",
                    data=analysis_result,
                    file_name="Contract_Analysis_Report.txt",
                    mime="text/plain"
                )