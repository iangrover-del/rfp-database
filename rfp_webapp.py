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
            for page_num, page in enumerate(pdf_reader.pages):
                page_text = page.extract_text()
                if page_text.strip():  # Only add non-empty pages
                    text += f"\n--- PAGE {page_num + 1} ---\n"
                    text += page_text + "\n"
            
            # Add debug info about content length
            text += f"\n\n=== DEBUG INFO ===\n"
            text += f"Total pages: {len(pdf_reader.pages)}\n"
            text += f"Total characters extracted: {len(text)}\n"
            text += f"Content preview (first 1000 chars): {text[:1000]}...\n"
            text += f"Content preview (last 1000 chars): ...{text[-1000:]}\n"
            
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
    
    # Split content into chunks with overlap to ensure we don't miss anything
    chunk_size = 12000
    overlap = 2000
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
        You are an expert RFP question extraction specialist. Your task is to find and extract EVERY SINGLE QUESTION, REQUEST, or INFORMATION REQUIREMENT from this document chunk.
        
        CRITICAL INSTRUCTIONS:
        1. Read through the ENTIRE chunk carefully, word by word
        2. Extract the EXACT wording of every question, request, or information requirement
        3. Include questions that end with "?" AND questions that don't end with "?"
        4. Include numbered items, bullet points, table headers, and any text that asks for information
        5. Do NOT summarize, paraphrase, or group similar questions
        6. List EVERY question separately, even if they seem similar
        7. Include questions from tables, forms, and structured sections
        8. Look for implicit questions (text that requests information even without "?")
        
        WHAT TO EXTRACT (be very inclusive):
        - Direct questions ending with "?"
        - Requests starting with "What", "How", "When", "Where", "Why", "Who", "Which", "Describe", "Explain", "Provide", "List", "Please", "Can you", "Do you", "Are you", "Will you"
        - Numbered items that ask for information (even without "?")
        - Bullet points that ask for information
        - Table headers that ask for information
        - Any text that requests specific details, information, or responses
        - Form fields that need to be filled out
        - Requirements that need to be addressed
        - Sections that ask for documentation or evidence
        
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
        
        RESPONSE FORMAT (JSON only):
        {{
            "all_questions_found": [
                "Exact question 1 as written in document",
                "Exact question 2 as written in document",
                "Exact question 3 as written in document"
            ],
            "question_count": "total number of questions found in this chunk",
            "sheets_analyzed": "list of sheet names analyzed (for Excel files)",
            "pages_analyzed": "list of page numbers analyzed (for PDFs)"
        }}
        
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
                max_tokens=4000
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
                
                # Extract questions from this chunk
                if "all_questions_found" in chunk_data:
                    chunk_questions = chunk_data["all_questions_found"]
                    print(f"DEBUG: Chunk {i+1} found {len(chunk_questions)} questions")
                    all_questions.extend(chunk_questions)
                
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
    
    # Add a critical note about content requirements
    existing_summary += "🚨 CRITICAL INSTRUCTION: Only use ACTUAL content from the above submissions. Do NOT create placeholder text like '[specific details]' or '[explained]'. If no relevant content exists, say 'No specific answer found in previous submissions'.\n\n"
    
    prompt = f"""
    You are an expert RFP analyst helping to fill out a new RFP based on previous submissions. Your job is to find the BEST matching answers for each question in the new RFP.
    
    {existing_summary}
    
    New RFP content:
    {new_content[:8000]}
    
    CRITICAL INSTRUCTIONS:
    1. FIRST: Extract ALL specific questions from the new RFP (not just section headers)
    2. SECOND: For each question, find the BEST matching answer from previous submissions
    3. THIRD: Provide the most relevant, accurate answer for each question
    
    MATCHING STRATEGY:
    - Look for DIRECT question matches first (same or very similar wording)
    - Then look for CONCEPTUAL matches (same topic, different wording)
    - Match topics like: company info, technical requirements, business objectives, security, compliance, etc.
    - Use your knowledge to suggest relevant answers even if questions are worded differently
    
    CONFIDENCE WEIGHTING RULES:
    - CORRECTED ANSWERS: 100% confidence (user improved these)
    - WINNING RFPs: 95% confidence (proven to work)
    - UNKNOWN/PENDING: 80% confidence (might be good, include them)
    - LOST RFPs: 60% confidence (include but weight lower - might have lost for non-RFP reasons)
    
    ANSWER QUALITY REQUIREMENTS:
    - ONLY use ACTUAL content from previous RFP submissions - NO placeholder text like "[specific details]" or "[explained]"
    - Provide SPECIFIC, DETAILED answers that directly address the question using real information
    - If no good match exists, say "No specific answer found in previous submissions" instead of making up content
    - NEVER use generic placeholders - only use actual text from the source RFPs
    - Make sure the answer is appropriate for the question being asked
    
    For each question in the new RFP, provide:
    1. The exact question from the new RFP
    2. A suggested answer that directly addresses that question
    3. A confidence score (0-100) based on the source RFP's win status
    4. The source RFP that provided the best answer
    5. The source RFP's win status
    6. The category/theme matched
    7. Why this answer matches the question
    
    Format your response as JSON with this structure:
    {{
        "matches": [
            {{
                "question": "exact question from new RFP",
                "suggested_answer": "specific answer that addresses the question",
                "confidence": 85,
                "source_rfp": "filename.pdf",
                "category": "company_info|technical|business|security|compliance|timeline|etc",
                "source_status": "won|lost|unknown|pending|corrected",
                "matching_reason": "brief explanation of why this answer matches the question"
            }}
        ],
        "overall_confidence": 75
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # Changed from gpt-4 to gpt-3.5-turbo for better compatibility
            messages=[
                {"role": "system", "content": "You are an expert RFP analyst specializing in question-answer matching. Your job is to: 1) Extract ALL specific questions from the new RFP, 2) Find the BEST matching answers from previous submissions, 3) Provide accurate, relevant answers using ONLY actual content from previous RFPs. NEVER use placeholder text like '[specific details]' or '[explained]' - only use real content from the source documents. If no good match exists, say 'No specific answer found in previous submissions'. Always respond with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=3000
        )
        
        # Get the response content
        response_content = response.choices[0].message.content
        
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
                
                if submission[4]:  # extracted_data
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
