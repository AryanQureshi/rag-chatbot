import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
import google.generativeai as genai
from langchain_core.prompts import PromptTemplate
from langchain.chains import RetrievalQA
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain_community.vectorstores import FAISS
from datetime import datetime
from fpdf import FPDF
import io
import textwrap
from typing import Literal
from components.email_ui import show_email_ui

# Import authentication modules
from auth.authenticator import FirebaseAuthenticator
from auth.chat_history import ChatHistoryManager
from auth.ui import auth_page, user_sidebar, chat_history_sidebar, sync_chat_message, load_user_preferences, save_user_preferences

# Import email service
from services.email_service import EmailService

# Emergency authority email mapping
EMERGENCY_AUTHORITIES = {
    "Flood": "flood.authority@example.com",
    "Earthquake": "earthquake.response@example.com",
    "Fire": "fire.department@example.com",
    "Medical": "medical.emergency@example.com",
    "General": "general.emergency@example.com"
}

# Initialize session state for chat history and language preferences
if "messages" not in st.session_state:
    st.session_state.messages = []
if "input_language" not in st.session_state:
    st.session_state.input_language = "English"
if "output_language" not in st.session_state:
    st.session_state.output_language = "English"

def get_language_prompt(output_lang: Literal["English", "Sindhi", "Urdu"]) -> str:
    """Get the language-specific prompt instruction."""
    if output_lang == "Sindhi":
        return """سنڌي ۾ جواب ڏيو. مهرباني ڪري صاف ۽ سادي سنڌي استعمال ڪريو، اردو لفظن کان پاسو ڪريو. جواب تفصيلي ۽ سمجهه ۾ اچڻ جوڳو هجڻ گهرجي."""
    elif output_lang == "Urdu":
        return """اردو میں جواب دیں۔ براہ کرم واضح اور سادہ اردو استعمال کریں۔ جواب تفصیلی اور سمجھنے کے قابل ہونا چاہیے۔"""
    return "Respond in English using clear and professional language."

def create_chat_pdf():
    """Generate a PDF file of chat history with proper formatting."""
    try:
        # Create PDF object with UTF-8 support
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        
        # Title
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, "Disaster Management Chatbot - Conversation Log", 0, 1, 'C')
        pdf.ln(10)
        
        # Chat messages
        for message in st.session_state.messages:
            # Role header
            role = "Bot" if message["role"] == "assistant" else "User"
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 10, role + ":", 0, 1)
            
            # Message content
            pdf.set_font("Arial", "", 11)
            content = message["content"]
            
            # Handle Sindhi text
            try:
                # Try encoding as latin-1 first
                content.encode('latin-1')
                # If successful, write normally
                lines = textwrap.wrap(content, width=85)
                for line in lines:
                    pdf.cell(0, 7, line, 0, 1)
            except UnicodeEncodeError:
                # For Sindhi text, write "[Sindhi]" followed by transliterated version
                pdf.cell(0, 7, "[Sindhi Message]", 0, 1)
                # Try to write a transliterated version if possible
                try:
                    ascii_text = content.encode('ascii', 'replace').decode('ascii')
                    lines = textwrap.wrap(ascii_text, width=85)
                    for line in lines:
                        pdf.cell(0, 7, line, 0, 1)
                except:
                    pass
            
            pdf.ln(5)
        
        # Output PDF
        return pdf.output(dest='S').encode('latin-1', errors='replace')
        
    except Exception as e:
        st.error(f"Error generating PDF: {str(e)}")
        return None

def create_chat_text():
    """Generate a formatted text file of chat history."""
    try:
        output = []
        output.append("Disaster Management Chatbot - Conversation Log")
        output.append("=" * 50)
        output.append("")  # Empty line
        
        for message in st.session_state.messages:
            role = "Bot" if message["role"] == "assistant" else "User"
            output.append(f"{role}:")
            output.append(message['content'])
            output.append("-" * 30)
            output.append("")  # Empty line
        
        # Join with newlines and encode as UTF-8
        return "\n".join(output).encode('utf-8')
    except Exception as e:
        st.error(f"Error generating text file: {str(e)}")
        return None

def is_general_chat(query):
    """Check if the query is a general chat or greeting."""
    # Make patterns more specific to avoid false positives
    general_phrases = [
        '^hi$', '^hello$', '^hey$', 
        '^good morning$', '^good afternoon$', '^good evening$',
        '^how are you$', '^what\'s up$', '^nice to meet you$', 
        '^thanks$', '^thank you$', '^bye$', '^goodbye$', '^see you$',
        '^who are you$', '^what can you do$'
    ]
    
    query_lower = query.lower().strip()
    # Only match if these are standalone phrases
    return any(query_lower == phrase.strip('^$') for phrase in general_phrases)


