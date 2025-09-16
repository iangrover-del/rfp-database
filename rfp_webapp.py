import streamlit as st
import os
import tempfile
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Any
import sqlite3
from pathlib import Path
import openai
from docx import Document
import PyPDF2
import io
import hashlib
import secrets
import time

# Excel support will be checked when needed
EXCEL_SUPPORT = None  # Will be determined dynamically

def check_excel_support():
    """Check if Excel libraries are available"""
    global EXCEL_SUPPORT
    if EXCEL_SUPPORT is None:
        try:
            import openpyxl
            import xlrd
            EXCEL_SUPPORT = True
        except ImportError:
            EXCEL_SUPPORT = False
    return EXCEL_SUPPORT

# Authentication functions
def hash_password(password: str) -> str:
    """Hash a password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    return hash_password(password) == hashed

def check_authentication():
    """Check if user is authenticated with session timeout"""
    # Initialize session state if not exists
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'login_time' not in st.session_state:
        st.session_state.login_time = None
    if 'session_token' not in st.session_state:
        st.session_state.session_token = None
    
    # Check if user is authenticated
    if st.session_state.authenticated and st.session_state.login_time:
        # Check if session has expired (2 hours = 7200 seconds)
        current_time = time.time()
        session_duration = 2 * 60 * 60  # 2 hours in seconds
        
        if current_time - st.session_state.login_time > session_duration:
            # Session expired
            st.session_state.authenticated = False
            st.session_state.login_time = None
            st.session_state.session_token = None
            st.warning("⏰ Your session has expired. Please log in again.")
            return False
        else:
            # Session is still valid
            remaining_time = session_duration - (current_time - st.session_state.login_time)
            remaining_minutes = int(remaining_time / 60)
            
            # Show session info in sidebar (only if less than 30 minutes remaining)
            if remaining_minutes < 30:
                st.sidebar.info(f"⏰ Session expires in {remaining_minutes} minutes")
            
            return True
    
    # Try to restore session from URL parameters (for page refreshes)
    if 'session_token' in st.query_params and st.query_params['session_token']:
        # Validate session token (simple check for now)
        try:
            token_data = st.query_params['session_token']
            # Simple validation - in production you'd want more security
            if len(token_data) > 10:  # Basic validation
                st.session_state.authenticated = True
                st.session_state.login_time = time.time()
                st.session_state.session_token = token_data
                return True
        except:
            pass
    
    return False

def check_public_access():
    """Check if the app is publicly accessible and show warning"""
    # Check if we're running on Streamlit Cloud
    try:
        # This will work on Streamlit Cloud
        if hasattr(st, '_is_running_with_streamlit') and st._is_running_with_streamlit:
            st.error("🚨 **SECURITY WARNING**: This app is publicly accessible!")
            st.warning("Anyone with the URL can access your RFP database. Consider adding additional security measures.")
            
            # Suggest security improvements
            with st.expander("🔒 Security Recommendations"):
                st.markdown("""
                **To secure your app:**
                1. **Change the default password** in Streamlit Cloud secrets
                2. **Use a strong, unique password**
                3. **Don't share the URL** publicly
                4. **Monitor who has access**
                
                **Current password:** `rfp2024` (change this!)
                """)
            
            return True
    except:
        pass
    return False

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
                # Generate session token
                session_token = secrets.token_urlsafe(32)
                st.session_state.authenticated = True
                st.session_state.login_time = time.time()  # Record login time
                st.session_state.session_token = session_token
                
                # Set URL parameter to maintain session across refreshes
                st.query_params.session_token = session_token
                
                st.success("✅ Login successful! Your session will last 2 hours.")
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

def test_openai_connection(client):
    """Test OpenAI API connection with a simple request"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Respond with a simple JSON object containing a 'status' field set to 'ok'."},
                {"role": "user", "content": "Test connection"}
            ],
            temperature=0.1,
            max_tokens=50
        )
        
        content = response.choices[0].message.content
        if content and content.strip():
            try:
                result = json.loads(content)
                return True, "API connection successful"
            except:
                return True, f"API responded but with invalid JSON: {content[:100]}"
        else:
            return False, "API returned empty response"
            
    except Exception as e:
        return False, f"API connection failed: {str(e)}"

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

def delete_rfp_submission(rfp_id: int):
    """Delete an RFP submission and all related data"""
    conn = init_database()
    cursor = conn.cursor()
    
    try:
        # Delete related answers first (foreign key constraint)
        cursor.execute('DELETE FROM rfp_answers WHERE source_rfp_id = ?', (rfp_id,))
        
        # Delete the main submission
        cursor.execute('DELETE FROM rfp_submissions WHERE id = ?', (rfp_id,))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        return False
    finally:
        conn.close()

def rename_rfp_submission(rfp_id: int, new_filename: str):
    """Rename an RFP submission filename"""
    conn = init_database()
    cursor = conn.cursor()
    
    try:
        # Check if the new filename already exists
        cursor.execute('SELECT id FROM rfp_submissions WHERE filename = ? AND id != ?', (new_filename, rfp_id))
        if cursor.fetchone():
            return False, "A file with this name already exists"
        
        # Update the filename
        cursor.execute('UPDATE rfp_submissions SET filename = ? WHERE id = ?', (new_filename, rfp_id))
        
        conn.commit()
        return True, "Filename updated successfully"
    except Exception as e:
        conn.rollback()
        return False, f"Error updating filename: {str(e)}"
    finally:
        conn.close()

def get_all_submissions():
    """Get all RFP submissions"""
    conn = init_database()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, filename, company_name, created_at, extracted_data, win_status, deal_value, win_date, broker_consultant
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
        SELECT id, filename, company_name, created_at, extracted_data, win_status, deal_value, win_date, broker_consultant
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
        elif file_extension in ['xlsx', 'xls']:
            if check_excel_support():
                return extract_excel_content(file_content, file_extension)
            else:
                return "Excel support not available. Please convert to PDF or DOCX format."
        elif file_extension == 'csv':
            return extract_csv_content(file_content)
        else:
            return "Unsupported file format"
    except Exception as e:
        return f"Error extracting text: {str(e)}"

def extract_excel_content(file_content: bytes, file_extension: str) -> str:
    """Extract content from Excel files, handling Q&A format and multiple tabs"""
    try:
        # Create a temporary file to work with
        with tempfile.NamedTemporaryFile(suffix=f'.{file_extension}', delete=False) as tmp_file:
            tmp_file.write(file_content)
            tmp_file_path = tmp_file.name
        
        try:
            # Read Excel file and get all sheet names
            if file_extension == 'xlsx':
                excel_file = pd.ExcelFile(tmp_file_path, engine='openpyxl')
            else:  # xls
                excel_file = pd.ExcelFile(tmp_file_path, engine='xlrd')
            
            sheet_names = excel_file.sheet_names
            text_content = f"EXCEL FILE PROCESSING: Found {len(sheet_names)} sheet(s): {', '.join(sheet_names)}\n\n"
            
            # Process each sheet
            for sheet_name in sheet_names:
                df = pd.read_excel(tmp_file_path, sheet_name=sheet_name, engine=excel_file.engine)
                
                # Skip empty sheets
                if df.empty:
                    continue
                
                # Add sheet header
                if len(sheet_names) > 1:
                    text_content += f"\n=== SHEET: {sheet_name} ===\n"
                else:
                    text_content += f"\n=== SHEET: {sheet_name} ===\n"
                
                text_content += f"Sheet dimensions: {df.shape[0]} rows x {df.shape[1]} columns\n"
                text_content += f"Sheet content preview: {str(df.head(3).to_dict())}\n\n"
                
                # Check if this looks like a Q&A format (questions in one column, answers in next)
                if len(df.columns) >= 2:
                    # Look for patterns that suggest Q&A format
                    first_col = df.iloc[:, 0].astype(str).str.lower()
                    second_col = df.iloc[:, 1].astype(str).str.lower()
                    
                    # Check if first column contains questions (has question marks, starts with question words)
                    has_questions = first_col.str.contains(r'\?|what|how|when|where|why|who|which', na=False).any()
                    has_answers = second_col.str.len().mean() > 20  # Answers are typically longer
                    
                    if has_questions and has_answers:
                        # Format as Q&A pairs
                        text_content += "RFP QUESTIONS AND ANSWERS:\n\n"
                        for idx, row in df.iterrows():
                            question = str(row.iloc[0]).strip()
                            answer = str(row.iloc[1]).strip()
                            
                            if question and answer and question != 'nan' and answer != 'nan':
                                text_content += f"Q: {question}\n"
                                text_content += f"A: {answer}\n\n"
                    else:
                        # Check if this is a question table (like "Network Questions" with "Vendor Response")
                        table_headers = [str(col).lower() for col in df.columns]
                        is_question_table = any(keyword in ' '.join(table_headers) for keyword in 
                                              ['question', 'vendor response', 'response', 'answer', 'requirement'])
                        
                        if is_question_table:
                            # Format as structured question table
                            text_content += "RFP QUESTION TABLE:\n\n"
                            # Add column headers
                            header_row = " | ".join([str(col) for col in df.columns])
                            text_content += f"HEADERS: {header_row}\n\n"
                            
                            # Process each row as a question
                            for idx, row in df.iterrows():
                                row_data = []
                                for cell in row:
                                    cell_str = str(cell).strip()
                                    if cell_str and cell_str != 'nan':
                                        row_data.append(cell_str)
                                
                                if row_data:
                                    # Format as structured question
                                    if len(row_data) >= 2:
                                        text_content += f"TABLE QUESTION: {row_data[0]}\n"
                                        text_content += f"RESPONSE FIELD: {row_data[1] if len(row_data) > 1 else 'N/A'}\n"
                                        if len(row_data) > 2:
                                            text_content += f"ADDITIONAL INFO: {' | '.join(row_data[2:])}\n"
                                        text_content += "\n"
                                    else:
                                        text_content += f"TABLE ITEM: {' | '.join(row_data)}\n"
                        else:
                            # Standard table format
                            text_content += "RFP DATA:\n\n"
                            for idx, row in df.iterrows():
                                row_text = " | ".join([str(cell) for cell in row if str(cell) != 'nan'])
                                if row_text.strip():
                                    text_content += row_text + "\n"
                else:
                    # Single column or simple format
                    text_content += "RFP CONTENT:\n\n"
                    for idx, row in df.iterrows():
                        row_text = " ".join([str(cell) for cell in row if str(cell) != 'nan'])
                        if row_text.strip():
                            text_content += row_text + "\n"
                
                # Add separator between sheets
                if len(sheet_names) > 1:
                    text_content += "\n" + "="*50 + "\n"
            
            # Add final summary
            text_content += f"\n\n=== EXCEL PROCESSING COMPLETE ===\n"
            text_content += f"Total sheets processed: {len(sheet_names)}\n"
            text_content += f"Total content length: {len(text_content)} characters\n"
            text_content += f"Content preview (first 2000 chars): {text_content[:2000]}...\n"
            text_content += f"Content preview (last 2000 chars): ...{text_content[-2000:]}\n"
            
            return text_content
            
        finally:
            # Clean up temporary file
            os.unlink(tmp_file_path)
            
    except Exception as e:
        return f"Error processing Excel file: {str(e)}"

