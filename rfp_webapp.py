import streamlit as st
import os
import tempfile
import json
import pandas as pd
from datetime import datetime
from typing import Dict, List, Any
import sqlite3
from pathlib import Path
import openai
from docx import Document
import PyPDF2
import io
import hashlib
import secrets

# Authentication functions
def hash_password(password: str) -> str:
    """Hash a password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    return hash_password(password) == hashed

def check_authentication():
    """Check if user is authenticated"""
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    return st.session_state.authenticated

def login_page():
    """Display login page"""
    st.title("🔐 RFP Database Login")
    st.markdown("Please enter the password to access the RFP Database System")
    
    # Get password from secrets or use default
    try:
        # Try to get password from Streamlit secrets
        correct_password = st.secrets.get("APP_PASSWORD", "rfp2024")
    except:
        # Fallback to default password
        correct_password = "rfp2024"
    
    password = st.text_input("Password", type="password", placeholder="Enter password")
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("Login", type="primary", use_container_width=True):
            if password == correct_password:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ Incorrect password. Please try again.")
    
    st.markdown("---")
    
    # Show current password info
    if correct_password == "rfp2024":
        st.info("💡 **Current password:** `rfp2024` (Default - you can change this)")
    else:
        st.success("✅ **Custom password is set** (Password configured in Streamlit Cloud secrets)")
    
    st.markdown("### 🔧 How to Change Password:")
    st.markdown("""
    1. Go to your **Streamlit Cloud app settings**
    2. Click **"Secrets"**
    3. Add or update: `APP_PASSWORD = "your-new-password"`
    4. Click **"Save"** - the app will restart automatically
    """)

# Configure Streamlit page
st.set_page_config(
    page_title="RFP Database System",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize OpenAI
@st.cache_resource
def init_openai():
    api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.error("⚠️ OpenAI API key not found. Please set OPENAI_API_KEY in secrets or environment variables.")
        st.stop()
    return openai.OpenAI(api_key=api_key)

# Database functions
def init_database():
    """Initialize SQLite database"""
    conn = sqlite3.connect('rfp_database.db')
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rfp_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            content TEXT NOT NULL,
            extracted_data TEXT,
            company_name TEXT,
            is_corrected BOOLEAN DEFAULT FALSE,
            original_rfp_id INTEGER,
            win_status TEXT DEFAULT 'unknown',
            deal_value REAL,
            win_date DATE,
            broker_consultant TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (original_rfp_id) REFERENCES rfp_submissions (id)
        )
    ''')
    
    # Check for missing columns and add them (database migration)
    cursor.execute("PRAGMA table_info(rfp_submissions)")
    columns = [column[1] for column in cursor.fetchall()]
    
    # Add missing columns if they don't exist
    if 'is_corrected' not in columns:
        cursor.execute('ALTER TABLE rfp_submissions ADD COLUMN is_corrected BOOLEAN DEFAULT FALSE')
    if 'original_rfp_id' not in columns:
        cursor.execute('ALTER TABLE rfp_submissions ADD COLUMN original_rfp_id INTEGER')
    if 'win_status' not in columns:
        cursor.execute('ALTER TABLE rfp_submissions ADD COLUMN win_status TEXT DEFAULT "unknown"')
    if 'deal_value' not in columns:
        cursor.execute('ALTER TABLE rfp_submissions ADD COLUMN deal_value REAL')
    if 'win_date' not in columns:
        cursor.execute('ALTER TABLE rfp_submissions ADD COLUMN win_date DATE')
    if 'broker_consultant' not in columns:
        cursor.execute('ALTER TABLE rfp_submissions ADD COLUMN broker_consultant TEXT')
    
    conn.commit()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rfp_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_category TEXT,
            question_text TEXT,
            answer_text TEXT,
            confidence_score INTEGER,
            source_rfp_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_rfp_id) REFERENCES rfp_submissions (id)
        )
    ''')
    
    conn.commit()
    return conn

def save_rfp_submission(filename: str, content: str, extracted_data: Dict, company_name: str = None, is_corrected: bool = False, original_rfp_id: int = None, win_status: str = 'unknown', deal_value: float = None, win_date: str = None, broker_consultant: str = None):
    """Save RFP submission to database"""
    conn = init_database()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO rfp_submissions (filename, content, extracted_data, company_name, is_corrected, original_rfp_id, win_status, deal_value, win_date, broker_consultant)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (filename, content, json.dumps(extracted_data), company_name, is_corrected, original_rfp_id, win_status, deal_value, win_date, broker_consultant))
    
    conn.commit()
    conn.close()

def update_win_status(rfp_id: int, win_status: str, deal_value: float = None, win_date: str = None):
    """Update win/loss status for an RFP"""
    conn = init_database()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE rfp_submissions 
        SET win_status = ?, deal_value = ?, win_date = ?
        WHERE id = ?
    ''', (win_status, deal_value, win_date, rfp_id))
    
    conn.commit()
    conn.close()

def save_corrected_answers(rfp_id: int, corrected_answers: List[Dict]):
    """Save corrected answers to improve future suggestions"""
    conn = init_database()
    cursor = conn.cursor()
    
    for answer in corrected_answers:
        cursor.execute('''
            INSERT INTO rfp_answers (question_category, question_text, answer_text, confidence_score, source_rfp_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (answer.get('category', 'general'), 
              answer.get('question', ''), 
              answer.get('corrected_answer', ''), 
              100,  # High confidence for user-corrected answers
              rfp_id))
    
    conn.commit()
    conn.close()

def get_all_submissions():
    """Get all RFP submissions"""
    conn = init_database()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, filename, company_name, created_at, extracted_data
        FROM rfp_submissions
        ORDER BY created_at DESC
    ''')
    
    results = cursor.fetchall()
    conn.close()
    return results

def search_submissions(query: str):
    """Search RFP submissions"""
    conn = init_database()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, filename, company_name, created_at, extracted_data
        FROM rfp_submissions
        WHERE filename LIKE ? OR company_name LIKE ? OR content LIKE ?
        ORDER BY created_at DESC
    ''', (f'%{query}%', f'%{query}%', f'%{query}%'))
    
    results = cursor.fetchall()
    conn.close()
    return results

# Document processing functions
def extract_text_from_file(file_content: bytes, filename: str) -> str:
    """Extract text from uploaded file"""
    file_extension = filename.lower().split('.')[-1]
    
    try:
        if file_extension == 'pdf':
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text
        elif file_extension == 'docx':
            doc = Document(io.BytesIO(file_content))
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text
        elif file_extension == 'txt':
            return file_content.decode('utf-8')
        else:
            return "Unsupported file format"
    except Exception as e:
        return f"Error extracting text: {str(e)}"

def extract_rfp_data_with_ai(content: str, client) -> Dict[str, Any]:
    """Extract structured data from RFP using AI"""
    
    prompt = f"""
    Analyze this RFP document and extract key information in a structured format.
    
    Please extract the following information if available:
    
    1. Company Information:
       - Company name
       - Industry/sector
       - Company size
       - Location
    
    2. Project Details:
       - Project name/title
       - Project description
       - Timeline/deadlines
       - Budget range
       - Key requirements
    
    3. Technical Requirements:
       - Technology stack preferences
       - Integration requirements
       - Security requirements
       - Performance requirements
    
    4. Business Requirements:
       - Business objectives
       - Success criteria
       - Stakeholders
       - Decision makers
    
    5. Questions and Responses:
       - Extract any questions asked in the RFP
       - Note any specific response requirements
       - Identify mandatory vs optional sections
    
    Please format your response as a JSON object with the above categories.
    If information is not available, use null for that field.
    Be as specific and detailed as possible.
    
    Document content:
    {content[:6000]}  # Limit content to avoid token limits
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert at analyzing RFP documents and extracting structured information. Always respond with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=2000
        )
        
        return json.loads(response.choices[0].message.content)
        
    except Exception as e:
        return {"error": f"Failed to extract data: {str(e)}"}