def get_general_response(query):
    """
    Generate appropriate responses for general chat, including specific hardcoded Q&A.
    Checks specific Q&A and greetings first, then falls back to general info.
    """
    query_normalized = normalize_query(query) # Normalize the input query

    # Ensure session state has the language, default to English if not set
    if 'output_language' not in st.session_state:
        st.session_state.output_language = "English"
    output_lang = st.session_state.output_language

    if output_lang == "Sindhi":
        # --- Greetings and Common Phrases ---
        if any(greeting in query_normalized for greeting in ['hi', 'hello', 'hey', 'هيلو', 'سلام']):
            return "السلام عليڪم! مان توهان جو آفتن جي انتظام جو مددگار آهيان. مان توهان جي ڪهڙي مدد ڪري سگهان ٿو؟"
        elif any(time in query_normalized for time in ['good morning', 'good afternoon', 'good evening']):
            return "توهان جو مهرباني! مان توهان جي آفتن جي انتظام جي سوالن ۾ مدد ڪرڻ لاءِ حاضر آهيان."
        elif 'how are you' in query_normalized or 'ڪيئن آهيو' in query_normalized:
            return "مان ٺيڪ آهيان، توهان جي پڇڻ جو مهرباني! مان آفتن جي انتظام جي معلومات ڏيڻ لاءِ تيار آهيان."
        elif 'thank' in query_normalized or 'مهرباني' in query_normalized:
            return "توهان جو مهرباني! آفتن جي انتظام بابت ڪو به سوال پڇڻ لاءِ آزاد محسوس ڪريو."
        elif 'bye' in query_normalized or 'goodbye' in query_normalized or 'خدا حافظ' in query_normalized:
            return "خدا حافظ! جيڪڏهن توهان کي آفتن جي انتظام بابت وڌيڪ سوال هجن ته پوءِ ضرور پڇو."
        elif 'who are you' in query_normalized or 'تون ڪير آهين' in query_normalized:
            return "مان هڪ خاص آفتن جي انتظام جو مددگار آهيان. مان آفتن جي انتظام، حفاظتي اپاءَ ۽ آفتن جي جواب جي حڪمت عملي بابت معلومات ڏئي سگهان ٿو."

        # --- Specific Q&A (Hardcoded from JSON) ---
        elif query_normalized == normalize_query("زلزلي دوران مون کي ڇا ڪرڻ گهرجي؟"):
             return "زمين تي ڪريو، پناهه وٺو، ۽ لوڏا بند ٿيڻ تائين انتظار ڪريو."
        elif query_normalized == normalize_query("گرمي جي لهر دوران مان ڪيئن محفوظ رهي سگھان ٿو؟"):
             return "هائيڊريٽ رهندا، سڌو سنئون سج کان بچندا، ۽ وڌ ۾ وڌ گرمي جي ڪلاڪن دوران اندر رهندا."
        elif query_normalized == normalize_query("جيڪڏهن مون ڏٺو ته ٻيلهه جي باهه ويجهو اچي رهي آهي ته مون کي ڇا ڪرڻ گهرجي؟"):
             return "جيڪڏهن هدايت ڏني وڃي ته فوري طور تي نڪتو ۽ باهه کان پري محفوظ علائقي ڏانهن هليو وڃو."
        elif query_normalized == normalize_query("هڪ سامونڊي طوفان لاءِ مان ڪيئن تياري ڪري سگھان ٿو؟"):
             return "ٻاهران شين کي محفوظ ڪريو، ونڊوز کي مضبوط ڪريو، ۽ جيڪڏهن هدايت ڏني وڃي ته نيڪالي جا حڪم مڃيو."
        elif query_normalized == normalize_query("منهنجي ايمرجنسي کٽ ۾ ڇا شامل ٿيڻ گهرجي؟"):
             return "پاڻي، غير خراب ٿيڻ وارو کاڌو، ٽارچ، بيٽرين، پهرين مدد جو کٽ، ۽ ضروري دوائون."
        elif query_normalized == normalize_query("مان پنهنجي گهر کي ٻوڏ کان ڪيئن بچائي سگھان ٿو؟"):
             return "جيڪڏهن توهان ٻوڏ جي خطري واري علائقي ۾ رهندا آهيو ته برقي آلات کي بلند ڪريو ۽ ٻوڏ جا رڪاوٽون لڳايو."
        elif query_normalized == normalize_query("هڪ ايمرجنسي نيڪالي ۾ پهرين قدمن ڇا آهن؟"):
             return "پرسڪون رهو، نيڪالي جي رستن جي پيروي ڪريو، ۽ لفٽون استعمال نه ڪريو."
        elif query_normalized == normalize_query("مان قدرتي آفت بابت ڪيئن ڄاڻ حاصل ڪري سگهان ٿو؟"):
             return "مقامي خبرون ۽ موسم جي اپ ڊيٽس تي نظر رکندا، ۽ ايمرجنسي الرٽس لاءِ سائن اپ ڪندا."
        elif query_normalized == normalize_query("مان مقامي اختيارين سان ڪيئن رابطو ڪري سگهان ٿو؟"):
             return "مقامي اختيارين لاءِ، توهان +92 335 5557362 سان رابطو ڪري سگهو ٿا."
        elif query_normalized == normalize_query("ايمرجنسي رابطو نمبر ڇا آهي؟"):
             return "ايمرجنسي حالتن ۾، مهرباني ڪري 1736 سان رابطو ڪريو."
        elif query_normalized == normalize_query("ڇا هتي ڪو ريسڪيو ٽيم موجود آهي؟"):
             return "ها، ريسڪيو ٽيمون موجود آهن. توهان انهن سان 1736 يا +92 335 5557362 تي رابطو ڪري سگهو ٿا."
        elif query_normalized == normalize_query("هتي پيئڻ جو پاڻي محفوظ آهي؟"):
             return "اسان پيئڻ لاءِ هتي فراهم ڪيل بوتل جو پاڻي استعمال ڪرڻ جي صلاح ڏيون ٿا. ٻوڏ جو پاڻي استعمال ڪرڻ کان پاسو ڪريو ڇاڪاڻ ته اهو آلودگي ٿي سگهي ٿو."
        elif query_normalized == normalize_query("مان طبي مدد ڪٿي حاصل ڪري سگهان ٿو؟") or query_normalized == normalize_query("طبي مدد ڪن جائين ٿوـ"): # Handle both variations
             return "طبي ڪلينڪ سينٽر جي ڏکڻ ونگ ۾ واقع آهي. نشانين جي پيروي ڪريو يا اسان جي عملي کان هدايتون پڇو."
        elif query_normalized == normalize_query("مان پنهنجي خاندان سان ڪيئن رابطو ڪري سگهان ٿو؟"):
             return "اسان وٽ خاندان جي ٻيهر ملاپ لاءِ سهولتون آهن. مهرباني ڪري مدد لاءِ استقباليه تي تفصيل فراهم ڪريو."

        # --- General Fallback ---
        else:
            return "مان آفتن جي انتظام جي معاملن ۾ ماهر آهيان. عام موضوعن تي مدد نه ڪري سگهندس، پر آفتن جي انتظام، ايمرجنسي طريقن يا حفاظتي اپاءَ بابت ڪو به سوال پڇڻ لاءِ آزاد محسوس ڪريو."

    elif output_lang == "Urdu":
        # --- Greetings and Common Phrases ---
        if any(greeting in query_normalized for greeting in ['hi', 'hello', 'hey', 'ہیلو', 'سلام']):
            return "السلام علیکم! میں آپ کا آفات کے انتظام کا مددگار ہوں۔ میں آپ کی کیا مدد کر سکتا ہوں؟"
        elif any(time in query_normalized for time in ['good morning', 'good afternoon', 'good evening']):
            return "آپ کا شکریہ! میں آپ کی آفات کے انتظام کے سوالات میں مدد کرنے کے لیے حاضر ہوں۔"
        elif 'how are you' in query_normalized or 'آپ کیسے ہیں' in query_normalized:
            return "میں ٹھیک ہوں، آپ کی پوچھنے کا شکریہ! میں آفات کے انتظام کی معلومات دینے کے لیے تیار ہوں۔"
        elif 'thank' in query_normalized or 'شکریہ' in query_normalized:
            return "آپ کا شکریہ! آفات کے انتظام کے بارے میں کوئی بھی سوال پوچھنے کے لیے آزاد محسوس کریں۔"
        elif 'bye' in query_normalized or 'goodbye' in query_normalized or 'خدا حافظ' in query_normalized:
            return "خدا حافظ! اگر آپ کو آفات کے انتظام کے بارے میں مزید سوالات ہوں تو ضرور پوچھیں۔"
        elif 'who are you' in query_normalized or 'آپ کون ہیں' in query_normalized:
            return "میں ایک خصوصی آفات کے انتظام کا مددگار ہوں۔ میں آفات کے انتظام، حفاظتی اقدامات اور آفات کے جواب کی حکمت عملی کے بارے میں معلومات دے سکتا ہوں۔"

        # --- Specific Q&A (Hardcoded from JSON) ---
        elif query_normalized == normalize_query("زلزلے کے دوران مجھے کیا کرنا چاہئے؟"):
             return "زمین پر گر جائیں، پناہ لیں، اور جھٹکے رکنے تک انتظار کریں۔"
        elif query_normalized == normalize_query("گرمی کی لہر کے دوران میں کیسے محفوظ رہ سکتا ہوں؟"):
             return "ہائیڈریٹ رہیں، براہ راست دھوپ سے بچیں، اور زیادہ گرمی کے اوقات میں اندر رہیں۔"
        elif query_normalized == normalize_query("اگر میں دیکھوں کہ جنگل کی آگ قریب آ رہی ہے تو مجھے کیا کرنا چاہئے؟"):
             return "اگر ہدایت دی جائے تو فوراً نکلو اور آگ سے دور محفوظ علاقے میں چلے جائیں۔"
        elif query_normalized == normalize_query("سمندری طوفان کے لئے میں کیسے تیاری کر سکتا ہوں؟"):
             return "باہر کے اشیاء کو محفوظ کریں، کھڑکیوں کو مضبوط کریں، اور اگر ہدایت دی جائے تو نکاسی کے احکامات پر عمل کریں۔"
        elif query_normalized == normalize_query("میرے ایمرجنسی کٹ میں کیا شامل ہونا چاہئے؟"):
             return "پانی، غیر خراب ہونے والا کھانا، ٹارچ، بیٹریاں، ابتدائی طبی امداد کا کٹ، اور ضروری ادویات۔"
        elif query_normalized == normalize_query("میں اپنے گھر کو سیلاب سے کیسے بچا سکتا ہوں؟"):
             return "اگر آپ سیلاب کے خطرے والے علاقے میں رہتے ہیں تو بجلی کے آلات کو بلند کریں اور سیلاب کی رکاوٹیں لگائیں۔"
        elif query_normalized == normalize_query("ایمرجنسی نکاسی میں پہلے اقدامات کیا ہیں؟"):
             return "پرسکون رہیں، نکاسی کے راستوں کی پیروی کریں، اور لفٹوں کا استعمال نہ کریں۔"
        elif query_normalized == normalize_query("میں قدرتی آفت کے بارے میں کیسے مطلع رہ سکتا ہوں؟"):
             return "مقامی خبریں اور موسمی اپ ڈیٹس دیکھتے رہیں، اور ایمرجنسی الرٹس کے لئے سائن اپ کریں۔"
        elif query_normalized == normalize_query("میں مقامی حکام سے کیسے رابطہ کر سکتا ہوں؟"):
             return "مقامی حکام کے لئے، آپ +92 335 5557362 سے رابطہ کر سکتے ہیں۔"
        elif query_normalized == normalize_query("ایمرجنسی رابطہ نمبر کیا ہے؟"):
             return "ہنگامی صورتحال میں، براہ کرم 1736 سے رابطہ کریں۔"
        elif query_normalized == normalize_query("کیا یہاں کوئی ریسکیو ٹیم موجود ہے؟"):
             return "جی ہاں، ریسکیو ٹیمیں دستیاب ہیں۔ آپ ان سے 1736 یا +92 335 5557362 پر رابطہ کر سکتے ہیں۔"
        elif query_normalized == normalize_query("یہاں پینے کا پانی کیا محفوظ ہے؟"):
             return "ہم پینے کے لئے یہاں دی گئی بوتل پانی کا استعمال کرنے کی تجویز دیتے ہیں۔ براہ کرم سیلاب کے پانی کو نہ پیں کیونکہ یہ آلودہ ہو سکتا ہے۔"
        elif query_normalized == normalize_query("میں طبی مدد کہاں حاصل کروں؟") or query_normalized == normalize_query("طبي مدد ڪن جائين ٿوـ"): # Handle both variations
             return "طبی کلینک مرکز کے جنوبی ونگ میں واقع ہے۔ نشانیوں کی پیروی کریں یا ہمارے عملے سے رہنمائی کے لئے پوچھیں۔"
        elif query_normalized == normalize_query("میں اپنے خاندان سے کیسے رابطہ کروں؟"):
             return "ہمارے پاس خاندان کے ملاپ کے لیے سہولیات ہیں۔ براہ کرم مدد کے لیے استقبالیہ پر تفصیلات فراہم کریں۔"

        # --- General Fallback ---
        else:
            return "میں آفات کے انتظام کے معاملات میں ماہر ہوں۔ عام موضوعات پر مدد نہیں کر سکتا، لیکن آفات کے انتظام، ایمرجنسی طریقوں یا حفاظتی اقدامات کے بارے میں کوئی بھی سوال پوچھنے کے لیے آزاد محسوس کریں۔"

    else: # Default to English
        # --- Greetings and Common Phrases ---
        if any(greeting in query_normalized for greeting in ['hi', 'hello', 'hey']):
            return "Hello! I'm your disaster management assistant. How can I help you today?"
        elif any(time in query_normalized for time in ['good morning', 'good afternoon', 'good evening']):
            return "Thank you! I'm here to help you with disaster management related questions."
        elif 'how are you' in query_normalized:
            return "I'm functioning well, thank you for asking! I'm ready to help you with disaster management information."
        elif 'thank' in query_normalized:
            return "You're welcome! Feel free to ask any questions about disaster management."
        elif 'bye' in query_normalized or 'goodbye' in query_normalized:
            return "Goodbye! If you have more questions about disaster management later, feel free to ask."
        elif 'who are you' in query_normalized:
            return "I'm a specialized chatbot designed to help with disaster management information and procedures. I can answer questions about emergency protocols, safety measures, and disaster response strategies."

        # --- Specific Q&A (Hardcoded from JSON) ---
        elif query_normalized == normalize_query("What should I do during an earthquake?"):
             return "Drop, cover, and hold on until the shaking stops."
        elif query_normalized == normalize_query("How can I stay safe during a heatwave?"):
             return "Stay hydrated, avoid direct sunlight, and stay indoors during peak heat hours."
        elif query_normalized == normalize_query("What should I do if I see a wildfire approaching?"):
             return "Evacuate immediately if instructed, and move to a safe area away from the fire."
        elif query_normalized == normalize_query("How can I prepare for a hurricane?"):
             return "Secure outdoor objects, reinforce windows, and follow evacuation orders if given."
        elif query_normalized == normalize_query("What should I include in my emergency kit?"):
             return "Water, non-perishable food, flashlight, batteries, first aid kit, and essential medications."
        elif query_normalized == normalize_query("How can I protect my home from floods?"):
             return "Elevate electrical appliances and install flood barriers if you live in a flood-prone area."
        elif query_normalized == normalize_query("What are the first steps in an emergency evacuation?"):
             return "Stay calm, follow evacuation routes, and do not use elevators."
        elif query_normalized == normalize_query("How can I stay informed about a natural disaster?"):
             return "Monitor local news and weather updates, and sign up for emergency alerts."
        elif query_normalized == normalize_query("How can I contact local authorities?"):
             return "For local authorities, you can contact +92 335 5557362."
        elif query_normalized == normalize_query("What is the emergency contact number?"):
             return "For emergencies, please contact 1736."
        elif query_normalized == normalize_query("Is there a rescue team available?"):
             return "Yes, rescue teams are available. You can contact them at 1736 or +92 335 5557362."
        elif query_normalized == normalize_query("Is the drinking water safe here?"):
             return "We advise using bottled water provided here for drinking. Avoid consuming floodwater as it may be contaminated."
        elif query_normalized == normalize_query("Where can I find medical help?"):
             return "The medical clinic is located in the south wing of the center. Follow the signs or ask our staff for directions."
        elif query_normalized == normalize_query("How can I contact my family?"):
             return "We have facilities for family reunification. Please provide details at the reception for assistance."

        # --- General Fallback ---
        else:
            return "I'm specialized in disaster management topics. While I can't help with general topics, I'd be happy to answer any questions about disaster management, emergency procedures, or safety protocols."


