import streamlit as st
import requests
import pypdf
from st_paywall import add_auth

# --- ১. পেজ কনফিগারেশন ---
st.set_page_config(page_title="Legal AI - Contract Analyzer", page_icon="📜", layout="wide")

st.title("📜 AI Contract & Legal Document Analyzer")
st.write("আপনার যেকোনো চুক্তিপত্র বা ডকুমেন্ট আপলোড করুন এবং AI থেকে তাৎক্ষণিক মূল সারসংক্ষেপ ও ঝুঁকিপূর্ণ শর্তগুলো জেনে নিন।")

# --- ২. সাবস্ক্রিপশন ও লগইন চেক (Paywall) ---
# st-paywall অটোমেটিক Google Login এবং Stripe Payment চেক পরিচালনা করবে
# --- ২. সাবস্ক্রিপশন ও লগইন চেক (Paywall) ---
# st-paywall অটোমেটিক Google/Email Login এবং Stripe Payment চেক পরিচালনা করবে
require_auth = add_auth()

# ইউজার পেমেন্ট সম্পন্ন করলে নিচের কোডগুলো এক্সিকিউট হবে
if require_auth:
    st.success("স্বাগতম! আপনি প্রিমিয়াম ইউজার হিসেবে লগইন আছেন।")

    # --- ৩. PDF ফাইল থেকে টেক্সট এক্সট্রাক্ট করার ফাংশন ---
    def extract_text_from_pdf(pdf_file):
        reader = pypdf.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text

    # --- ৪. Hugging Face AI API কল করা ---
    def analyze_contract_with_ai(contract_text):
        API_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2"
        headers = {"Authorization": f"Bearer {st.secrets['HF_API_TOKEN']}"}
        
        # প্রম্পট ইঞ্জিনিয়ারিং
        prompt = f"""<s>[INST] You are an expert legal advisor. Analyze the following contract document carefully.
Provide:
1. Executive Summary (3 bullet points).
2. Key Risks, Hidden Penalties, or Unfair Clauses (Highlight them clearly with warning flags).
3. Important Dates & Financial Commitments.

Contract Text:
{contract_text[:3000]} [/INST]"""  # টোকেন লিমিটের জন্য প্রথম ৩০০০ ক্যারেক্টার পাঠানো হচ্ছে

        response = requests.post(API_URL, headers=headers, json={"inputs": prompt, "parameters": {"max_new_tokens": 500}})
        
        if response.status_code == 200:
            result = response.json()
            # মডেলের আউটপুট ফিল্টার করা
            raw_text = result[0]['generated_text']
            return raw_text.split("[/INST]")[-1]
        else:
            return "AI প্রসেসিংয়ে সমস্যা হয়েছে। অনুগ্রহ করে আবার চেষ্টা করুন।"

    # --- ৫. ফাইল আপলোড UI ---
    uploaded_file = st.file_uploader("আপনার চুক্তিপত্রের PDF ফাইল আপলোড করুন", type=["pdf"])

    if uploaded_file is not None:
        with st.spinner("PDF পড়া হচ্ছে..."):
            contract_text = extract_text_from_pdf(uploaded_file)
            st.info(f"ফাইল সফলভাবে পড়া হয়েছে ({len(contract_text)} ক্যারেক্টার)")

        if st.button("AI দিয়ে বিশ্লেষণ করুন 🚀"):
            with st.spinner("AI চুক্তিপত্রটি বিশ্লেষণ করছে, কিছু সময় অপেক্ষা করুন..."):
                analysis_result = analyze_contract_with_ai(contract_text)
                
                st.markdown("---")
                st.subheader("📊 বিশ্লেষণের ফলাফল:")
                st.write(analysis_result)
                
                # ফলাফল ডাউনলোড বাটন
                st.download_button(
                    label="রিপোর্ট ডাউনলোড করুন (Text)",
                    data=analysis_result,
                    file_name="Contract_Analysis_Report.txt",
                    mime="text/plain"
                )