def extract_csv_content(file_content: bytes) -> str:
    """Extract content from CSV files, handling Q&A format"""
    try:
        # Decode the CSV content
        csv_content = file_content.decode('utf-8')
        
        # Read CSV using pandas
        from io import StringIO
        df = pd.read_csv(StringIO(csv_content))
        
        text_content = "RFP DATA (CSV):\n\n"
        
        # Check if this looks like a Q&A format (questions in one column, answers in next)
        if len(df.columns) >= 2:
            # Look for patterns that suggest Q&A format
            first_col = df.iloc[:, 0].astype(str).str.lower()
            second_col = df.iloc[:, 1].astype(str).str.lower()
            
            # Check if first column contains questions (has question marks, starts with question words)
            has_questions = first_col.str.contains(r'\?|what|how|when|where|why|who|which', na=False).any()
            has_answers = second_col.str.len().mean() > 20  # Answers are typically longer
            
            if has_questions and has_answers:
                # Format as Q&A pairs
                text_content += "RFP QUESTIONS AND ANSWERS:\n\n"
                for idx, row in df.iterrows():
                    question = str(row.iloc[0]).strip()
                    answer = str(row.iloc[1]).strip()
                    
                    if question and answer and question != 'nan' and answer != 'nan':
                        text_content += f"Q: {question}\n"
                        text_content += f"A: {answer}\n\n"
            else:
                # Standard table format
                text_content += "RFP DATA:\n\n"
                for idx, row in df.iterrows():
                    row_text = " | ".join([str(cell) for cell in row if str(cell) != 'nan'])
                    if row_text.strip():
                        text_content += row_text + "\n"
        else:
            # Single column or simple format
            text_content += "RFP CONTENT:\n\n"
            for idx, row in df.iterrows():
                row_text = " ".join([str(cell) for cell in row if str(cell) != 'nan'])
                if row_text.strip():
                    text_content += row_text + "\n"
        
        return text_content
        
    except Exception as e:
        return f"Error processing CSV file: {str(e)}"

def extract_rfp_data_with_ai(content: str, client) -> Dict[str, Any]:
    """Extract structured data from RFP using AI"""
    
    # Use smaller chunks to avoid token limit issues
    # Process in smaller chunks with better overlap for comprehensive extraction
    chunk_size = 8000  # Reduced from 12000 to avoid token limits
    overlap = 2000     # Increased overlap for better question capture
    
    chunks = []
    for i in range(0, len(content), chunk_size - overlap):
        chunk = content[i:i+chunk_size]
        chunks.append(chunk)
        if i + chunk_size >= len(content):
            break
    
    all_questions = []
    sheets_analyzed = set()
    pages_analyzed = set()
    
    # Debug info
    print(f"DEBUG: Total content length: {len(content)} characters")
    print(f"DEBUG: Split into {len(chunks)} chunks")
    for i, chunk in enumerate(chunks):
        print(f"DEBUG: Chunk {i+1}: {len(chunk)} characters")
    
    for i, chunk in enumerate(chunks):
        prompt = f"""
        You are an expert RFP response extraction specialist. Your task is to extract BOTH questions and their corresponding answers from this RFP response document.
        
        CRITICAL INSTRUCTIONS:
        1. This document contains RFP RESPONSES (answers to questions), not just questions
        2. Extract EVERY question-answer pair from the document
        3. For each question, find the corresponding answer that was provided
        4. Include questions that end with "?" AND questions that don't end with "?"
        5. Look for question-answer patterns in tables, forms, and structured sections
        6. Extract questions from headers, bullet points, and numbered items
        7. Find the answers that correspond to each question
        8. If a question doesn't have a clear answer, note that
        9. Be EXTREMELY thorough - extract everything that could be considered a question-answer pair
        10. Look for questions in ALL formats: paragraphs, lists, tables, forms, checkboxes
        11. Extract questions that are embedded in longer text
        12. Look for questions that start with action words like "Describe", "Explain", "Provide", "List", "Detail"
        13. Include questions that are part of larger statements
        14. Look for questions in section headers and subheaders
        15. Extract questions from any text that asks for specific information, details, or responses
        
        WHAT TO EXTRACT (be extremely inclusive - extract EVERYTHING that asks for information):
        - Direct questions ending with "?"
        - Requests starting with "What", "How", "When", "Where", "Why", "Who", "Which", "Describe", "Explain", "Provide", "List", "Please", "Can you", "Do you", "Are you", "Will you"
        - Numbered items that ask for information (even without "?")
        - Bullet points that ask for information
        - Table headers that ask for information
        - Any text that requests specific details, information, or responses
        - Form fields that need to be filled out
        - Requirements that need to be addressed
        - Sections that ask for documentation or evidence
        - Instructions that ask for specific information
        - Prompts that require responses
        - Any text that ends with a colon and asks for information
        - Any text that says "include", "provide", "submit", "attach", "complete", "fill out"
        - Any text that asks for "details", "information", "processes", "procedures", "requirements"
        - Any text that asks for "outline", "describe", "explain", "specify", "detail", "clarify"
        - Any text that asks for "standards", "processes", "delivery times", "fees", "costs"
        - Any text that asks for "capabilities", "experience", "qualifications", "certifications"
        - Any text that asks for "references", "examples", "case studies", "testimonials"
        - Any text that asks for "timeline", "schedule", "deadlines", "milestones"
        - Any text that asks for "team", "staff", "personnel", "resources"
        - Any text that asks for "technology", "systems", "platforms", "tools"
        - Any text that asks for "security", "compliance", "privacy", "data protection"
        - Any text that asks for "support", "maintenance", "training", "documentation"
        
        EXAMPLES OF WHAT TO EXTRACT:
        - "What is your company's annual revenue?"
        - "How many employees do you serve?"
        - "Describe your technology platform"
        - "Please provide your company background"
        - "List your key capabilities"
        - "Can you provide references?"
        - "1. Company Information:" (if it's asking for company info)
        - "• Experience with financial services:" (if it's asking for experience)
        - "Vendor Qualifications:" (if it's asking for qualifications)
        - "Complete the following table:" (if it's asking to fill out a table)
        - "Submit the following documents:" (if it's asking for documents)
        - "Network Questions: Provider count for mental health services"
        - "Vendor Response: Average wait times for appointments"
        - "Requirements: Technology platform capabilities"
        - "Response Field: Implementation timeline"
        - "Please provide evidence of..." (even without "?")
        - "Include details about..." (even without "?")
        - "Detail the experience for someone who meets the visit limit"
        - "What happens after they exhaust their employer sponsored sessions?"
        - "Please outline your eligibility file requirements"
        - "Please include as an attachment your standard eligibility file data request"
        - "Please provide your definition of dependents"
        - "Please clearly note who is eligible for the EAP services"
        - "Please provide any standard leave of absence (LOA) process flows"
        - "Please provide any standards/process/delivery time for Fitness-for-duty"
        - "Please ensure that any fees are included in the financial template"
        - "Can you provide a sample log-in for Barclays to demo your capabilities?"
        
        RESPONSE FORMAT (JSON only):
        {{
            "question_answer_pairs": [
                {{
                    "question": "Exact question 1 as written in document",
                    "answer": "Exact answer provided for question 1"
                }},
                {{
                    "question": "Exact question 2 as written in document", 
                    "answer": "Exact answer provided for question 2"
                }}
            ],
            "question_count": "total number of question-answer pairs found in this chunk",
            "sheets_analyzed": "list of sheet names analyzed (for Excel files)",
            "pages_analyzed": "list of page numbers analyzed (for PDFs)"
        }}
        
        CRITICAL: Extract BOTH the question AND the corresponding answer. If no answer is found for a question, use "No answer provided" as the answer. Do NOT include index numbers, ranges, or placeholder text.
        
        Document chunk {i+1} of {len(chunks)}:
        {chunk}
        """
        
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an expert RFP question extraction specialist. Your ONLY task is to find and list EVERY SINGLE QUESTION, REQUEST, or INFORMATION REQUIREMENT from this document chunk. Go through the chunk word by word and extract the exact wording of every question, request, or information requirement. Be very inclusive - include questions that don't end with '?' and implicit requests for information. Do not summarize, do not paraphrase, do not categorize, do not group similar questions. List every question separately. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=3000  # Reduced to be more conservative with token limits
            )
            
            # Get the response content
            response_content = response.choices[0].message.content
            
            # Check if response is empty
            if not response_content or response_content.strip() == "":
                continue
            
            # Try to extract JSON from the response
            try:
                # First try to extract JSON from markdown code blocks
                if "```json" in response_content:
                    json_start = response_content.find("```json") + 7
                    json_end = response_content.find("```", json_start)
                    if json_end != -1:
                        json_str = response_content[json_start:json_end].strip()
                    else:
                        json_str = response_content[json_start:].strip()
                elif "```" in response_content:
                    json_start = response_content.find("```") + 3
                    json_end = response_content.find("```", json_start)
                    if json_end != -1:
                        json_str = response_content[json_start:json_end].strip()
                    else:
                        json_str = response_content[json_start:].strip()
                else:
                    # Try to find JSON object boundaries
                    json_start = response_content.find("{")
                    json_end = response_content.rfind("}") + 1
                    if json_start != -1 and json_end > json_start:
                        json_str = response_content[json_start:json_end]
                    else:
                        json_str = response_content
                
                # Parse the JSON
                chunk_data = json.loads(json_str)
                
                # Extract question-answer pairs from this chunk
                if "question_answer_pairs" in chunk_data:
                    chunk_pairs = chunk_data["question_answer_pairs"]
                    print(f"DEBUG: Chunk {i+1} found {len(chunk_pairs)} question-answer pairs")
                    # Store both questions and answers
                    for pair in chunk_pairs:
                        if isinstance(pair, dict) and "question" in pair and "answer" in pair:
                            all_questions.append({
                                "question": pair["question"],
                                "answer": pair["answer"]
                            })
                    print(f"DEBUG: Chunk {i+1} processed {len(chunk_pairs)} pairs")
                elif "all_questions_found" in chunk_data:
                    # Fallback for old format
                    chunk_questions = chunk_data["all_questions_found"]
                    print(f"DEBUG: Chunk {i+1} found {len(chunk_questions)} questions (old format)")
                    # Filter out index-only entries and keep only actual question text
                    actual_questions = [q for q in chunk_questions if isinstance(q, str) and not q.startswith('[') and not q.endswith(']')]
                    all_questions.extend(actual_questions)
                    print(f"DEBUG: Chunk {i+1} actual questions: {len(actual_questions)}")
                
                # Track sheets and pages analyzed
                if "sheets_analyzed" in chunk_data:
                    sheets_data = chunk_data["sheets_analyzed"]
                    if isinstance(sheets_data, str):
                        sheets_analyzed.update(sheets_data.split(", ") if sheets_data else [])
                    elif isinstance(sheets_data, list):
                        sheets_analyzed.update(sheets_data)
                
                if "pages_analyzed" in chunk_data:
                    pages_data = chunk_data["pages_analyzed"]
                    if isinstance(pages_data, str):
                        pages_analyzed.update(pages_data.split(", ") if pages_data else [])
                    elif isinstance(pages_data, list):
                        pages_analyzed.update(pages_data)
                    
            except json.JSONDecodeError as e:
                # If JSON parsing fails, return error with raw response
                return {
                    "error": f"AI returned invalid JSON for chunk {i+1}",
                    "json_error": str(e),
                    "raw_response": response_content
                }
            except Exception as e:
                return {
                    "error": f"Error processing chunk {i+1}: {str(e)}",
                    "raw_response": response_content
                }
        
        except Exception as e:
            return {
                "error": f"Failed to process chunk {i+1}: {str(e)}"
            }
    
    # Combine all results
    final_result = {
        "all_questions_found": all_questions,
        "question_count": len(all_questions),
        "sheets_analyzed": list(sheets_analyzed) if sheets_analyzed else [],
        "pages_analyzed": list(pages_analyzed) if pages_analyzed else [],
        "debug_info": {
            "total_chunks": len(chunks),
            "chunk_sizes": [len(chunk) for chunk in chunks],
            "total_content_length": len(content)
        }
    }
    
    return final_result