def get_rag_response(qa_chain, query):
    """
    Get a response from the RAG system for a domain-specific query.
    
    Args:
        qa_chain: The initialized QA chain
        query: User's question
        
    Returns:
        str: Generated response
    """
    try:
        # Add language-specific instructions based on output language
        lang_instruction = get_language_prompt(st.session_state.output_language)
        
        # Get response from RAG system
        response = qa_chain({"query": f"{query}\n\n{lang_instruction}"})
        return response['result']
    except Exception as e:
        st.error(f"Error generating RAG response: {str(e)}")
        return f"I'm sorry, I couldn't generate a response. Error: {str(e)}"

def initialize_rag():
    try:
        # API Keys from secrets
        PINECONE_API_KEY = st.secrets["PINECONE_API_KEY"]
        GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
        
        if not GOOGLE_API_KEY or not PINECONE_API_KEY:
            st.error("Please set up API keys in Streamlit Cloud secrets")
            st.stop()
            
        genai.configure(api_key=GOOGLE_API_KEY)

        # Initialize Pinecone
        from pinecone import Pinecone
        pc = Pinecone(api_key=PINECONE_API_KEY)

        # Initialize embeddings
        try:
            embeddings = HuggingFaceEmbeddings(
                model_name='all-MiniLM-L6-v2',
                model_kwargs={'device': 'cpu'},
                encode_kwargs={
                    'normalize_embeddings': True,
                    'batch_size': 32
                }
            )
        except Exception as e:
            st.error(f"Error initializing embeddings: {str(e)}")
            st.stop()

        # Initialize vector store
        index_name = "pdfinfo"
        vectorstore = PineconeVectorStore(
            index=pc.Index(index_name),
            embedding=embeddings,
            text_key="text"
        )

        # Create Gemini LLM
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-exp",
            temperature=0.1,
            google_api_key=GOOGLE_API_KEY,
            max_retries=3,
            timeout=30,
            max_output_tokens=2048
        )

        # Create the QA chain with improved prompt
        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=vectorstore.as_retriever(search_kwargs={"k": 6}),
            return_source_documents=False,
            chain_type_kwargs={
                "prompt": PromptTemplate(
                    template=f"""You are a knowledgeable disaster management assistant. {get_language_prompt(st.session_state.output_language)}

Use the following guidelines to answer questions:

1. If the context contains relevant information:
   - Provide a detailed and comprehensive answer using the information
   - Include specific details and procedures from the source
   - Structure the response in a clear, readable format
   - Use professional and precise language

2. If the context does NOT contain sufficient information:
   - Provide a general, informative response based on common disaster management principles
   - Be honest about not having specific details
   - Offer to help with related topics that are within your knowledge base
   - Never make up specific numbers or procedures
   - Guide the user towards asking more specific questions about disaster management

Context: {{context}}

Question: {{question}}

Response (remember to be natural and helpful):""",
                    input_variables=["context", "question"],
                )
            }
        )
        return qa_chain, llm
    except Exception as e:
        st.error(f"Error initializing RAG system: {str(e)}")
        st.stop()

