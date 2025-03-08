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

# Import authentication modules
from auth.authenticator import FirebaseAuthenticator
from auth.chat_history import ChatHistoryManager
from auth.ui import auth_page, user_sidebar, chat_history_sidebar, sync_chat_message, load_user_preferences, save_user_preferences

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
        page_icon="🚨",
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
            padding: 20px;
        }
        
        /* Streamlit elements styling */
        div.stButton > button {
            width: 100%;
        }

        /* Thinking animation */
        @keyframes thinking {
            0% { opacity: 0.3; }
            50% { opacity: 1; }
            100% { opacity: 0.3; }
        }
        
        .thinking-animation {
            display: flex;
            align-items: center;
            gap: 8px;
            animation: thinking 1.5s infinite;
            margin-bottom: 10px;
        }
        
        .thinking-dot {
            width: 8px;
            height: 8px;
            background-color: #0066cc;
            border-radius: 50%;
        }

        /* User profile button */
        .user-profile {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px;
            border-radius: 8px;
            cursor: pointer;
            transition: background-color 0.3s;
        }

        .user-profile:hover {
            background-color: #f0f2f6;
        }
        </style>
    """, unsafe_allow_html=True)

    # Handle authentication
    is_authenticated, user = auth_page()
    
    if not is_authenticated:
        # Show welcome message with minimal styling
        st.markdown("""
        <div style="text-align: center; padding: 20px;">
        <h2>🚨 Welcome to the Disaster Management Assistant</h2>
        <p>Please log in or create an account to access the chatbot.</p>
        </div>
        """, unsafe_allow_html=True)
        return
    
    # User is authenticated
    user_id = user['uid']
    preferences = load_user_preferences(user)

    # Sidebar with improved layout
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/000000/emergency-exit.png", width=50)
        
        # User profile section
        if st.session_state.get('show_settings', False):
            st.title("User Settings")
            # Back button
            if st.button("← Back to Chat"):
                st.session_state.show_settings = False
                st.rerun()
            
            # User profile settings
            st.subheader("Profile")
            user_sidebar(user)
            
            # Language Settings
            st.subheader("🌐 Language Settings")
            input_language = st.selectbox(
                "Input Language:",
                ["English", "Urdu", "Sindhi"],
                index=["English", "Urdu", "Sindhi"].index(st.session_state.input_language)
            )
            
            output_language = st.selectbox(
                "Output Language:",
                ["English", "Urdu", "Sindhi"],
                index=["English", "Urdu", "Sindhi"].index(st.session_state.output_language)
            )
            
            if input_language != st.session_state.input_language:
                st.session_state.input_language = input_language
                save_user_preferences(user_id)
                
            if output_language != st.session_state.output_language:
                st.session_state.output_language = output_language
                save_user_preferences(user_id)
        else:
            # Show minimal sidebar with user profile button
            col1, col2 = st.columns([1, 4])
            with col1:
                st.markdown("👤")
            with col2:
                if st.button(f"Profile Settings"):
                    st.session_state.show_settings = True
                    st.rerun()
            
            st.divider()
            
            # Chat History
            st.subheader("📝 Chat History")
            chat_history_sidebar(user_id)

            # Download options
            st.subheader("💾 Download Chat")
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("Download PDF"):
                    pdf_file = create_chat_pdf()
                    st.download_button(
                        label="Download PDF",
                        data=pdf_file,
                        file_name=f"chat_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                        mime="application/pdf"
                    )
            
            with col2:
                if st.button("Download Text"):
                    text_file = create_chat_text()
                    st.download_button(
                        label="Download Text",
                        data=text_file,
                        file_name=f"chat_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                        mime="text/plain"
                    )

    # Main chat interface
    st.title("🚨 Disaster Management Assistant")
    
    # Initialize RAG system
    qa_chain, llm = initialize_rag()

    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input
    if prompt := st.chat_input("Ask a question about disaster management..."):
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
            <div class="thinking-animation">
                <div class="thinking-dot"></div>
                <div class="thinking-dot"></div>
                <div class="thinking-dot"></div>
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
                
            except Exception as e:
                error_message = f"Error generating response: {str(e)}"
                message_placeholder.error(error_message)
                st.session_state.messages.append({"role": "assistant", "content": error_message})

if __name__ == "__main__":
    main()