def extract_numbered_questions(content: str) -> List[str]:
    """Extract all numbered questions from content, filtering out table questions from PDFs"""
    import re
    
    questions = []
    
    # Look for patterns like "1.", "2.", "3.", etc.
    pattern1 = r'^(\d+)\.\s+(.+)$'
    matches1 = re.findall(pattern1, content, re.MULTILINE)
    for num, question in matches1:
        # Skip table questions from PDFs
        if is_table_question(question):
            continue
        questions.append(f"{num}. {question.strip()}")
    
    # Look for patterns like "1)", "2)", "3)", etc.
    pattern2 = r'^(\d+)\)\s+(.+)$'
    matches2 = re.findall(pattern2, content, re.MULTILINE)
    for num, question in matches2:
        # Skip table questions from PDFs
        if is_table_question(question):
            continue
        questions.append(f"{num}) {question.strip()}")
    
    # Look for patterns like "1:", "2:", "3:", etc.
    pattern3 = r'^(\d+):\s+(.+)$'
    matches3 = re.findall(pattern3, content, re.MULTILINE)
    for num, question in matches3:
        # Skip table questions from PDFs
        if is_table_question(question):
            continue
        questions.append(f"{num}: {question.strip()}")
    
    # Sort by number
    questions.sort(key=lambda x: int(re.search(r'^(\d+)', x).group(1)))
    
    return questions

def is_table_question(question: str) -> bool:
    """Check if a question is asking for table completion (which we should skip for PDFs)"""
    question_lower = question.lower()
    
    # Table-related keywords that indicate this is a table question
    table_indicators = [
        'complete the table',
        'fill in the table',
        'table below',
        'table above',
        'table on page',
        'table in',
        'complete table',
        'fill table',
        'table based on',
        'table and provide',
        'table with',
        'table showing',
        'table including'
    ]
    
    return any(indicator in question_lower for indicator in table_indicators)

def find_matching_answers_semantic(questions: List[str], existing_submissions: List) -> Dict[str, Any]:
    """Find matching answers using semantic similarity and intelligent matching"""
    
    if not existing_submissions:
        return {
            "matches": [], 
            "confidence": 0,
            "error": "No historical RFPs found in database. Please upload some historical RFPs first to build a knowledge base.",
            "suggestion": "Go to 'Upload Historical RFPs' to add your past successful proposals."
        }
    
    matches = []
    
    # Extract all question-answer pairs from historical submissions
    all_qa_pairs = []
    for submission in existing_submissions:
        if len(submission) > 4 and submission[4]:
            try:
                data = json.loads(submission[4])
                
                # Try different data formats
                print(f"DEBUG: Processing {submission[1]}, data keys: {list(data.keys())}")
                
                # Let's see the raw data structure
                st.write(f"**DEBUG: {submission[1]} data keys:** {list(data.keys())}")
                if 'question_answer_pairs' in data:
                    st.write(f"**DEBUG: Found {len(data['question_answer_pairs'])} question_answer_pairs**")
                elif 'all_questions_found' in data:
                    st.write(f"**DEBUG: Found {len(data['all_questions_found'])} all_questions_found**")
                else:
                    st.write(f"**DEBUG: Unknown format, showing first few keys:**")
                    for key, value in list(data.items())[:3]:
                        st.write(f"  - {key}: {type(value)} with {len(value) if isinstance(value, (list, dict)) else 'N/A'} items")
                
                if 'question_answer_pairs' in data:
                    # Format 1: question_answer_pairs
                    print(f"DEBUG: Found question_answer_pairs in {submission[1]}, count: {len(data['question_answer_pairs'])}")
                    for pair in data['question_answer_pairs']:
                        if isinstance(pair, dict) and 'question' in pair and 'answer' in pair:
                            all_qa_pairs.append({
                                'question': pair['question'],
                                'answer': pair['answer'],
                                'source': submission[1],
                                'status': submission[5] if len(submission) > 5 else 'unknown'
                            })
                elif 'all_questions_found' in data:
                    # Format 2: all_questions_found (might actually contain Q&A pairs)
                    print(f"DEBUG: Found all_questions_found in {submission[1]}, checking for Q&A pairs...")
                    questions_found = data['all_questions_found']
                    if isinstance(questions_found, list) and len(questions_found) > 0:
                        # Check if the first item is a dict with question and answer
                        if isinstance(questions_found[0], dict) and 'question' in questions_found[0] and 'answer' in questions_found[0]:
                            print(f"DEBUG: Found Q&A pairs in all_questions_found! Count: {len(questions_found)}")
                            for pair in questions_found:
                                if isinstance(pair, dict) and 'question' in pair and 'answer' in pair:
                                    all_qa_pairs.append({
                                        'question': pair['question'],
                                        'answer': pair['answer'],
                                        'source': submission[1],
                                        'status': submission[5] if len(submission) > 5 else 'unknown'
                                    })
                        else:
                            print(f"DEBUG: all_questions_found contains questions only, skipping...")
                else:
                    # Format 3: Try to extract from raw content
                    print(f"DEBUG: Unknown data format in {submission[1]}, keys: {list(data.keys())}")
                    # Let's see what's actually in the data
                    for key, value in data.items():
                        if isinstance(value, list) and len(value) > 0:
                            print(f"DEBUG: Key '{key}' has {len(value)} items, first item type: {type(value[0])}")
                            if isinstance(value[0], dict):
                                print(f"DEBUG: First item keys: {list(value[0].keys())}")
                    
            except Exception as e:
                print(f"DEBUG: Error parsing submission {submission[1]}: {e}")
                continue
    
    print(f"DEBUG: Found {len(all_qa_pairs)} question-answer pairs from historical RFPs")
    print(f"DEBUG: This message should appear in the console/logs")
    if all_qa_pairs:
        print(f"DEBUG: First Q&A pair: Q: {all_qa_pairs[0]['question'][:100]}... A: {all_qa_pairs[0]['answer'][:100]}...")
    else:
        print("DEBUG: No Q&A pairs found - checking data structure...")
        for i, submission in enumerate(existing_submissions[:2]):
            print(f"DEBUG: Submission {i+1}: {submission[1]}")
            if len(submission) > 4 and submission[4]:
                try:
                    data = json.loads(submission[4])
                    print(f"DEBUG: Data keys: {list(data.keys())}")
                    if 'question_answer_pairs' in data:
                        print(f"DEBUG: Found {len(data['question_answer_pairs'])} pairs in this submission")
                    else:
                        print("DEBUG: No 'question_answer_pairs' key found")
                except Exception as e:
                    print(f"DEBUG: Error parsing data: {e}")
    
    # For each new question, find the best matching answer
    print(f"DEBUG: Processing {len(questions)} questions, limiting to first 10")
    used_answers = set()  # Track used answers to avoid duplicates
    
    for i, question in enumerate(questions[:10]):  # Limit to first 10
        print(f"DEBUG: Processing question {i+1}: {question[:100]}...")
        best_match = None
        best_score = 0
        
        # Use semantic similarity matching
        question_lower = question.lower()
        question_type = classify_question_type(question_lower)
        
        for qa_pair in all_qa_pairs:
            # Skip if we've already used this answer
            answer_hash = hash(qa_pair['answer'][:200])  # Use first 200 chars as hash
            if answer_hash in used_answers:
                continue
                
            # Calculate semantic similarity score
            score = calculate_semantic_score(question, qa_pair['question'], qa_pair['answer'], question_type)
            
            if score > best_score:
                best_score = score
                best_match = qa_pair
                print(f"DEBUG: New best match (score {score:.3f}): {qa_pair['answer'][:100]}...")
        
        if best_match and best_score > 0.4:  # Higher threshold for better quality matches
            # Mark this answer as used
            answer_hash = hash(best_match['answer'][:200])
            used_answers.add(answer_hash)
            
            # Clean brand names from the answer
            cleaned_answer = clean_brand_names(best_match['answer'])
            
            matches.append({
                "question": question,
                "suggested_answer": cleaned_answer,
                "confidence": min(95, int(best_score * 100)),
                "source_rfp": best_match['source'],
                "category": "matched",
                "source_status": best_match['status'],
                "matching_reason": f"Semantic match (score: {best_score:.3f})"
            })
        else:
            # Provide a more helpful fallback answer based on question type
            fallback_answer = get_fallback_answer(question, question_type)
            matches.append({
                "question": question,
                "suggested_answer": fallback_answer,
                "confidence": 10,
                "source_rfp": "None",
                "category": "no_match",
                "source_status": "unknown",
                "matching_reason": "No semantic match found"
            })
    
    return {
        "matches": matches,
        "overall_confidence": sum(m['confidence'] for m in matches) // len(matches) if matches else 0,
        "total_questions_found": len(questions),
        "questions_answered": len(matches),
        "debug_info": {
            "qa_pairs_found": len(all_qa_pairs),
            "submissions_processed": len(existing_submissions),
            "first_qa_pair": all_qa_pairs[0] if all_qa_pairs else None
        }
    }