def find_matching_answers(new_content: str, existing_submissions: List, client) -> Dict[str, Any]:
    """Find matching answers for new RFP"""
    
    if not existing_submissions:
        return {"matches": [], "confidence": 0}
    
    # Get corrected answers from database
    conn = init_database()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT question_category, question_text, answer_text, confidence_score, source_rfp_id
        FROM rfp_answers
        ORDER BY confidence_score DESC
    ''')
    corrected_answers = cursor.fetchall()
    conn.close()
    
    # Create summary of existing submissions
    existing_summary = "Previous RFP Submissions:\n\n"
    
    # Add corrected answers first (highest priority - 100% confidence)
    if corrected_answers:
        existing_summary += "CORRECTED ANSWERS (Highest Priority - 100% Confidence):\n"
        for answer in corrected_answers[:10]:  # Top 10 corrected answers
            existing_summary += f"Category: {answer[0]}\n"
            existing_summary += f"Question: {answer[1]}\n"
            existing_summary += f"Corrected Answer: {answer[2][:200]}...\n"
            existing_summary += f"Confidence: 100% (User-corrected)\n"
            existing_summary += "---\n"
        existing_summary += "\n"
    
    # Add winning submissions (high priority - 95% confidence)
    winning_submissions = [s for s in existing_submissions if len(s) > 5 and s[5] == 'won']
    if winning_submissions:
        existing_summary += "WINNING RFP SUBMISSIONS (High Priority - 95% Confidence - These worked!):\n"
        for submission in winning_submissions[:3]:  # Top 3 winning submissions
            existing_summary += f"🏆 WINNER - RFP: {submission[1]}\n"
            existing_summary += f"Company: {submission[2] or 'Unknown'}\n"
            if len(submission) > 6 and submission[6]:  # deal_value
                existing_summary += f"Deal Value: ${submission[6]:,.0f}\n"
            existing_summary += f"Confidence: 95% (Proven winner)\n"
            if submission[4]:  # extracted_data
                try:
                    data = json.loads(submission[4])
                    for category, info in data.items():
                        if info and isinstance(info, (str, dict)):
                            existing_summary += f"{category}: {str(info)[:200]}...\n"
                except:
                    pass
            existing_summary += "\n---\n"
        existing_summary += "\n"
    
    # Add unknown/pending submissions (medium priority - 80% confidence)
    unknown_submissions = [s for s in existing_submissions if len(s) <= 5 or s[5] in ['unknown', 'pending']]
    if unknown_submissions:
        existing_summary += "UNKNOWN/PENDING RFP SUBMISSIONS (Medium Priority - 80% Confidence - Include these):\n"
        for submission in unknown_submissions[:3]:  # Top 3 unknown/pending
            win_status = submission[5] if len(submission) > 5 else 'unknown'
            status_emoji = {"pending": "⏳", "unknown": "❓"}.get(win_status, "❓")
            existing_summary += f"{status_emoji} RFP: {submission[1]}\n"
            existing_summary += f"Company: {submission[2] or 'Unknown'}\n"
            existing_summary += f"Status: {win_status.upper()}\n"
            existing_summary += f"Confidence: 80% (Unknown outcome - might be good)\n"
            if submission[4]:  # extracted_data
                try:
                    data = json.loads(submission[4])
                    for category, info in data.items():
                        if info and isinstance(info, (str, dict)):
                            existing_summary += f"{category}: {str(info)[:200]}...\n"
                except:
                    pass
            existing_summary += "\n---\n"
        existing_summary += "\n"
    
    # Add lost submissions (lower priority - 60% confidence but still included)
    lost_submissions = [s for s in existing_submissions if len(s) > 5 and s[5] == 'lost']
    if lost_submissions:
        existing_summary += "LOST RFP SUBMISSIONS (Lower Priority - 60% Confidence - Include but weight lower):\n"
        existing_summary += "Note: These might have had good answers but lost for non-RFP reasons (budget, politics, timing, etc.)\n"
        for submission in lost_submissions[:2]:  # Top 2 lost submissions
            existing_summary += f"❌ LOST - RFP: {submission[1]}\n"
            existing_summary += f"Company: {submission[2] or 'Unknown'}\n"
            existing_summary += f"Confidence: 60% (Lost but might have good content)\n"
            if submission[4]:  # extracted_data
                try:
                    data = json.loads(submission[4])
                    for category, info in data.items():
                        if info and isinstance(info, (str, dict)):
                            existing_summary += f"{category}: {str(info)[:200]}...\n"
                except:
                    pass
            existing_summary += "\n---\n"
        existing_summary += "\n"
    
    prompt = f"""
    You are helping to fill out a new RFP based on previous submissions with smart confidence weighting.
    
    {existing_summary}
    
    New RFP content:
    {new_content[:4000]}
    
    IMPORTANT CONFIDENCE WEIGHTING RULES:
    - CORRECTED ANSWERS: 100% confidence (user improved these)
    - WINNING RFPs: 95% confidence (proven to work)
    - UNKNOWN/PENDING: 80% confidence (might be good, include them)
    - LOST RFPs: 60% confidence (include but weight lower - might have lost for non-RFP reasons)
    
    Please analyze the new RFP and suggest answers based on the previous submissions.
    Prioritize winning and corrected answers, but include all relevant content with appropriate confidence scores.
    Don't ignore lost RFPs completely - they might have had great answers that just didn't win for other reasons.
    
    For each question or section in the new RFP, provide:
    1. The question/section identified
    2. A suggested answer based on previous submissions
    3. A confidence score (0-100) based on the source RFP's win status
    4. The source RFP that provided the best answer
    5. The source RFP's win status
    
    Format your response as JSON with this structure:
    {{
        "matches": [
            {{
                "question": "question text",
                "suggested_answer": "answer text",
                "confidence": 85,
                "source_rfp": "filename.pdf",
                "category": "company_info|technical|business|etc",
                "source_status": "won|lost|unknown|pending|corrected"
            }}
        ],
        "overall_confidence": 75
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert at matching RFP questions with existing answers. Always respond with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=3000
        )
        
        return json.loads(response.choices[0].message.content)
        
    except Exception as e:
        return {"matches": [], "confidence": 0, "error": str(e)}

# Main Streamlit app
def main():
    # Check authentication first
    if not check_authentication():
        login_page()
        return
    
    st.title("📋 RFP Database System")
    st.markdown("AI-powered RFP database for automatic answer extraction and matching")
    
    # Initialize OpenAI client
    client = init_openai()
    
    # Sidebar navigation
    st.sidebar.title("Navigation")
    
    # Add logout button at the top
    if st.sidebar.button("🚪 Logout", type="secondary"):
        st.session_state.authenticated = False
        st.rerun()
    
    st.sidebar.markdown("---")
    
    page = st.sidebar.selectbox(
        "Choose a page",
        ["Dashboard", "Upload Historical RFP", "Process New RFP", "Upload Corrected RFP", "Browse Database", "Search", "Export Data"]
    )
    
    if page == "Dashboard":
        show_dashboard()
    elif page == "Upload Historical RFP":
        show_upload_page(client)
    elif page == "Process New RFP":
        show_process_page(client)
    elif page == "Upload Corrected RFP":
        show_corrected_upload_page(client)
    elif page == "Browse Database":
        show_browse_page()
    elif page == "Search":
        show_search_page()
    elif page == "Export Data":
        show_export_page()

def show_dashboard():
    """Show the main dashboard"""
    st.header("Dashboard")
    
    # Get statistics
    submissions = get_all_submissions()
    
    # Calculate win/loss metrics
    won_count = len([s for s in submissions if len(s) > 5 and s[5] == 'won'])
    lost_count = len([s for s in submissions if len(s) > 5 and s[5] == 'lost'])
    pending_count = len([s for s in submissions if len(s) > 5 and s[5] == 'pending'])
    unknown_count = len([s for s in submissions if len(s) <= 5 or s[5] == 'unknown'])
    
    total_deals = won_count + lost_count + pending_count
    win_rate = (won_count / total_deals * 100) if total_deals > 0 else 0
    total_deal_value = sum(s[6] for s in submissions if len(s) > 6 and s[6] and s[5] == 'won')
    
    # Broker analytics
    broker_stats = {}
    for submission in submissions:
        broker = submission[8] if len(submission) > 8 and submission[8] else 'Direct/Unknown'
        if broker not in broker_stats:
            broker_stats[broker] = {'total': 0, 'won': 0, 'lost': 0, 'pending': 0, 'deal_value': 0}
        
        broker_stats[broker]['total'] += 1
        win_status = submission[5] if len(submission) > 5 else 'unknown'
        if win_status == 'won':
            broker_stats[broker]['won'] += 1
            if len(submission) > 6 and submission[6]:
                broker_stats[broker]['deal_value'] += submission[6]
        elif win_status == 'lost':
            broker_stats[broker]['lost'] += 1
        elif win_status == 'pending':
            broker_stats[broker]['pending'] += 1
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Submissions", len(submissions))
    
    with col2:
        st.metric("Win Rate", f"{win_rate:.1f}%", f"{won_count}/{total_deals}")
    
    with col3:
        st.metric("Won Deals", won_count, f"${total_deal_value:,.0f}" if total_deal_value > 0 else "")
    
    with col4:
        st.metric("Database Status", "✅ Active")
    
    # Win/Loss breakdown
    if total_deals > 0:
        st.subheader("📊 Win/Loss Analytics")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("🏆 Won", won_count, f"{win_rate:.1f}%")
        with col2:
            st.metric("❌ Lost", lost_count)
        with col3:
            st.metric("⏳ Pending", pending_count)
        with col4:
            st.metric("❓ Unknown", unknown_count)
        
        # Win rate chart
        if won_count > 0 or lost_count > 0:
            chart_data = pd.DataFrame({
                'Status': ['Won', 'Lost', 'Pending', 'Unknown'],
                'Count': [won_count, lost_count, pending_count, unknown_count]
            })
            st.bar_chart(chart_data.set_index('Status'))
    
    # Broker analytics
    if broker_stats:
        st.subheader("🏢 Broker/Consultant Analytics")
        
        # Create broker performance table
        broker_data = []
        for broker, stats in broker_stats.items():
            broker_win_rate = (stats['won'] / (stats['won'] + stats['lost']) * 100) if (stats['won'] + stats['lost']) > 0 else 0
            broker_data.append({
                'Broker/Consultant': broker,
                'Total RFPs': stats['total'],
                'Won': stats['won'],
                'Lost': stats['lost'],
                'Pending': stats['pending'],
                'Win Rate': f"{broker_win_rate:.1f}%",
                'Deal Value': f"${stats['deal_value']:,.0f}" if stats['deal_value'] > 0 else "N/A"
            })
        
        broker_df = pd.DataFrame(broker_data)
        st.dataframe(broker_df, use_container_width=True)
        
        # Broker performance chart
        if len(broker_stats) > 1:
            chart_data = pd.DataFrame({
                'Broker': list(broker_stats.keys()),
                'Win Rate': [(stats['won'] / (stats['won'] + stats['lost']) * 100) if (stats['won'] + stats['lost']) > 0 else 0 for stats in broker_stats.values()]
            })
            st.bar_chart(chart_data.set_index('Broker'))
    
    # Recent submissions with win status
    st.subheader("Recent Submissions")
    if submissions:
        # Show last 5 submissions with win status
        recent_submissions = submissions[-5:]
        for submission in reversed(recent_submissions):
            win_status = submission[5] if len(submission) > 5 else 'unknown'
            status_emoji = {"won": "🏆", "lost": "❌", "pending": "⏳", "unknown": "❓"}.get(win_status, "❓")
            deal_info = f" (${submission[6]:,.0f})" if len(submission) > 6 and submission[6] and win_status == 'won' else ""
            st.write(f"{status_emoji} **{submission[1]}** - {submission[2] or 'Unknown Company'} ({submission[3].strftime('%Y-%m-%d') if hasattr(submission[3], 'strftime') else submission[3]}){deal_info}")
    else:
        st.info("No submissions found. Upload some historical RFPs to get started!")

def show_upload_page(client):
    """Show the RFP upload page"""
    st.header("Upload Historical RFP")
    st.markdown("Upload historical RFP documents to build your knowledge base")
    
    uploaded_file = st.file_uploader(
        "Choose an RFP file",
        type=['pdf', 'docx', 'txt'],
        help="Supported formats: PDF, DOCX, TXT"
    )
    
    if uploaded_file is not None:
        st.info(f"Selected file: {uploaded_file.name}")
        
        if st.button("Upload and Process", type="primary"):
            with st.spinner("Processing document..."):
                # Extract text
                content = extract_text_from_file(uploaded_file.read(), uploaded_file.name)
                
                if content.startswith("Error") or content == "Unsupported file format":
                    st.error(f"❌ {content}")
                    return
                
                # Extract data with AI
                extracted_data = extract_rfp_data_with_ai(content, client)
                
                # Extract company name
                company_name = None
                if isinstance(extracted_data, dict) and "Company Information" in extracted_data:
                    company_info = extracted_data["Company Information"]
                    if isinstance(company_info, dict) and "Company name" in company_info:
                        company_name = company_info["Company name"]
                
                # Win/Loss tracking
                st.subheader("📊 Win/Loss Tracking")
                st.markdown("**Help the system learn from your success!**")
                
                col1, col2 = st.columns(2)
                with col1:
                    win_status = st.selectbox(
                        "Was this proposal successful?",
                        ["unknown", "won", "lost", "pending"],
                        format_func=lambda x: {
                            "unknown": "❓ Unknown/Not sure",
                            "won": "🏆 Won the deal!",
                            "lost": "❌ Lost the deal",
                            "pending": "⏳ Still pending"
                        }[x]
                    )
                
                with col2:
                    deal_value = None
                    win_date = None
                    if win_status == "won":
                        deal_value = st.number_input("Deal Value ($)", min_value=0.0, step=1000.0, help="Enter the deal value in dollars")
                        win_date = st.date_input("Win Date", value=datetime.now().date())
                
                # Broker/Consultant tracking
                st.subheader("🏢 Broker/Consultant Information")
                st.markdown("**Track which broker or consultant brought this opportunity**")
                
                broker_consultant = st.text_input(
                    "Broker/Consultant Name", 
                    placeholder="e.g., Mercer, Alliant, Willis Towers Watson, etc.",
                    help="Leave blank if direct client or unknown"
                )
                
                if broker_consultant:
                    st.info(f"📊 This will help track success patterns for **{broker_consultant}**")
                
                # Save to database
                save_rfp_submission(uploaded_file.name, content, extracted_data, company_name, win_status=win_status, deal_value=deal_value, win_date=win_date.strftime('%Y-%m-%d') if win_date else None, broker_consultant=broker_consultant if broker_consultant else None)
                
                st.success("✅ Document uploaded and processed successfully!")
                
                # Show extracted data
                st.subheader("Extracted Information")
                st.json(extracted_data)

def show_process_page(client):
    """Show the new RFP processing page"""
    st.header("Process New RFP")
    st.markdown("Upload a new RFP to get AI-suggested answers based on your historical submissions")
    
    uploaded_file = st.file_uploader(
        "Choose a new RFP file",
        type=['pdf', 'docx', 'txt'],
        help="Upload a new RFP to get suggested answers"
    )
    
    if uploaded_file is not None:
        st.info(f"Selected file: {uploaded_file.name}")
        
        if st.button("Process RFP", type="primary"):
            with st.spinner("Analyzing RFP and finding matching answers..."):
                # Extract text
                content = extract_text_from_file(uploaded_file.read(), uploaded_file.name)
                
                if content.startswith("Error") or content == "Unsupported file format":
                    st.error(f"❌ {content}")
                    return
                
                # Get existing submissions
                existing_submissions = get_all_submissions()
                
                # Find matching answers
                matches = find_matching_answers(content, existing_submissions, client)
                
                st.success("✅ RFP processed successfully!")
                
                # Display results
                st.subheader("Suggested Answers")
                
                if matches.get("matches"):
                    for i, match in enumerate(matches["matches"]):
                        with st.expander(f"Question {i+1}: {match.get('question', 'N/A')[:100]}..."):
                            st.write(f"**Suggested Answer:** {match.get('suggested_answer', 'N/A')}")
                            st.write(f"**Confidence:** {match.get('confidence', 0)}%")
                            st.write(f"**Source:** {match.get('source_rfp', 'N/A')}")
                            st.write(f"**Category:** {match.get('category', 'N/A')}")
                else:
                    st.info("No matching answers found. Upload more historical RFPs to improve matching.")
                
                # Download results
                if matches:
                    results_json = json.dumps(matches, indent=2)
                    st.download_button(
                        label="📥 Download Results",
                        data=results_json,
                        file_name=f"rfp_analysis_{uploaded_file.name}.json",
                        mime="application/json"
                    )

def show_corrected_upload_page(client):
    """Show the corrected RFP upload page"""
    st.header("Upload Corrected RFP")
    st.markdown("Upload your edited/corrected RFP to help the system learn from your improvements")
    
    # Get list of recent RFPs for reference
    submissions = get_all_submissions()
    
    if not submissions:
        st.warning("⚠️ No RFPs found. Please upload some historical RFPs first.")
        return
    
    st.subheader("Step 1: Select Original RFP")
    rfp_options = {f"{sub[1]} - {sub[2] or 'Unknown Company'}": sub[0] for sub in submissions}
    selected_rfp = st.selectbox("Which RFP did you correct?", list(rfp_options.keys()))
    original_rfp_id = rfp_options[selected_rfp]
    
    st.subheader("Step 2: Upload Corrected RFP")
    uploaded_file = st.file_uploader(
        "Choose your corrected RFP file",
        type=['pdf', 'docx', 'txt'],
        help="Upload the RFP with your corrections and improvements"
    )
    
    if uploaded_file is not None:
        st.info(f"Selected file: {uploaded_file.name}")
        
        st.subheader("Step 3: Review Corrections")
        st.markdown("**Please review the extracted information and make any final adjustments:**")
        
        # Extract text from corrected file
        content = extract_text_from_file(uploaded_file.read(), uploaded_file.name)
        
        if content.startswith("Error") or content == "Unsupported file format":
            st.error(f"❌ {content}")
            return
        
        # Extract data with AI
        extracted_data = extract_rfp_data_with_ai(content, client)
        
        # Show extracted data for review
        st.json(extracted_data)
        
        st.subheader("Step 4: Save Corrected Answers")
        st.markdown("**The system will learn from your corrections to improve future suggestions.**")
        
        if st.button("Save Corrected RFP", type="primary"):
            with st.spinner("Saving corrected RFP and updating knowledge base..."):
                # Extract company name
                company_name = None
                if isinstance(extracted_data, dict) and "Company Information" in extracted_data:
                    company_info = extracted_data["Company Information"]
                    if isinstance(company_info, dict) and "Company name" in company_info:
                        company_name = company_info["Company name"]
                
                # Save as corrected submission
                save_rfp_submission(
                    f"corrected_{uploaded_file.name}", 
                    content, 
                    extracted_data, 
                    company_name, 
                    is_corrected=True, 
                    original_rfp_id=original_rfp_id
                )
                
                # Extract corrected answers for learning
                corrected_answers = []
                if isinstance(extracted_data, dict):
                    for category, data in extracted_data.items():
                        if data and isinstance(data, dict):
                            for key, value in data.items():
                                if value and isinstance(value, str):
                                    corrected_answers.append({
                                        'category': category,
                                        'question': key,
                                        'corrected_answer': value
                                    })
                
                # Save corrected answers for future learning
                if corrected_answers:
                    save_corrected_answers(original_rfp_id, corrected_answers)
                
                st.success("✅ Corrected RFP saved successfully!")
                st.info("🧠 The system has learned from your corrections and will use them to improve future suggestions.")
                
                # Show what was learned
                st.subheader("What the System Learned:")
                for answer in corrected_answers[:5]:  # Show first 5
                    st.write(f"**{answer['category']} - {answer['question']}:** {answer['corrected_answer'][:100]}...")
                
                if len(corrected_answers) > 5:
                    st.write(f"... and {len(corrected_answers) - 5} more corrections")

def show_browse_page():
    """Show the database browsing page"""
    st.header("Browse RFP Database")
    
    submissions = get_all_submissions()
    
    if not submissions:
        st.info("No submissions found. Upload some historical RFPs to get started!")
        return
    
    st.subheader("📊 RFP Management")
    st.markdown("View and update win/loss status for your RFPs")
    
    # Create a more detailed DataFrame
    df_data = []
    for sub in submissions:
        win_status = sub[5] if len(sub) > 5 else 'unknown'
        deal_value = sub[6] if len(sub) > 6 and sub[6] else None
        win_date = sub[7] if len(sub) > 7 and sub[7] else None
        
        df_data.append({
            "ID": sub[0],
            "Filename": sub[1],
            "Company": sub[2] or "Unknown",
            "Created": sub[3],
            "Win Status": win_status,
            "Deal Value": f"${deal_value:,.0f}" if deal_value else "N/A",
            "Win Date": win_date or "N/A"
        })
    
    df = pd.DataFrame(df_data)
    
    # Display the dataframe
    st.dataframe(df, use_container_width=True)
    
    # Win/Loss status update section
    st.subheader("🔄 Update Win/Loss Status")
    
    # Select RFP to update
    rfp_options = {f"{sub[1]} - {sub[2] or 'Unknown'}": sub[0] for sub in submissions}
    selected_rfp = st.selectbox("Select RFP to update:", list(rfp_options.keys()))
    rfp_id = rfp_options[selected_rfp]
    
    # Get current status
    current_submission = next(s for s in submissions if s[0] == rfp_id)
    current_status = current_submission[5] if len(current_submission) > 5 else 'unknown'
    current_deal_value = current_submission[6] if len(current_submission) > 6 and current_submission[6] else None
    current_win_date = current_submission[7] if len(current_submission) > 7 and current_submission[7] else None
    
    col1, col2 = st.columns(2)
    
    with col1:
        new_status = st.selectbox(
            "Update Status:",
            ["unknown", "won", "lost", "pending"],
            index=["unknown", "won", "lost", "pending"].index(current_status),
            format_func=lambda x: {
                "unknown": "❓ Unknown/Not sure",
                "won": "🏆 Won the deal!",
                "lost": "❌ Lost the deal",
                "pending": "⏳ Still pending"
            }[x]
        )
    
    with col2:
        new_deal_value = None
        new_win_date = None
        if new_status == "won":
            new_deal_value = st.number_input(
                "Deal Value ($)", 
                min_value=0.0, 
                step=1000.0, 
                value=current_deal_value or 0.0,
                help="Enter the deal value in dollars"
            )
            new_win_date = st.date_input(
                "Win Date", 
                value=datetime.strptime(current_win_date, '%Y-%m-%d').date() if current_win_date else datetime.now().date()
            )
    
    if st.button("Update Status", type="primary"):
        with st.spinner("Updating status..."):
            update_win_status(
                rfp_id, 
                new_status, 
                new_deal_value if new_deal_value and new_deal_value > 0 else None,
                new_win_date.strftime('%Y-%m-%d') if new_win_date else None
            )
            st.success("✅ Status updated successfully!")
            st.rerun()
    
    # Detailed view section
    st.subheader("📄 Detailed View")
    for submission in submissions:
        win_status = submission[5] if len(submission) > 5 else 'unknown'
        status_emoji = {"won": "🏆", "lost": "❌", "pending": "⏳", "unknown": "❓"}.get(win_status, "❓")
        
        with st.expander(f"{status_emoji} {submission[1]} - {submission[2] or 'Unknown Company'}"):
            st.write(f"**Uploaded:** {submission[3]}")
            st.write(f"**Company:** {submission[2] or 'Not specified'}")
            st.write(f"**Win Status:** {win_status.upper()}")
            
            if len(submission) > 6 and submission[6]:
                st.write(f"**Deal Value:** ${submission[6]:,.0f}")
            if len(submission) > 7 and submission[7]:
                st.write(f"**Win Date:** {submission[7]}")
            
            if submission[4]:  # extracted_data
                try:
                    data = json.loads(submission[4])
                    st.write("**Extracted Information:**")
                    st.json(data)
                except:
                    st.write("**Raw Data:**", submission[4])

def show_search_page():
    """Show the search page"""
    st.header("Search RFP Database")
    
    search_query = st.text_input("Enter search terms", placeholder="Search by filename, company, or content")
    
    if search_query:
        if st.button("Search"):
            with st.spinner("Searching..."):
                results = search_submissions(search_query)
            
            if results:
                st.success(f"Found {len(results)} results")
                
                for result in results:
                    with st.expander(f"📄 {result[1]} - {result[2] or 'Unknown Company'}"):
                        st.write(f"**Company:** {result[2] or 'Not specified'}")
                        st.write(f"**Uploaded:** {result[3]}")
                        
                        if result[4]:  # extracted_data
                            try:
                                data = json.loads(result[4])
                                st.write("**Extracted Information:**")
                                st.json(data)
                            except:
                                st.write("**Raw Data:**", result[4])
            else:
                st.info("No results found")

def show_export_page():
    """Show the export page"""
    st.header("📊 Export Data")
    st.markdown("Export your RFP data for analysis and reporting")
    
    submissions = get_all_submissions()
    
    if not submissions:
        st.info("No data to export. Upload some RFPs first!")
        return
    
    # Prepare export data
    export_data = []
    for submission in submissions:
        win_status = submission[5] if len(submission) > 5 else 'unknown'
        deal_value = submission[6] if len(submission) > 6 and submission[6] else None
        win_date = submission[7] if len(submission) > 7 and submission[7] else None
        broker_consultant = submission[8] if len(submission) > 8 and submission[8] else None
        
        export_data.append({
            'ID': submission[0],
            'Filename': submission[1],
            'Company': submission[2] or 'Unknown',
            'Created Date': submission[3],
            'Win Status': win_status,
            'Deal Value': deal_value or 0,
            'Win Date': win_date or '',
            'Broker/Consultant': broker_consultant or 'Direct/Unknown',
            'Is Corrected': submission[4] if len(submission) > 4 else False
        })
    
    df = pd.DataFrame(export_data)
    
    st.subheader("📋 Export Options")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**📈 All Data Export**")
        st.markdown("Complete dataset with all RFP information")
        
        # Convert to CSV
        csv_data = df.to_csv(index=False)
        
        st.download_button(
            label="📥 Download All Data (CSV)",
            data=csv_data,
            file_name=f"rfp_database_export_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    
    with col2:
        st.markdown("**🏆 Winning RFPs Only**")
        st.markdown("Export only successful proposals for analysis")
        
        winning_df = df[df['Win Status'] == 'won']
        if not winning_df.empty:
            winning_csv = winning_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Winners (CSV)",
                data=winning_csv,
                file_name=f"winning_rfps_export_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        else:
            st.info("No winning RFPs to export yet")
    
    st.subheader("🏢 Broker-Specific Exports")
    
    # Get unique brokers
    brokers = df['Broker/Consultant'].unique()
    brokers = [b for b in brokers if b != 'Direct/Unknown']
    
    if brokers:
        selected_broker = st.selectbox("Select broker/consultant:", brokers)
        
        broker_df = df[df['Broker/Consultant'] == selected_broker]
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Total RFPs", len(broker_df))
            st.metric("Won", len(broker_df[broker_df['Win Status'] == 'won']))
        
        with col2:
            won_deals = broker_df[broker_df['Win Status'] == 'won']
            total_value = won_deals['Deal Value'].sum()
            win_rate = (len(won_deals) / len(broker_df[broker_df['Win Status'].isin(['won', 'lost'])]) * 100) if len(broker_df[broker_df['Win Status'].isin(['won', 'lost'])]) > 0 else 0
            
            st.metric("Win Rate", f"{win_rate:.1f}%")
            st.metric("Total Deal Value", f"${total_value:,.0f}")
        
        # Export broker data
        broker_csv = broker_df.to_csv(index=False)
        st.download_button(
            label=f"📥 Download {selected_broker} Data (CSV)",
            data=broker_csv,
            file_name=f"{selected_broker.replace(' ', '_')}_rfps_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.info("No broker/consultant data to export yet")
    
    st.subheader("📊 Data Preview")
    st.dataframe(df, use_container_width=True)

if __name__ == "__main__":
    main()