def main():
    # Page config
    st.set_page_config(
        page_title="Disaster Management RAG Chatbot",
        page_icon="🤖",
        layout="wide"
    )

    # Custom CSS for layout and animations
    st.markdown("""
        <style>
        /* Main container styling */
        .main {
            padding: 0;
            max-width: 1200px;
            margin: 0 auto;
        }
        
        /* Chat container */
        .chat-container {
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }
        
        /* Sidebar styling */
        .css-1d391kg {
            padding: 1.5rem;
            background-color: #1e1e1e;
        }
        
        /* Streamlit elements styling */
        div.stButton > button {
            width: 100%;
            background-color: #252525 !important;
            border: none !important;
            color: #e0e0e0 !important;
            border-radius: 4px !important;
            padding: 0.5rem !important;
            margin: 0.25rem 0 !important;
            font-size: 0.9rem !important;
            transition: all 0.2s ease !important;
            display: flex !important;
            align-items: center !important;
            gap: 0.5rem !important;
        }

        div.stButton > button:hover {
            background-color: #353535 !important;
            transform: translateY(-1px);
        }

        /* Primary buttons */
        div.stButton > button[kind="primary"] {
            background-color: #005fb8 !important;
            color: white !important;
        }

        div.stButton > button[kind="primary"]:hover {
            background-color: #0052a3 !important;
        }

        /* Section headers */
        .section-header {
            color: #808080 !important;
            font-size: 0.85rem !important;
            font-weight: 500 !important;
            margin: 1rem 0 0.5rem 0 !important;
            padding: 0 !important;
            display: flex !important;
            align-items: center !important;
            gap: 0.5rem !important;
            text-transform: uppercase !important;
            letter-spacing: 0.5px !important;
        }

        /* Chat history items */
        .chat-item {
            background-color: #252525;
            border: none;
            border-radius: 4px;
            padding: 0.5rem;
            margin: 0.25rem 0;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .chat-item:hover {
            background-color: #353535;
            transform: translateY(-1px);
        }

        /* Expander styling */
        .streamlit-expanderHeader {
            background-color: #252525 !important;
            border: none !important;
            border-radius: 4px !important;
            padding: 0.5rem !important;
            margin: 0.25rem 0 !important;
            color: #e0e0e0 !important;
            font-weight: normal !important;
            font-size: 0.9rem !important;
        }

        .streamlit-expanderHeader:hover {
            background-color: #353535 !important;
        }

        .streamlit-expanderContent {
            border: none !important;
            border-radius: 4px !important;
            padding: 0.75rem !important;
            background-color: #252525 !important;
            color: #e0e0e0 !important;
            margin-top: 0.25rem !important;
        }

        /* Profile button */
        .profile-button {
            background-color: #252525 !important;
            border: none !important;
            border-radius: 4px !important;
            padding: 0.5rem !important;
            color: #e0e0e0 !important;
            display: flex !important;
            align-items: center !important;
            gap: 0.5rem !important;
            transition: all 0.2s ease !important;
            font-size: 0.9rem !important;
        }

        .profile-button:hover {
            background-color: #353535 !important;
            transform: translateY(-1px);
        }

        /* Dividers */
        hr {
            margin: 1.25rem 0 !important;
            border-color: #353535 !important;
            opacity: 0.3 !important;
        }

        /* Selectbox styling */
        .stSelectbox > div > div {
            background-color: #252525 !important;
            border: none !important;
            color: #e0e0e0 !important;
        }

        .stSelectbox > div > div:hover {
            border: none !important;
        }

        /* Selectbox options */
        .stSelectbox > div > div > div {
            background-color: #252525 !important;
            color: #e0e0e0 !important;
        }

        /* Thinking animation */
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .thinking-container {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            margin: 0;
            padding: 0.5rem 0.5rem;
            background-color: transparent;
            border-radius: 4px;
            max-width: fit-content;
        }

        .thinking-spinner {
            width: 16px;
            height: 16px;
            border: 2px solid #808080;
            border-top: 2px solid transparent;
            border-radius: 50%;
            animation: spin 1s linear infinite;
           
        }

        .thinking-text {
            color: #fffffff;
            font-size: 0.9rem;
            font-weight: 500;
        }

        /* Chat message container */
        .stChatMessage {
            display: flex;
            align-items: flex-start;
            gap: 1rem;
            padding: 1rem;
        }

        .stChatMessageContent {
            flex: 1;
        }
        
        /* Main heading */
        .main-heading {
            text-align: center;
            color: #3498db;
            font-weight: 700;
            margin: 1.5rem 0;
            padding: 1rem;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 15px;
            backdrop-filter: blur(10px);
        }
        
        /* Responsive font sizes */
        @media screen and (min-width: 768px) {
            .main-heading {
                font-size: 2.2rem;
            }
        }
        
        @media screen and (max-width: 767px) {
            .main-heading {
                font-size: 1.5rem;
                margin: 1rem 0;
                padding: 0.75rem;
            }
        }
        </style>
    """, unsafe_allow_html=True)

    # Add custom CSS with media queries for responsive heading
    st.markdown("""
        <style>
        .main-heading {
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 1.5rem;
            color: #262730;
            text-align: center;
        }
        
        /* Mobile devices */
        @media screen and (max-width: 768px) {
            .main-heading {
                font-size: 1.75rem;
                margin-bottom: 1rem;
                padding: 0 10px;
            }
        }
        
        /* Extra small devices */
        @media screen and (max-width: 480px) {
            .main-heading {
                font-size: 32px !important;
                margin-bottom: 0.75rem;
            }
        }
        </style>
        """, unsafe_allow_html=True)
        
    # Display the responsive heading
    st.markdown('<h1 class="main-heading">🚨 Welcome to the Disaster Management Assistant</h1>', unsafe_allow_html=True)

    # Handle authentication
    is_authenticated, user = auth_page()
    
    if not is_authenticated:
        st.markdown("""
        <div style="text-align: center; padding: 20px;">
        <h2></h2>
        <p></p>
        </div>
        """, unsafe_allow_html=True)
        return
    
    # User is authenticated
    user_id = user['uid']
    preferences = load_user_preferences(user)

    # Main chat interface
    st.title("")

    # Display thinking animation when processing
    if st.session_state.get('thinking', False):
        st.markdown("""
            <div class="thinking-container">
                <div class="thinking-spinner"></div>
                <span class="thinking-text">Thinking...</span>
            </div>
        """, unsafe_allow_html=True)

    # Initialize RAG system
    qa_chain, llm = initialize_rag()

    # Sidebar with clean layout
    with st.sidebar:
        if st.session_state.get('show_settings', False):
            st.title("User Settings")
            if st.button("← Back to Chat", type="primary"):
                st.session_state.show_settings = False
                st.rerun()
            user_sidebar(user)
        else:
            # New Chat Button
            if st.button("✨ New Conversation", type="primary", use_container_width=True):
                # Create new session and clear messages
                history_manager = ChatHistoryManager()
                session_id = history_manager.create_new_session(user_id)
                st.session_state.messages = []
                st.session_state.current_session_id = session_id
                st.rerun()
            
            chat_history_sidebar(user_id)
            
            st.divider()
            
            # Language Settings
            with st.expander("🌐 Language"):
                input_language = st.selectbox(
                    "Input Language",
                    ["English", "Urdu", "Sindhi"],
                    index=["English", "Urdu", "Sindhi"].index(st.session_state.input_language)
                )
                output_language = st.selectbox(
                    "Output Language",
                    ["English", "Urdu", "Sindhi"],
                    index=["English", "Urdu", "Sindhi"].index(st.session_state.output_language)
                )
                
                if input_language != st.session_state.input_language:
                    st.session_state.input_language = input_language
                    save_user_preferences(user_id)
                    
                if output_language != st.session_state.output_language:
                    st.session_state.output_language = output_language
                    save_user_preferences(user_id)
            
            # About Section
            with st.expander("ℹ️ About"):
                st.markdown("""
                # This chatbot uses:
                
                - 🧠 Gemini Pro for text generation
                - 🔍 Pinecone for vector storage
                - ⚡ LangChain for the RAG pipeline
                - 🌐 Multilingual support (English , Sindhi and Urdu)
                
                # Topics 📑
                
                You can ask questions about:
                
                - 📋 Disaster management procedures
                - 🚨 Emergency protocols
                - 🛡️ Safety measures
                - 📊 Risk assessment
                - 👥 Relief operations
                
                # Tips 💡
                
                For best results:
                
                - ✨ Be specific in your questions
                - 🎯 Ask about one topic at a time
                - 📝 Use clear, simple language
                - 🔄 Try rephrasing if needed
                """)
            
            st.divider()
            
            # Profile Button
            if st.button("🙍🏻‍♂️ Profile", use_container_width=True):
                st.session_state.show_settings = True
                st.rerun()
            
            st.divider()
            
            # Download Options
            st.markdown('<div class="section-header">💾 Export</div>', unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📄 PDF", use_container_width=True):
                    pdf_file = create_chat_pdf()
                    st.download_button(
                        label="Download PDF",
                        data=pdf_file,
                        file_name=f"chat_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                        mime="application/pdf"
                    )
            with col2:
                if st.button("📝 Text", use_container_width=True):
                    text_file = create_chat_text()
                    st.download_button(
                        label="Download Text",
                        data=text_file,
                        file_name=f"chat_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                        mime="text/plain"
                    )
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Create a dedicated container for the email UI
    email_ui_container = st.container()

    # Show email sharing UI in the dedicated container
    with email_ui_container:
        if "user" in locals():
            user_email = user.get('email', 'Anonymous')
        else:
            user_email = "Anonymous"
        show_email_ui(st.session_state.messages, user_email)

    # Chat input
    if prompt := st.chat_input("Ask Your Questions Here..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        if is_authenticated:
            metadata = {
                'language': st.session_state.input_language,
                'timestamp': datetime.now().isoformat()
            }
            sync_chat_message(user_id, "user", prompt, metadata)
        
        with st.chat_message("user"):
            st.markdown(prompt)
        
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            
            # Show thinking animation
            message_placeholder.markdown("""
            <div class="thinking-container">
                <div class="thinking-spinner"></div>
                <span class="thinking-text">Thinking...</span>
            </div>
            """, unsafe_allow_html=True)
            
            try:
                if is_general_chat(prompt):
                    response = get_general_response(prompt)
                else:
                    response = get_rag_response(qa_chain, prompt)
                
                message_placeholder.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
                
                if is_authenticated:
                    metadata = {
                        'language': st.session_state.output_language,
                        'timestamp': datetime.now().isoformat(),
                        'type': 'general' if is_general_chat(prompt) else 'rag'
                    }
                    sync_chat_message(user_id, "assistant", response, metadata)
                
                # Force Streamlit to rerun to refresh the UI and show the email sharing component
                st.rerun()
                
            except Exception as e:
                error_message = f"Error generating response: {str(e)}"
                message_placeholder.error(error_message)
                st.session_state.messages.append({"role": "assistant", "content": error_message})
                
                # Force Streamlit to rerun even in case of error
                st.rerun()

if __name__ == "__main__":
    main()