def classify_question_type(question_lower: str) -> str:
    """Classify the type of question for better matching"""
    if any(word in question_lower for word in ['network', 'provider', 'coach', 'therapist', 'coverage', 'table']):
        return 'network'
    elif any(word in question_lower for word in ['timeline', 'implementation', 'plan', 'launch', 'deploy']):
        return 'timeline'
    elif any(word in question_lower for word in ['eligibility', 'dependent', 'file', 'requirements']):
        return 'eligibility'
    elif any(word in question_lower for word in ['demo', 'sample', 'login', 'capabilities', 'show']):
        return 'demo'
    elif any(word in question_lower for word in ['visit', 'limit', 'enrolled', 'medical', 'exhaust', 'session']):
        return 'visit_limit'
    elif any(word in question_lower for word in ['leave', 'absence', 'loa', 'cism', 'manager', 'referral']):
        return 'loa_cism'
    elif any(word in question_lower for word in ['fitness', 'duty', 'standard', 'process', 'delivery']):
        return 'fitness_duty'
    elif any(word in question_lower for word in ['geo', 'access', 'census', 'pricing']):
        return 'geo_access'
    elif any(word in question_lower for word in ['wait', 'time', 'appointment', 'average']):
        return 'wait_times'
    else:
        return 'general'

def calculate_semantic_score(new_question: str, historical_question: str, historical_answer: str, question_type: str) -> float:
    """Calculate semantic similarity score between new question and historical Q&A"""
    new_q_lower = new_question.lower()
    hist_q_lower = historical_question.lower()
    hist_a_lower = historical_answer.lower()
    
    score = 0.0
    
    # 1. Direct question similarity (highest weight)
    question_similarity = calculate_text_similarity(new_q_lower, hist_q_lower)
    score += question_similarity * 0.7  # 70% weight on question similarity
    
    # 2. Answer relevance to question type
    answer_relevance = calculate_answer_relevance(hist_a_lower, question_type)
    score += answer_relevance * 0.3  # 30% weight on answer relevance
    
    # 3. Boost for exact phrase matches
    if 'fitness-for-duty' in new_q_lower and ('fitness' in hist_a_lower or 'duty' in hist_a_lower):
        score += 0.4
    if 'visit limit' in new_q_lower and 'visit limit' in hist_a_lower:
        score += 0.4
    if 'implementation timeline' in new_q_lower and 'implementation' in hist_a_lower:
        score += 0.4
    if 'loa' in new_q_lower and ('loa' in hist_a_lower or 'leave of absence' in hist_a_lower):
        score += 0.4
    if 'table' in new_q_lower and 'table' in hist_a_lower:
        score += 0.4
    if 'geo access' in new_q_lower and ('geo' in hist_a_lower or 'access' in hist_a_lower):
        score += 0.4
    if 'demo' in new_q_lower and ('demo' in hist_a_lower or 'sample' in hist_a_lower):
        score += 0.4
    
    # 4. Special handling for specific question patterns
    if 'complete the table' in new_q_lower and 'network' in new_q_lower:
        # This is a network table question - boost network-related answers
        if any(word in hist_a_lower for word in ['network', 'provider', 'coach', 'therapist', 'coverage', 'access']):
            score += 0.3
        # Look for table-like data in the answer
        if any(word in hist_a_lower for word in ['table', 'data', 'numbers', 'count', 'total', 'providers']):
            score += 0.2
    
    if 'geo access' in new_q_lower or 'census' in new_q_lower:
        # This is a geo access question - boost geographic/access answers
        if any(word in hist_a_lower for word in ['geo', 'access', 'census', 'pricing', 'location', 'coverage']):
            score += 0.3
        if any(word in hist_a_lower for word in ['global', 'worldwide', 'countries', 'regions']):
            score += 0.2
    
    if 'wait times' in new_q_lower or 'appointment' in new_q_lower:
        # This is a wait time question - boost timing-related answers
        if any(word in hist_a_lower for word in ['wait', 'time', 'appointment', 'schedule', 'availability']):
            score += 0.3
        if any(word in hist_a_lower for word in ['hours', 'days', 'minutes', 'immediate', '24/7']):
            score += 0.2
    
    if 'demo' in new_q_lower and 'sample' in new_q_lower:
        # This is a demo question - boost demo-related answers
        if any(word in hist_a_lower for word in ['demo', 'sample', 'login', 'capabilities', 'show', 'demonstrate']):
            score += 0.3
        if any(word in hist_a_lower for word in ['access', 'platform', 'app', 'system']):
            score += 0.2
    
    # 4. Heavy penalties for completely wrong answers
    if question_type == 'network' and 'table' in new_q_lower:
        # Network table question should NOT get suicide/self-harm answers
        if any(word in hist_a_lower for word in ['suicide', 'self-harm', 'crisis', 'emergency', 'risk']):
            score -= 0.8
        # Should have network/provider info
        if not any(word in hist_a_lower for word in ['network', 'provider', 'coach', 'therapist', 'coverage']):
            score -= 0.5
    
    elif question_type == 'geo_access':
        # Geo access question should NOT get eligibility answers
        if any(word in hist_a_lower for word in ['eligibility', 'dependent', 'file', 'requirements']):
            score -= 0.6
        # Should have geo/access info
        if not any(word in hist_a_lower for word in ['geo', 'access', 'census', 'pricing', 'location']):
            score -= 0.4
    
    elif question_type == 'fitness_duty':
        # Fitness-for-duty should NOT get partnership/strategic answers
        if any(word in hist_a_lower for word in ['partnership', 'strategic', 'alignment', 'communication', 'goals']):
            score -= 0.7
        # Should have fitness/duty info
        if not any(word in hist_a_lower for word in ['fitness', 'duty', 'standard', 'process', 'delivery']):
            score -= 0.5
    
    elif question_type == 'demo':
        # Demo question should NOT get training answers
        if any(word in hist_a_lower for word in ['training', 'webinar', 'onboarding', 'workshop']):
            score -= 0.6
        # Should have demo/sample info
        if not any(word in hist_a_lower for word in ['demo', 'sample', 'login', 'capabilities', 'show']):
            score -= 0.4
    
    elif question_type == 'wait_times':
        # Wait times question should NOT get general service descriptions
        if any(word in hist_a_lower for word in ['access', 'unlimited', '24/7', 'global']):
            score -= 0.3
        # Should have wait time info
        if not any(word in hist_a_lower for word in ['wait', 'time', 'appointment', 'average', 'schedule']):
            score -= 0.4
    
    return max(0.0, min(1.0, score))  # Clamp between 0 and 1

def calculate_text_similarity(text1: str, text2: str) -> float:
    """Calculate similarity between two texts using word overlap and semantic understanding"""
    words1 = set(text1.split())
    words2 = set(text2.split())
    
    if not words1 or not words2:
        return 0.0
    
    # Basic word overlap
    common_words = words1.intersection(words2)
    overlap_score = len(common_words) / max(len(words1), len(words2))
    
    # Boost for important keywords with higher weights
    important_keywords = {
        'network': 0.3, 'provider': 0.3, 'coach': 0.3, 'therapist': 0.3,
        'timeline': 0.3, 'implementation': 0.3, 'plan': 0.2,
        'eligibility': 0.3, 'dependent': 0.2, 'file': 0.2,
        'demo': 0.3, 'sample': 0.3, 'login': 0.2,
        'visit': 0.3, 'limit': 0.3, 'enrolled': 0.2,
        'loa': 0.3, 'leave': 0.2, 'absence': 0.2,
        'fitness': 0.3, 'duty': 0.3, 'standard': 0.2,
        'geo': 0.3, 'access': 0.3, 'census': 0.2,
        'wait': 0.3, 'time': 0.2, 'appointment': 0.2,
        'table': 0.3, 'complete': 0.2
    }
    
    keyword_boost = 0.0
    for word, weight in important_keywords.items():
        if word in words1 and word in words2:
            keyword_boost += weight
    
    return min(1.0, overlap_score + keyword_boost)

def get_fallback_answer(question: str, question_type: str) -> str:
    """Provide a helpful fallback answer when no good match is found"""
    if question_type == 'network':
        return "Modern Health maintains a global network of licensed therapists, coaches, and mental health professionals. Please provide specific network details based on your current provider data."
    elif question_type == 'timeline':
        return "Modern Health typically implements programs within 4-6 weeks. Please provide your specific implementation timeline and plan details."
    elif question_type == 'eligibility':
        return "Modern Health works with clients to determine eligibility requirements. Please provide your specific eligibility file requirements and dependent definitions."
    elif question_type == 'demo':
        return "Modern Health can provide demo access and sample logins. Please contact your account manager to arrange a demonstration of our platform capabilities."
    elif question_type == 'visit_limit':
        return "Modern Health provides flexible visit limits and coverage options. Please provide specific details about visit limits and coverage for non-enrolled members."
    elif question_type == 'fitness_duty':
        return "Modern Health can provide information about fitness-for-duty processes and standards. Please provide specific details about your fitness-for-duty requirements and delivery times."
    elif question_type == 'loa_cism':
        return "Modern Health supports leave of absence processes and critical incident stress management. Please provide specific details about your LOA process flows and CISM requirements."
    elif question_type == 'geo_access':
        return "Modern Health provides global access to mental health services. Please provide specific geographic access requirements and census data details."
    elif question_type == 'wait_times':
        return "Modern Health provides rapid access to care with industry-leading wait times. Please provide specific wait time requirements and appointment scheduling details."
    else:
        return "No specific answer found in historical RFPs. Please provide a custom answer based on your specific requirements."

def clean_brand_names(text: str) -> str:
    """Remove competitor brand names from text"""
    # List of competitor names to remove
    brand_names = [
        'Henry Schein', 'Voya Financial', 'Voya', 'Barclays', 'Boston Scientific', 
        'Mattel', 'Sunrun', 'Stripe', 'Uber', 'Palo Alto Networks', 'Electronic Arts'
    ]
    
    cleaned_text = text
    for brand in brand_names:
        # Remove brand name and any following punctuation
        cleaned_text = cleaned_text.replace(brand, '[Client]')
        cleaned_text = cleaned_text.replace(brand.lower(), '[client]')
        cleaned_text = cleaned_text.replace(brand.upper(), '[CLIENT]')
    
    return cleaned_text

def calculate_answer_relevance(answer: str, question_type: str) -> float:
    """Calculate how relevant an answer is to a specific question type"""
    if question_type == 'network':
        network_keywords = ['network', 'provider', 'coach', 'therapist', 'coverage', 'access']
        return sum(0.2 for keyword in network_keywords if keyword in answer)
    elif question_type == 'timeline':
        timeline_keywords = ['timeline', 'implementation', 'plan', 'launch', 'deploy', 'schedule']
        return sum(0.2 for keyword in timeline_keywords if keyword in answer)
    elif question_type == 'eligibility':
        eligibility_keywords = ['eligibility', 'dependent', 'file', 'requirements', 'coverage']
        return sum(0.2 for keyword in eligibility_keywords if keyword in answer)
    elif question_type == 'fitness_duty':
        fitness_keywords = ['fitness', 'duty', 'standard', 'process', 'delivery', 'time']
        return sum(0.2 for keyword in fitness_keywords if keyword in answer)
    elif question_type == 'loa_cism':
        loa_keywords = ['leave', 'absence', 'loa', 'cism', 'manager', 'referral', 'process']
        return sum(0.2 for keyword in loa_keywords if keyword in answer)
    else:
        return 0.5  # Default relevance for general questions

