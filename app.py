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

# Initialize session state for chat history and language preferences
if "messages" not in st.session_state:
    st.session_state.messages = []
if "input_language" not in st.session_state:
    st.session_state.input_language = "English"
if "output_language" not in st.session_state:
    st.session_state.output_language = "English"

# Sindh-inspired color palette
COLORS = {
    'ajrak_red': '#8D1B1B',
    'deep_indigo': '#1E2952',
    'sand_beige': '#C2A878',
    'sindh_green': '#15616D',
    'warm_mustard': '#D89216',
    'charcoal_black': '#2B2B2B'
}

# Custom CSS with Sindh-inspired colors
st.markdown(f"""
    <style>
    /* Main container styling */
    .main .block-container {{
        background-color: {COLORS['sand_beige']}20;
        padding: 2rem;
        border-radius: 10px;
    }}
    
    /* Header styling */
    .stTitle {{
        color: {COLORS['ajrak_red']} !important;
        font-family: 'Arial', sans-serif;
    }}
    
    /* Sidebar styling */
    .css-1d391kg {{
        background-color: {COLORS['deep_indigo']};
    }}
    
    /* Chat message containers */
    .user-message {{
        background-color: {COLORS['sindh_green']}15 !important;
        border-left: 5px solid {COLORS['sindh_green']} !important;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0 10px 10px 0;
    }}
    
    .assistant-message {{
        background-color: {COLORS['warm_mustard']}15 !important;
        border-left: 5px solid {COLORS['warm_mustard']} !important;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0 10px 10px 0;
    }}
    
    /* Button styling */
    .stButton button {{
        background-color: {COLORS['sindh_green']} !important;
        color: white !important;
        border: none !important;
        border-radius: 5px !important;
        transition: all 0.3s ease !important;
    }}
    
    .stButton button:hover {{
        background-color: {COLORS['deep_indigo']} !important;
        transform: translateY(-2px);
    }}
    
    /* Input box styling */
    .stTextInput input {{
        border: 2px solid {COLORS['deep_indigo']}40 !important;
        border-radius: 5px !important;
    }}
    
    .stTextInput input:focus {{
        border-color: {COLORS['sindh_green']} !important;
        box-shadow: 0 0 5px {COLORS['sindh_green']}40 !important;
    }}
    
    /* Selectbox styling */
    .stSelectbox select {{
        border-color: {COLORS['deep_indigo']} !important;
    }}
    
    /* Expander styling */
    .streamlit-expanderHeader {{
        background-color: {COLORS['deep_indigo']} !important;
        color: white !important;
        border-radius: 5px !important;
    }}
    
    /* Scrollbar styling */
    ::-webkit-scrollbar {{
        width: 10px;
    }}
    
    ::-webkit-scrollbar-track {{
        background: {COLORS['sand_beige']}30;
    }}
    
    ::-webkit-scrollbar-thumb {{
        background: {COLORS['deep_indigo']};
        border-radius: 5px;
    }}
    
    /* Footer styling */
    footer {{
        border-top: 2px solid {COLORS['deep_indigo']}20;
        padding-top: 1rem;
        margin-top: 2rem;
    }}
    </style>
""", unsafe_allow_html=True)

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
    """Generate appropriate responses for general chat."""
    query_lower = query.lower()
    output_lang = st.session_state.output_language
    
    if output_lang == "Sindhi":
        if any(greeting in query_lower for greeting in ['hi', 'hello', 'hey']):
            return "السلام عليڪم! مان توهان جو آفتن جي انتظام جو مددگار آهيان. مان توهان جي ڪهڙي مدد ڪري سگهان ٿو؟"
        elif any(time in query_lower for time in ['good morning', 'good afternoon', 'good evening']):
            return "توهان جو مهرباني! مان توهان جي آفتن جي انتظام جي سوالن ۾ مدد ڪرڻ لاءِ حاضر آهيان."
        elif 'how are you' in query_lower:
            return "مان ٺيڪ آهيان، توهان جي پڇڻ جو مهرباني! مان آفتن جي انتظام جي معلومات ڏيڻ لاءِ تيار آهيان."
        elif 'thank' in query_lower:
            return "توهان جو مهرباني! آفتن جي انتظام بابت ڪو به سوال پڇڻ لاءِ آزاد محسوس ڪريو."
        elif 'bye' in query_lower or 'goodbye' in query_lower:
            return "خدا حافظ! جيڪڏهن توهان کي آفتن جي انتظام بابت وڌيڪ سوال هجن ته پوءِ ضرور پڇو."
        elif 'who are you' in query_lower:
            return "مان هڪ خاص آفتن جي انتظام جو مددگار آهيان. مان آفتن جي انتظام، حفاظتي اپاءَ ۽ آفتن جي جواب جي حڪمت عملي بابت معلومات ڏئي سگهان ٿو."
        else:
            return "مان آفتن جي انتظام جي معاملن ۾ ماهر آهيان. عام موضوعن تي مدد نه ڪري سگهندس، پر آفتن جي انتظام، ايمرجنسي طريقن يا حفاظتي اپاءَ بابت ڪو به سوال پڇڻ لاءِ آزاد محسوس ڪريو."
    elif output_lang == "Urdu":
        if any(greeting in query_lower for greeting in ['hi', 'hello', 'hey']):
            return "السلام علیکم! میں آپ کا آفات کے انتظام کا مددگار ہوں۔ میں آپ کی کیا مدد کر سکتا ہوں؟"
        elif any(time in query_lower for time in ['good morning', 'good afternoon', 'good evening']):
            return "آپ کا شکریہ! میں آپ کی آفات کے انتظام کے سوالات میں مدد کرنے کے لیے حاضر ہوں۔"
        elif 'how are you' in query_lower:
            return "میں ٹھیک ہوں، آپ کی پوچھنے کا شکریہ! میں آفات کے انتظام کی معلومات دینے کے لیے تیار ہوں۔"
        elif 'thank' in query_lower:
            return "آپ کا شکریہ! آفات کے انتظام کے بارے میں کوئی بھی سوال پوچھنے کے لیے آزاد محسوس کریں۔"
        elif 'bye' in query_lower or 'goodbye' in query_lower:
            return "خدا حافظ! اگر آپ کو آفات کے انتظام کے بارے میں مزید سوالات ہوں تو ضرور پوچھیں۔"
        elif 'who are you' in query_lower:
            return "میں ایک خصوصی آفات کے انتظام کا مددگار ہوں۔ میں آفات کے انتظام، حفاظتی اقدامات اور آفات کے جواب کی حکمت عملی کے بارے میں معلومات دے سکتا ہوں۔"
        else:
            return "میں آفات کے انتظام کے معاملات میں ماہر ہوں۔ عام موضوعات پر مدد نہیں کر سکتا، لیکن آفات کے انتظام، ایمرجنسی طریقوں یا حفاظتی اقدامات کے بارے میں کوئی بھی سوال پوچھنے کے لیے آزاد محسوس کریں۔"
    else:
        # Original English responses
        if any(greeting in query_lower for greeting in ['hi', 'hello', 'hey']):
            return "Hello! I'm your disaster management assistant. How can I help you today?"
        elif any(time in query_lower for time in ['good morning', 'good afternoon', 'good evening']):
            return f"Thank you, {query}! I'm here to help you with disaster management related questions."
        elif 'how are you' in query_lower:
            return "I'm functioning well, thank you for asking! I'm ready to help you with disaster management information."
        elif 'thank' in query_lower:
            return "You're welcome! Feel free to ask any questions about disaster management."
        elif 'bye' in query_lower or 'goodbye' in query_lower:
            return "Goodbye! If you have more questions about disaster management later, feel free to ask."
        elif 'who are you' in query_lower:
            return "I'm a specialized chatbot designed to help with disaster management information and procedures. I can answer questions about emergency protocols, safety measures, and disaster response strategies."
        else:
            return "I'm specialized in disaster management topics. While I can't help with general topics, I'd be happy to answer any questions about disaster management, emergency procedures, or safety protocols."

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
    st.set_page_config(
        page_title="Sindh Disaster Management Assistant",
        page_icon="🆘",
        layout="wide"
    )

    # Custom title with Sindhi cultural context
    st.markdown(f"""
        <h1 style='color: {COLORS["ajrak_red"]}; text-align: center; margin-bottom: 2rem;'>
            Sindh Disaster Management Assistant 🆘
        </h1>
        <p style='text-align: center; color: {COLORS["deep_indigo"]}; font-size: 1.2em;'>
            Serving the people of Sindh with emergency guidance and support
        </p>
    """, unsafe_allow_html=True)
    
    try:
        # Initialize RAG system
        qa_chain, llm = initialize_rag()

        # Sidebar with cultural styling
        with st.sidebar:
            st.markdown(f"""
                <h2 style='color: {COLORS["warm_mustard"]}; margin-bottom: 1rem;'>Settings</h2>
            """, unsafe_allow_html=True)
            
            # Language Settings in an expander
            with st.expander("🌐 Language Settings", expanded=False):
                st.session_state.input_language = st.selectbox(
                    "Select Input Language",
                    ["English", "Urdu", "Sindhi"],
                    key="input_lang_select"
                )
                st.session_state.output_language = st.selectbox(
                    "Select Output Language",
                    ["English", "Urdu", "Sindhi"],
                    key="output_lang_select"
                )

            # About section in an expander
            with st.expander("ℹ️ About", expanded=False):
                st.markdown("""
                ### Features
                This chatbot uses:
                - 🧠 Gemini Pro for text generation
                - 🔍 Pinecone for vector storage
                - ⚡ LangChain for the RAG pipeline
                - 🌐 Multilingual support (English, Urdu & Sindhi)
                
                ### Topics
                You can ask questions about:
                - 📋 Disaster management procedures
                - 🚨 Emergency protocols
                - 🛡️ Safety measures
                - 📊 Risk assessment
                - 🏥 Relief operations
                
                ### Tips
                - Be specific in your questions
                - Ask about one topic at a time
                - Use clear, simple language
                """)
            
            # Download options in an expander
            with st.expander("💾 Download Chat History", expanded=False):
                col_download_pdf, col_download_text = st.columns(2)
                
                with col_download_pdf:
                    if st.button("Generate PDF"):
                        st.session_state.pdf_data = create_chat_pdf()
                        st.success("PDF generated! Click download button below.")
                    
                    if "pdf_data" in st.session_state and st.session_state.pdf_data is not None:
                        if st.download_button(
                            "Download PDF",
                            data=st.session_state.pdf_data,
                            file_name="chat_history.pdf",
                            mime="application/pdf"
                        ):
                            st.success("PDF downloaded!")
                
                with col_download_text:
                    text_data = create_chat_text()
                    if text_data is not None:
                        if st.download_button(
                            "Download Text",
                            data=text_data,
                            file_name="chat_history.txt",
                            mime="text/plain"
                        ):
                            st.success("Text downloaded!")
            
            # Clear chat button at the bottom of sidebar
            if st.button("🗑️ Clear Chat History"):
                st.session_state.messages = []
                if "pdf_data" in st.session_state:
                    del st.session_state.pdf_data
                st.rerun()

        # Main chat interface
        st.markdown('<div class="chat-container">', unsafe_allow_html=True)
        
        # Display chat title
        st.title("Disaster Management Assistant 🤖")
        
        # Display chat messages
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        # Fixed input box at bottom
        st.markdown('<div class="input-container">', unsafe_allow_html=True)
        if prompt := st.chat_input("Ask your question here"):
            # Display user message
            with st.chat_message("user"):
                st.markdown(prompt)
            st.session_state.messages.append({"role": "user", "content": prompt})

            # Display assistant response
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    if is_general_chat(prompt):
                        response_text = get_general_response(prompt)
                    else:
                        response = qa_chain({"query": prompt})
                        response_text = response['result']
                    st.markdown(response_text)
            st.session_state.messages.append({"role": "assistant", "content": response_text})
            
            # Update PDF data after new message
            if "pdf_data" in st.session_state:
                st.session_state.pdf_data = create_chat_pdf()
                
        st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

    except Exception as e:
        st.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()