def find_matching_answers_with_questions(questions: List[str], existing_submissions: List, client) -> Dict[str, Any]:
    """Find matching answers for pre-processed questions"""
    
    if not existing_submissions:
        return {
            "matches": [], 
            "confidence": 0,
            "error": "No historical RFPs found in database. Please upload some historical RFPs first to build a knowledge base.",
            "suggestion": "Go to 'Upload Historical RFPs' to add your past successful proposals."
        }
    
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
    
    # Debug: Print what we're working with
    print(f"DEBUG: Found {len(existing_submissions)} existing submissions")
    for i, sub in enumerate(existing_submissions[:3]):  # Show first 3
        print(f"DEBUG: Submission {i+1}: {sub[1]} | Content length: {len(str(sub[4])) if len(sub) > 4 and sub[4] else 0}")
        if len(sub) > 4 and sub[4]:
            try:
                data = json.loads(sub[4])
                print(f"DEBUG: Data keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
            except:
                print(f"DEBUG: Could not parse data")
    
    # Add won submissions (highest priority - 95% confidence) - limit to first 2
    won_submissions = [s for s in existing_submissions if len(s) > 5 and s[5] == 'won'][:2]
    if won_submissions:
        existing_summary += "WON RFP SUBMISSIONS (Highest Priority - 95% Confidence - Use these first):\n"
        for i, submission in enumerate(won_submissions):
            existing_summary += f"RFP {i+1}: {submission[1]}\n"
            existing_summary += f"Confidence: 95% (Proven winner)\n"
            if submission[4]:  # extracted_data or extracted_answers
                try:
                    data = json.loads(submission[4])
                    # Check for new question-answer format
                    if 'question_answer_pairs' in data:
                        pairs = data['question_answer_pairs']
                        existing_summary += f"Question-answer pairs found: {len(pairs)}\n"
                        for i, pair in enumerate(pairs[:2]):  # Show first 2 pairs only
                            if isinstance(pair, dict):
                                existing_summary += f"Q{i+1}: {pair.get('question', 'N/A')[:80]}...\n"
                                existing_summary += f"A{i+1}: {pair.get('answer', 'N/A')[:150]}...\n"
                        if len(pairs) > 2:
                            existing_summary += f"... and {len(pairs) - 2} more question-answer pairs\n"
                    elif 'all_questions_found' in data:
                        existing_summary += f"Questions found: {len(data['all_questions_found'])}\n"
                        existing_summary += f"First 3 questions: {data['all_questions_found'][:3]}\n"
                        existing_summary += "NOTE: This appears to be question-only data. We need the actual RFP responses/answers.\n"
                    else:
                        # This might have actual content
                        existing_summary += f"Raw data keys: {list(data.keys())}\n"
                except:
                    pass
            existing_summary += "\n---\n"
        existing_summary += "\n"
    
    # Add unknown/pending submissions (medium priority - 80% confidence) - limit to first 2
    unknown_submissions = [s for s in existing_submissions if len(s) <= 5 or s[5] in ['unknown', 'pending']][:2]
    if unknown_submissions:
        existing_summary += "UNKNOWN/PENDING RFP SUBMISSIONS (Medium Priority - 80% Confidence - Include these):\n"
        for i, submission in enumerate(unknown_submissions):
            existing_summary += f"RFP {i+1}: {submission[1]}\n"
            existing_summary += f"Confidence: 80% (Unknown status)\n"
            if submission[4]:  # extracted_data or extracted_answers
                try:
                    data = json.loads(submission[4])
                    # Check for new question-answer format
                    if 'question_answer_pairs' in data:
                        pairs = data['question_answer_pairs']
                        existing_summary += f"Question-answer pairs found: {len(pairs)}\n"
                        for i, pair in enumerate(pairs[:2]):  # Show first 2 pairs only
                            if isinstance(pair, dict):
                                existing_summary += f"Q{i+1}: {pair.get('question', 'N/A')[:80]}...\n"
                                existing_summary += f"A{i+1}: {pair.get('answer', 'N/A')[:150]}...\n"
                        if len(pairs) > 2:
                            existing_summary += f"... and {len(pairs) - 2} more question-answer pairs\n"
                    elif 'all_questions_found' in data:
                        existing_summary += f"Questions found: {len(data['all_questions_found'])}\n"
                        existing_summary += f"First 3 questions: {data['all_questions_found'][:3]}\n"
                        existing_summary += "NOTE: This appears to be question-only data. We need the actual RFP responses/answers.\n"
                    else:
                        # This might have actual content
                        existing_summary += f"Raw data keys: {list(data.keys())}\n"
                except:
                    pass
            existing_summary += "\n---\n"
        existing_summary += "\n"
    
    # Create a simple questions list
    questions_text = "QUESTIONS TO ANSWER:\n"
    for i, question in enumerate(questions[:10]):  # Limit to first 10 questions
        questions_text += f"{i+1}. {question}\n"
    
    # Create a much simpler prompt
    prompt = f"""You have NEW RFP questions that need answers. Use the OLD RFP submissions below to find answers.

NEW QUESTIONS TO ANSWER:
{questions_text}

OLD RFP SUBMISSIONS (use these to find answers):
{existing_summary}

IMPORTANT: Answer the NEW questions above using answers from the OLD submissions. Do not extract questions from the old submissions.

Return JSON with one answer for each NEW question:
{{"matches": [{{"question": "NEW question from above", "suggested_answer": "answer from OLD submissions", "confidence": 90, "source_rfp": "filename.pdf", "category": "type", "source_status": "won", "matching_reason": "match reason"}}], "overall_confidence": 85}}"""
    
    try:
        # Debug: Print what we're sending to AI
        print(f"DEBUG: Sending to AI - existing_summary length: {len(existing_summary)}")
        print(f"DEBUG: Sending to AI - questions count: {len(questions)}")
        print(f"DEBUG: First 200 chars of existing_summary: {existing_summary[:200]}...")
        print(f"DEBUG: Total prompt length: {len(prompt)}")
        print(f"DEBUG: First 500 chars of prompt: {prompt[:500]}...")
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an RFP analyst. You have NEW questions that need answers. Use the OLD RFP submissions to find matching answers. Answer the NEW questions using answers from the OLD submissions. Return valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=4096
        )
        
        # Get the response content
        response_content = response.choices[0].message.content
        
        # Debug: Print the raw AI response
        print(f"DEBUG: Raw AI response: {response_content[:500]}...")
        
        # Check if response is empty
        if not response_content or response_content.strip() == "":
            return {"matches": [], "confidence": 0, "error": "AI returned empty response. This might be due to API quota limits or content filtering."}
        
        # Try to parse JSON
        try:
            return json.loads(response_content)
        except json.JSONDecodeError as json_error:
            return {"matches": [], "confidence": 0, "error": f"Failed to parse AI response as JSON: {json_error}"}
    
    except Exception as e:
        return {"matches": [], "confidence": 0, "error": f"Error calling AI: {str(e)}"}

def find_matching_answers(new_content: str, existing_submissions: List, client) -> Dict[str, Any]:
    """Find matching answers for new RFP"""
    
    if not existing_submissions:
        return {
            "matches": [], 
            "confidence": 0,
            "error": "No historical RFPs found in database. Please upload some historical RFPs first to build a knowledge base.",
            "suggestion": "Go to 'Upload Historical RFPs' to add your past successful proposals."
        }
    
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
    
    # Debug: Print what we're working with
    print(f"DEBUG: Found {len(existing_submissions)} existing submissions")
    for i, sub in enumerate(existing_submissions[:3]):  # Show first 3
        print(f"DEBUG: Submission {i+1}: {sub[1]} | Content length: {len(str(sub[4])) if len(sub) > 4 and sub[4] else 0}")
        if len(sub) > 4 and sub[4]:
            try:
                data = json.loads(sub[4])
                print(f"DEBUG: Data keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
            except:
                print(f"DEBUG: Could not parse data")
    
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
            if submission[4]:  # extracted_data or extracted_answers
                try:
                    data = json.loads(submission[4])
                    # Check for new question-answer format
                    if 'question_answer_pairs' in data:
                        pairs = data['question_answer_pairs']
                        existing_summary += f"Question-answer pairs found: {len(pairs)}\n"
                        for i, pair in enumerate(pairs[:3]):  # Show first 3 pairs
                            if isinstance(pair, dict):
                                existing_summary += f"Q{i+1}: {pair.get('question', 'N/A')[:100]}...\n"
                                existing_summary += f"A{i+1}: {pair.get('answer', 'N/A')[:200]}...\n"
                        if len(pairs) > 3:
                            existing_summary += f"... and {len(pairs) - 3} more question-answer pairs\n"
                    elif 'all_questions_found' in data:
                        existing_summary += f"Questions found: {len(data['all_questions_found'])}\n"
                        existing_summary += f"First 5 questions: {data['all_questions_found'][:5]}\n"
                        existing_summary += "NOTE: This appears to be question-only data. We need the actual RFP responses/answers.\n"
                    else:
                        # This might have actual content
                        existing_summary += f"Raw data keys: {list(data.keys())}\n"
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
            if submission[4]:  # extracted_data or extracted_answers
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
            if submission[4]:  # extracted_data or extracted_answers
                try:
                    data = json.loads(submission[4])
                    for category, info in data.items():
                        if info and isinstance(info, (str, dict)):
                            existing_summary += f"{category}: {str(info)[:200]}...\n"
                except:
                    pass
            existing_summary += "\n---\n"
        existing_summary += "\n"
    
    # Add a critical note about content requirements
    existing_summary += "🚨 CRITICAL INSTRUCTION: You MUST use the ACTUAL content from the submissions above. Do NOT provide generic suggestions. If there is ANY content in the submissions above that could be relevant to a question, use it. Even if it's not a perfect match, use the best available content. Only provide generic suggestions if there is absolutely NO content in the submissions above.\n\n"
    existing_summary += "🔥 ULTIMATE RULE: If you see ANY text in the submissions above that could answer a question, use that EXACT text. Do NOT paraphrase, do NOT summarize, do NOT create placeholder text. Use the ACTUAL words from the submissions.\n\n"
    existing_summary += "⚠️ IMPORTANT: The submissions above contain question-answer pairs with actual answers. You MUST use these answers when they are relevant to the new RFP questions. Do NOT say 'No specific answer found' if there is relevant content in the submissions above.\n\n"
    
    # Debug: Add information about what content is available
    existing_summary += f"DEBUG INFO: Total submissions available: {len(existing_submissions)}, Corrected answers: {len(corrected_answers) if corrected_answers else 0}\n"
    
    # Debug: Show actual content from submissions
    if existing_submissions:
        existing_summary += "ACTUAL CONTENT FROM SUBMISSIONS:\n"
        for i, sub in enumerate(existing_submissions[:3]):  # Show first 3 submissions
            existing_summary += f"Submission {i+1}: {sub[1]}\n"
            existing_summary += f"  Company: {sub[2] or 'Unknown'}\n"
            existing_summary += f"  Win Status: {sub[5] if len(sub) > 5 else 'unknown'}\n"
            existing_summary += f"  Raw data length: {len(str(sub[4])) if len(sub) > 4 and sub[4] else 0}\n"
            
            if len(sub) > 4 and sub[4]:  # extracted_data or extracted_answers
                try:
                    data = json.loads(sub[4])
                    if isinstance(data, dict):
                        existing_summary += f"  Data keys: {list(data.keys())}\n"
                        for key, value in data.items():
                            if value and isinstance(value, (str, dict)):
                                if isinstance(value, dict):
                                    existing_summary += f"  {key} (dict): {str(value)[:500]}...\n"
                                else:
                                    existing_summary += f"  {key}: {str(value)[:500]}...\n"
                    else:
                        existing_summary += f"  Content: {str(data)[:500]}...\n"
                except Exception as e:
                    existing_summary += f"  Error parsing content: {str(e)}\n"
                    existing_summary += f"  Raw content: {str(sub[4])[:500]}...\n"
            else:
                existing_summary += "  No content found\n"
            existing_summary += "\n"
    else:
        existing_summary += "NO SUBMISSIONS FOUND IN DATABASE!\n"
    
    existing_summary += "\n"
    
    # Debug: Show what we're sending to the AI
    print(f"DEBUG: Sending prompt to AI with {len(existing_summary)} characters of context")
    print(f"DEBUG: New content length: {len(new_content)}")
    print(f"DEBUG: Existing summary preview: {existing_summary[:500]}...")
    
    prompt = f"""
    You are an expert RFP analyst. Your job is to find answers from the previous submissions below to answer questions in the NEW RFP.
    
    PREVIOUS SUBMISSIONS WITH ANSWERS (use these to find answers):
    {existing_summary}
    
    ===== NEW RFP CONTENT TO ANALYZE =====
    {new_content}
    ===== END NEW RFP CONTENT =====

    CRITICAL INSTRUCTIONS:
    1. FIRST: Scan the "NEW RFP CONTENT TO ANALYZE" section and find ALL numbered questions
    2. SECOND: For each question, find the best matching answer from the previous submissions
    3. THIRD: Use the EXACT answer text from the previous submissions

    ⚠️ SYSTEMATIC QUESTION EXTRACTION:
    - Look for any line that starts with a number followed by a period (1., 2., 3., 4., 5., 6., 7., 8., 9., 10., 11., 12., 13., 14., 15., 16., 17., 18., 19., 20., 21., 22., 23., 24., 25., etc.)
    - Look for any line that starts with a number followed by a space and period (1 . 2 . 3 . etc.)
    - Look for any line that starts with a number in parentheses (1) 2) 3) etc.)
    - Look for any line that starts with a number followed by a colon (1: 2: 3: etc.)
    - Extract the complete question text that follows each number
    - Be systematic: go through the document line by line looking for these patterns

    ⚠️ ANSWER MATCHING: Be FLEXIBLE with matching - if the topic is even remotely related, use the answer. NEVER say "No specific answer found" - always find the most relevant answer from the submissions.

    Return JSON format:
    {{
        "matches": [
            {{
                "question": "question from NEW RFP",
                "suggested_answer": "actual answer from previous submissions",
                "confidence": 90,
                "source_rfp": "filename.pdf",
                "category": "company_info",
                "source_status": "won",
                "matching_reason": "similar topic"
            }}
        ],
        "overall_confidence": 85,
        "total_questions_found": [number of questions you found]
    }}
    
    NOTE: Be thorough and extract every numbered question you find in the document. Count them and report the total in total_questions_found.
    """
    
    try:
        # Debug: Print what we're sending to AI
        print(f"DEBUG: Sending to AI - existing_summary length: {len(existing_summary)}")
        print(f"DEBUG: Sending to AI - new_content length: {len(new_content)}")
        print(f"DEBUG: First 200 chars of existing_summary: {existing_summary[:200]}...")
        print(f"DEBUG: First 200 chars of new_content: {new_content[:200]}...")
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # Changed from gpt-4 to gpt-3.5-turbo for better compatibility
            messages=[
                {"role": "system", "content": "You are an expert RFP analyst. Your job is simple: find answers from previous submissions to answer new RFP questions. Use the exact answers from the previous submissions. Don't be picky about perfect matches - if the topic is similar, use the answer. Always respond with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,  # Balanced for good responses
            max_tokens=4000  # Fixed: gpt-3.5-turbo supports max 4096 tokens
        )
        
        # Get the response content
        response_content = response.choices[0].message.content
        
        # Debug: Print the raw AI response
        print(f"DEBUG: Raw AI response: {response_content[:500]}...")
        
        # Check if response is empty
        if not response_content or response_content.strip() == "":
            return {"matches": [], "confidence": 0, "error": "AI returned empty response. This might be due to API quota limits or content filtering."}
        
        # Try to parse JSON
        try:
            return json.loads(response_content)
        except json.JSONDecodeError as json_error:
            # Try to extract JSON from markdown code blocks
            try:
                # Look for JSON in markdown code blocks
                if "```json" in response_content:
                    # Extract content between ```json and ```
                    start = response_content.find("```json") + 7
                    end = response_content.find("```", start)
                    if end != -1:
                        json_content = response_content[start:end].strip()
                        return json.loads(json_content)
                elif "```" in response_content:
                    # Extract content between ``` and ```
                    start = response_content.find("```") + 3
                    end = response_content.find("```", start)
                    if end != -1:
                        json_content = response_content[start:end].strip()
                        return json.loads(json_content)
                
                # If no code blocks, try to find JSON object boundaries
                if "{" in response_content and "}" in response_content:
                    start = response_content.find("{")
                    end = response_content.rfind("}") + 1
                    json_content = response_content[start:end]
                    return json.loads(json_content)
                    
            except json.JSONDecodeError:
                pass
            
            # If all parsing attempts fail, return the raw response for debugging
            return {
                "matches": [],
                "confidence": 0,
                "error": f"AI returned invalid JSON. Raw response: {response_content[:500]}...",
                "json_error": str(json_error),
                "raw_response": response_content
            }
        
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
    
    # Show security warning if publicly accessible
    check_public_access()
    
    # Initialize OpenAI client
    client = init_openai()
    
    # Sidebar navigation
    st.sidebar.title("Navigation")
    
    # Add logout button at the top
    if st.sidebar.button("🚪 Logout", type="secondary"):
        st.session_state.authenticated = False
        st.session_state.login_time = None
        st.session_state.session_token = None
        # Clear URL parameter
        if 'session_token' in st.query_params:
            del st.query_params.session_token
        st.success("👋 Logged out successfully!")
        st.rerun()
    
    # Show session info
    if st.session_state.authenticated and st.session_state.login_time:
        current_time = time.time()
        session_duration = 2 * 60 * 60  # 2 hours
        remaining_time = session_duration - (current_time - st.session_state.login_time)
        remaining_minutes = int(remaining_time / 60)
        remaining_hours = int(remaining_minutes / 60)
        remaining_minutes = remaining_minutes % 60
        
        if remaining_hours > 0:
            session_display = f"{remaining_hours}h {remaining_minutes}m"
        else:
            session_display = f"{remaining_minutes}m"
        
        st.sidebar.info(f"🕐 Session: {session_display} remaining")
        
        # Add extend session button if less than 30 minutes remaining
        if remaining_time < 30 * 60:  # Less than 30 minutes
            if st.sidebar.button("⏰ Extend Session", type="secondary"):
                st.session_state.login_time = time.time()  # Reset login time
                st.success("✅ Session extended for another 2 hours!")
                st.rerun()
    
    st.sidebar.markdown("---")
    
    page = st.sidebar.selectbox(
        "Choose a page",
        ["Dashboard", "Upload Historical RFP", "Process New RFP", "Upload Corrected RFP", "Browse Database", "Search", "Export Data"]
    )
    
    if page == "Dashboard":
        show_dashboard(client)
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

def show_dashboard(client):
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
    
    # API Test section
    st.subheader("🔧 System Diagnostics")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🧪 Test OpenAI API Connection"):
            with st.spinner("Testing API connection..."):
                success, message = test_openai_connection(client)
                if success:
                    st.success(f"✅ {message}")
                else:
                    st.error(f"❌ {message}")
    
    with col2:
        if st.button("📊 Refresh Dashboard"):
            st.rerun()
    
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
    
    # Determine supported file types
    if check_excel_support():
        file_types = ['pdf', 'docx', 'txt', 'xlsx', 'xls', 'csv']
        help_text = "Supported formats: PDF, DOCX, TXT, Excel (XLSX, XLS), CSV"
    else:
        file_types = ['pdf', 'docx', 'txt', 'csv']
        help_text = "Supported formats: PDF, DOCX, TXT, CSV (Excel support not available)"
    
    uploaded_file = st.file_uploader(
        "Choose an RFP file",
        type=None,  # Allow all file types, we'll validate manually
        help=help_text,
        accept_multiple_files=False
    )
    
    if uploaded_file is not None:
        # Validate file type
        file_extension = uploaded_file.name.lower().split('.')[-1]
        if file_extension not in file_types:
            st.error(f"❌ Unsupported file type: {file_extension}. Please use one of: {', '.join(file_types)}")
            return
        
        st.info(f"Selected file: {uploaded_file.name}")
        
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
        
        if st.button("Upload and Process", type="primary"):
            with st.spinner("Processing document..."):
                # Extract text
                content = extract_text_from_file(uploaded_file.read(), uploaded_file.name)
                
                if content.startswith("Error") or content == "Unsupported file format":
                    st.error(f"❌ {content}")
                    return
                
                # Show raw extracted content for debugging
                st.subheader("🔍 Debug: Raw Extracted Content")
                st.write(f"**Total content length:** {len(content)} characters")
                st.text_area("Content preview (first 2000 chars):", content[:2000], height=200)
                st.text_area("Content preview (last 2000 chars):", content[-2000:], height=200)
                
                # Show chunking info
                chunk_size = 12000
                overlap = 2000
                chunks = []
                for i in range(0, len(content), chunk_size - overlap):
                    chunk = content[i:i+chunk_size]
                    chunks.append(chunk)
                    if i + chunk_size >= len(content):
                        break
                
                st.write(f"**Chunking Info:**")
                st.write(f"- Split into {len(chunks)} chunks")
                for i, chunk in enumerate(chunks):
                    st.write(f"- Chunk {i+1}: {len(chunk)} characters")
                
                # Extract data with AI
                extracted_data = extract_rfp_data_with_ai(content, client)
                
                # Check for errors in extraction
                if isinstance(extracted_data, dict) and "error" in extracted_data:
                    st.error(f"❌ **AI Processing Error:** {extracted_data['error']}")
                    
                    # Show additional debugging info if available
                    if "json_error" in extracted_data:
                        st.error(f"**JSON Error:** {extracted_data['json_error']}")
                    if "raw_response" in extracted_data:
                        with st.expander("🔍 Raw AI Response (for debugging)"):
                            st.text(extracted_data['raw_response'])
                    
                    st.info("💡 **Troubleshooting Tips:**")
                    st.markdown("""
                    - Check your OpenAI API key and billing status
                    - Ensure you have sufficient API credits
                    - Try uploading a smaller document
                    - The document might contain content that's being filtered
                    """)
                    return
                
                # Extract company name
                company_name = None
                if isinstance(extracted_data, dict) and "Company Information" in extracted_data:
                    company_info = extracted_data["Company Information"]
                    if isinstance(company_info, dict) and "Company name" in company_info:
                        company_name = company_info["Company name"]
                
                # Save to database
                save_rfp_submission(uploaded_file.name, content, extracted_data, company_name, win_status=win_status, deal_value=deal_value, win_date=win_date.strftime('%Y-%m-%d') if win_date else None, broker_consultant=broker_consultant if broker_consultant else None)
                
                st.success("✅ Document uploaded and processed successfully!")
                
                # Show extracted data
                st.subheader("Extracted Information")
                
                # Show debug info if available
                if isinstance(extracted_data, dict) and "debug_info" in extracted_data:
                    debug_info = extracted_data["debug_info"]
                    st.write("**🔍 Processing Debug Info:**")
                    st.write(f"- Total chunks processed: {debug_info['total_chunks']}")
                    st.write(f"- Chunk sizes: {debug_info['chunk_sizes']}")
                    st.write(f"- Total questions found: {extracted_data.get('question_count', 0)}")
                    st.write(f"- Sheets analyzed: {extracted_data.get('sheets_analyzed', [])}")
                    st.write(f"- Pages analyzed: {extracted_data.get('pages_analyzed', [])}")
                
                st.json(extracted_data)

def show_process_page(client):
    """Show the new RFP processing page"""
    st.header("Process New RFP")
    st.markdown("Upload a new RFP to get AI-suggested answers based on your historical submissions")
    
    # Determine supported file types
    if check_excel_support():
        file_types = ['pdf', 'docx', 'txt', 'xlsx', 'xls', 'csv']
        help_text = "Upload a new RFP to get suggested answers. Supports PDF, DOCX, TXT, Excel (XLSX, XLS), CSV"
    else:
        file_types = ['pdf', 'docx', 'txt', 'csv']
        help_text = "Upload a new RFP to get suggested answers. Supports PDF, DOCX, TXT, CSV (Excel support not available)"
    
    uploaded_file = st.file_uploader(
        "Choose a new RFP file",
        type=None,  # Allow all file types, we'll validate manually
        help=help_text
    )
    
    if uploaded_file is not None:
        # Validate file type
        file_extension = uploaded_file.name.lower().split('.')[-1]
        if file_extension not in file_types:
            st.error(f"❌ Unsupported file type: {file_extension}. Please use one of: {', '.join(file_types)}")
            return
        
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
                
                # Debug: Show what content we extracted
                st.write("🔍 **Debug: Extracted Content Preview**")
                st.write(f"Content length: {len(content)} characters")
                st.write(f"First 1000 characters: {content[:1000]}")
                st.write(f"Last 1000 characters: {content[-1000:]}")
                
                # Pre-process to extract numbered questions
                st.write("🔍 **Debug: Pre-processed Questions**")
                questions = extract_numbered_questions(content)
                st.write(f"Found {len(questions)} numbered questions:")
                for i, q in enumerate(questions[:10]):  # Show first 10
                    st.write(f"{i+1}. {q}")
                if len(questions) > 10:
                    st.write(f"... and {len(questions) - 10} more questions")
                
                # Debug: Show what historical data we have
                st.write("🔍 **Debug: Historical RFP Data**")
                st.write(f"Found {len(existing_submissions)} historical submissions")
                for i, sub in enumerate(existing_submissions[:3]):
                    st.write(f"**Submission {i+1}:** {sub[1]}")
                    if len(sub) > 4 and sub[4]:
                        try:
                            data = json.loads(sub[4])
                            if 'question_answer_pairs' in data:
                                pairs = data['question_answer_pairs']
                                st.write(f"  - {len(pairs)} question-answer pairs found")
                                st.write(f"  - First pair: {pairs[0] if pairs else 'None'}")
                            else:
                                st.write(f"  - No question-answer pairs found")
                        except:
                            st.write(f"  - Error parsing data")
                
                # Find matching answers using semantic similarity
                matches = find_matching_answers_semantic(questions, existing_submissions)
                
                # Show debug info from semantic matching
                if "debug_info" in matches:
                    st.write("🔍 **Debug: Semantic Matching Results**")
                    st.write(f"Q&A pairs found: {matches['debug_info']['qa_pairs_found']}")
                    st.write(f"Submissions processed: {matches['debug_info']['submissions_processed']}")
                    if matches['debug_info']['first_qa_pair']:
                        st.write(f"First Q&A pair: {matches['debug_info']['first_qa_pair']['question'][:100]}...")
                    else:
                        st.write("No Q&A pairs found in any submission")
                
                st.success("✅ RFP processed successfully!")
                
                # Display results
                st.subheader("Suggested Answers")
                
                # Check if no historical RFPs were found
                if matches.get("error") and "No historical RFPs found" in matches.get("error", ""):
                    st.error(f"❌ {matches['error']}")
                    st.info(f"💡 {matches.get('suggestion', '')}")
                    st.markdown("""
                    **To get started:**
                    1. Go to "Upload Historical RFPs" 
                    2. Upload your past successful RFP responses
                    3. Mark them as "Won" if they were successful
                    4. Then come back here to process new RFPs
                    """)
                    return
                
                # Debug: Show what we found
                st.subheader("🔍 Debug Information")
                st.write(f"**Total submissions found:** {len(existing_submissions)}")
                if existing_submissions:
                    st.write("**Your uploaded RFPs:**")
                    for i, sub in enumerate(existing_submissions):
                        st.write(f"{i+1}. {sub[1]} - {sub[2] or 'Unknown Company'} (Status: {sub[5] if len(sub) > 5 else 'unknown'})")
                else:
                    st.error("❌ No RFPs found in database!")
                
                # Show the raw matches for debugging
                if matches:
                    st.subheader("🔍 Raw AI Response (Debug)")
                    st.json(matches)
                
                # Show what content was sent to the AI for matching
                st.subheader("🔍 Content Sent to AI (Debug)")
                if existing_submissions:
                    st.write("**Content summary sent to AI:**")
                    # Show a sample of what the AI received
                    sample_content = ""
                    for i, sub in enumerate(existing_submissions[:2]):
                        sample_content += f"RFP {i+1}: {sub[1]}\n"
                        if len(sub) > 4 and sub[4]:
                            try:
                                data = json.loads(sub[4])
                                if 'all_questions_found' in data:
                                    questions = data['all_questions_found']
                                    sample_content += f"Questions: {len(questions)} found\n"
                                    sample_content += f"First 3 questions: {questions[:3]}\n"
                            except:
                                sample_content += "Content parsing error\n"
                        sample_content += "\n"
                    
                    st.text_area("Sample content sent to AI:", sample_content, height=200)
                
                # Show actual content from RFPs for debugging
                if existing_submissions:
                    st.subheader("🔍 Content from Your RFPs (Debug)")
                    for i, sub in enumerate(existing_submissions[:3]):  # Show first 3
                        with st.expander(f"Content from: {sub[1]}"):
                            if len(sub) > 4 and sub[4]:
                                try:
                                    data = json.loads(sub[4])
                                    st.write(f"**Question count:** {data.get('question_count', 'Unknown')}")
                                    
                                    # Check for new question-answer format
                                    if 'question_answer_pairs' in data:
                                        pairs = data['question_answer_pairs']
                                        st.write(f"**Total question-answer pairs found:** {len(pairs)}")
                                        st.write("**First 3 question-answer pairs:**")
                                        for j, pair in enumerate(pairs[:3]):
                                            if isinstance(pair, dict):
                                                st.write(f"{j+1}. **Q:** {pair.get('question', 'N/A')}")
                                                st.write(f"   **A:** {pair.get('answer', 'N/A')}")
                                            else:
                                                st.write(f"{j+1}. {pair}")
                                        if len(pairs) > 3:
                                            st.write(f"... and {len(pairs) - 3} more pairs")
                                    elif 'all_questions_found' in data:
                                        questions = data['all_questions_found']
                                        st.write(f"**Total questions found:** {len(questions)}")
                                        st.write("**First 5 questions:**")
                                        for j, q in enumerate(questions[:5]):
                                            st.write(f"{j+1}. {q}")
                                        if len(questions) > 5:
                                            st.write(f"... and {len(questions) - 5} more questions")
                                    st.json(data)
                                except Exception as e:
                                    st.write(f"Error parsing content: {e}")
                                    st.write("Raw content:", sub[4][:1000] + "...")
                            else:
                                st.write("No content found")
                
                if matches.get("matches"):
                    for i, match in enumerate(matches["matches"]):
                        with st.expander(f"Question {i+1}: {match.get('question', 'N/A')[:100]}..."):
                            st.write(f"**Suggested Answer:** {match.get('suggested_answer', 'N/A')}")
                            st.write(f"**Confidence:** {match.get('confidence', 0)}%")
                            st.write(f"**Source:** {match.get('source_rfp', 'N/A')}")
                            st.write(f"**Category:** {match.get('category', 'N/A')}")
                            if match.get('matching_reason'):
                                st.write(f"**Why this matches:** {match.get('matching_reason')}")
                else:
                    st.warning("⚠️ No specific matches found, but here are some general suggestions:")
                    
                    # Provide general suggestions based on common RFP topics
                    general_suggestions = [
                        {
                            "topic": "Company Information",
                            "suggestion": "Include your company's background, years in business, key achievements, and relevant experience in the industry.",
                            "confidence": 50
                        },
                        {
                            "topic": "Technical Capabilities", 
                            "suggestion": "Highlight your technical expertise, relevant certifications, and experience with similar projects.",
                            "confidence": 50
                        },
                        {
                            "topic": "Project Approach",
                            "suggestion": "Describe your methodology, project phases, timeline, and how you ensure quality delivery.",
                            "confidence": 50
                        },
                        {
                            "topic": "Team Qualifications",
                            "suggestion": "Introduce key team members, their qualifications, and relevant experience for this project.",
                            "confidence": 50
                        }
                    ]
                    
                    for suggestion in general_suggestions:
                        with st.expander(f"💡 {suggestion['topic']} (General Suggestion)"):
                            st.write(f"**Suggestion:** {suggestion['suggestion']}")
                            st.write(f"**Confidence:** {suggestion['confidence']}% (General guidance)")
                    
                    st.info("💡 **Tip:** Upload more historical RFPs to get more specific, tailored suggestions!")
                
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
    # Determine supported file types
    if check_excel_support():
        file_types = ['pdf', 'docx', 'txt', 'xlsx', 'xls', 'csv']
        help_text = "Upload the RFP with your corrections and improvements. Supports PDF, DOCX, TXT, Excel (XLSX, XLS), CSV"
    else:
        file_types = ['pdf', 'docx', 'txt', 'csv']
        help_text = "Upload the RFP with your corrections and improvements. Supports PDF, DOCX, TXT, CSV (Excel support not available)"
    
    uploaded_file = st.file_uploader(
        "Choose your corrected RFP file",
        type=None,  # Allow all file types, we'll validate manually
        help=help_text
    )
    
    if uploaded_file is not None:
        # Validate file type
        file_extension = uploaded_file.name.lower().split('.')[-1]
        if file_extension not in file_types:
            st.error(f"❌ Unsupported file type: {file_extension}. Please use one of: {', '.join(file_types)}")
            return
        
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
        broker_consultant = sub[8] if len(sub) > 8 and sub[8] else None
        
        df_data.append({
            "ID": sub[0],
            "Filename": sub[1],
            "Company": sub[2] or "Unknown",
            "Created": sub[3],
            "Win Status": win_status,
            "Deal Value": f"${deal_value:,.0f}" if deal_value else "N/A",
            "Win Date": win_date or "N/A",
            "Broker/Consultant": broker_consultant or "Direct/Unknown"
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
    
    # Rename RFP section
    st.subheader("📝 Rename RFP")
    st.markdown("**Change the filename to something more descriptive**")
    
    # Select RFP to rename
    rename_rfp_options = {f"{sub[1]} - {sub[2] or 'Unknown'}": sub[0] for sub in submissions}
    selected_rename_rfp = st.selectbox("Select RFP to rename:", list(rename_rfp_options.keys()), key="rename_select")
    rename_rfp_id = rename_rfp_options[selected_rename_rfp]
    
    # Get current filename
    rename_submission = next(s for s in submissions if s[0] == rename_rfp_id)
    current_filename = rename_submission[1]
    
    # Show current filename and input for new name
    st.write(f"**Current filename:** `{current_filename}`")
    
    # Extract file extension
    file_extension = ""
    if '.' in current_filename:
        file_extension = '.' + current_filename.split('.')[-1]
    
    # Input for new filename
    new_filename = st.text_input(
        "New filename:",
        value=current_filename,
        placeholder="Enter new filename",
        help=f"File extension {file_extension} will be preserved if you don't include it"
    )
    
    # Auto-add extension if not provided
    if new_filename and not new_filename.endswith(file_extension) and file_extension:
        new_filename = new_filename + file_extension
    
    # Validation
    if new_filename and new_filename != current_filename:
        if len(new_filename) > 255:
            st.error("❌ Filename is too long (max 255 characters)")
        elif not new_filename.strip():
            st.error("❌ Filename cannot be empty")
        else:
            st.info(f"📝 Will rename to: `{new_filename}`")
            
            if st.button("📝 Rename File", type="primary"):
                with st.spinner("Renaming file..."):
                    success, message = rename_rfp_submission(rename_rfp_id, new_filename)
                    if success:
                        st.success(f"✅ {message}")
                        st.info("🔄 The page will refresh to show the updated filename.")
                        st.rerun()
                    else:
                        st.error(f"❌ {message}")
    elif new_filename == current_filename:
        st.info("💡 Enter a different name to rename the file")
    
    # Delete RFP section
    st.subheader("🗑️ Delete RFP")
    st.markdown("**⚠️ Warning: This action cannot be undone!**")
    
    # Select RFP to delete
    delete_rfp_options = {f"{sub[1]} - {sub[2] or 'Unknown'}": sub[0] for sub in submissions}
    selected_delete_rfp = st.selectbox("Select RFP to delete:", list(delete_rfp_options.keys()), key="delete_select")
    delete_rfp_id = delete_rfp_options[selected_delete_rfp]
    
    # Get details of the RFP to be deleted
    delete_submission = next(s for s in submissions if s[0] == delete_rfp_id)
    delete_win_status = delete_submission[5] if len(delete_submission) > 5 else 'unknown'
    delete_deal_value = delete_submission[6] if len(delete_submission) > 6 and delete_submission[6] else None
    
    # Show details of what will be deleted
    deal_value_display = f"${delete_deal_value:,.0f}" if delete_deal_value else 'N/A'
    st.warning(f"""
    **You are about to delete:**
    - **File:** {delete_submission[1]}
    - **Company:** {delete_submission[2] or 'Unknown'}
    - **Status:** {delete_win_status.upper()}
    - **Deal Value:** {deal_value_display}
    - **Created:** {delete_submission[3]}
    
    **This will also delete:**
    - All related answers and learning data
    - All analytics and reporting data
    - This action cannot be undone!
    """)
    
    # Confirmation checkbox
    confirm_delete = st.checkbox("I understand this action cannot be undone", key="confirm_delete")
    
    # Delete button
    if confirm_delete:
        if st.button("🗑️ Delete RFP Permanently", type="secondary"):
            with st.spinner("Deleting RFP and all related data..."):
                success = delete_rfp_submission(delete_rfp_id)
                if success:
                    st.success("✅ RFP deleted successfully!")
                    st.info("🔄 The page will refresh to show updated data.")
                    st.rerun()
                else:
                    st.error("❌ Failed to delete RFP. Please try again.")
    else:
        st.info("Please check the confirmation box to enable delete button.")
    
    # Detailed view section
    st.subheader("📄 Detailed View")
    for submission in submissions:
        win_status = submission[5] if len(submission) > 5 else 'unknown'
        status_emoji = {"won": "🏆", "lost": "❌", "pending": "⏳", "unknown": "❓"}.get(win_status, "❓")
        
        with st.expander(f"{status_emoji} {submission[1]} - {submission[2] or 'Unknown Company'}"):
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.write(f"**Uploaded:** {submission[3]}")
                st.write(f"**Company:** {submission[2] or 'Not specified'}")
                st.write(f"**Win Status:** {win_status.upper()}")
                
                if len(submission) > 6 and submission[6]:
                    st.write(f"**Deal Value:** ${submission[6]:,.0f}")
                if len(submission) > 7 and submission[7]:
                    st.write(f"**Win Date:** {submission[7]}")
                
                if submission[4]:  # extracted_data or extracted_answers
                    try:
                        data = json.loads(submission[4])
                        st.write("**Extracted Information:**")
                        st.json(data)
                    except:
                        st.write("**Raw Data:**", submission[4])
            
            with col2:
                st.markdown("**Quick Actions**")
                
                # Quick rename button
                if st.button(f"📝 Rename", key=f"rename_quick_{submission[0]}", type="secondary"):
                    # Use session state to store the RFP to rename
                    st.session_state.rename_rfp_id = submission[0]
                    st.session_state.rename_rfp_name = submission[1]
                    st.rerun()
                
                # Quick delete button
                if st.button(f"🗑️ Delete", key=f"delete_quick_{submission[0]}", type="secondary"):
                    # Use session state to store the RFP to delete
                    st.session_state.delete_rfp_id = submission[0]
                    st.session_state.delete_rfp_name = submission[1]
                    st.rerun()
    
    # Handle quick rename
    if 'rename_rfp_id' in st.session_state:
        st.info(f"""
        **📝 Quick Rename**
        
        Renaming: **{st.session_state.rename_rfp_name}**
        """)
        
        # Get current filename and extension
        current_filename = st.session_state.rename_rfp_name
        file_extension = ""
        if '.' in current_filename:
            file_extension = '.' + current_filename.split('.')[-1]
        
        # Input for new filename
        new_filename = st.text_input(
            "New filename:",
            value=current_filename,
            placeholder="Enter new filename",
            key="quick_rename_input",
            help=f"File extension {file_extension} will be preserved if you don't include it"
        )
        
        # Auto-add extension if not provided
        if new_filename and not new_filename.endswith(file_extension) and file_extension:
            new_filename = new_filename + file_extension
        
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col1:
            if st.button("✅ Rename", type="primary"):
                if new_filename and new_filename != current_filename:
                    if len(new_filename) > 255:
                        st.error("❌ Filename is too long (max 255 characters)")
                    elif not new_filename.strip():
                        st.error("❌ Filename cannot be empty")
                    else:
                        with st.spinner("Renaming file..."):
                            success, message = rename_rfp_submission(st.session_state.rename_rfp_id, new_filename)
                            if success:
                                st.success(f"✅ {message}")
                                # Clear session state
                                del st.session_state.rename_rfp_id
                                del st.session_state.rename_rfp_name
                                st.rerun()
                            else:
                                st.error(f"❌ {message}")
                else:
                    st.error("❌ Please enter a different filename")
        
        with col3:
            if st.button("❌ Cancel", type="secondary"):
                # Clear session state
                del st.session_state.rename_rfp_id
                del st.session_state.rename_rfp_name
                st.rerun()
    
    # Handle quick delete confirmation
    if 'delete_rfp_id' in st.session_state:
        st.error(f"""
        **⚠️ Delete Confirmation Required**
        
        You clicked delete for: **{st.session_state.delete_rfp_name}**
        
        This will permanently remove:
        - The RFP submission
        - All related answers and learning data
        - All analytics and reporting data
        
        **This action cannot be undone!**
        """)
        
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            if st.button("✅ Yes, Delete Permanently", type="primary"):
                with st.spinner("Deleting RFP..."):
                    success = delete_rfp_submission(st.session_state.delete_rfp_id)
                    if success:
                        st.success("✅ RFP deleted successfully!")
                        # Clear session state
                        del st.session_state.delete_rfp_id
                        del st.session_state.delete_rfp_name
                        st.rerun()
                    else:
                        st.error("❌ Failed to delete RFP. Please try again.")
        
        with col3:
            if st.button("❌ Cancel", type="secondary"):
                # Clear session state
                del st.session_state.delete_rfp_id
                del st.session_state.delete_rfp_name
                st.rerun()

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
