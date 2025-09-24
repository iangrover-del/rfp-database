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
    try:
    api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    except:
        api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        st.warning("⚠️ OpenAI API key not found. Some features may not work properly.")
        return None
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
        # Try rfp_responses first (Supabase), then fallback to rfp_submissions (local)
        try:
            cursor.execute('DELETE FROM rfp_responses WHERE id = ?', (rfp_id,))
        except:
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
        # Try rfp_responses first (Supabase), then fallback to rfp_submissions (local)
        try:
            cursor.execute('SELECT id FROM rfp_responses WHERE filename = ? AND id != ?', (new_filename, rfp_id))
        except:
        cursor.execute('SELECT id FROM rfp_submissions WHERE filename = ? AND id != ?', (new_filename, rfp_id))
        if cursor.fetchone():
            return False, "A file with this name already exists"
        
        # Update the filename - try rfp_responses first (Supabase), then fallback to rfp_submissions (local)
        try:
            cursor.execute('UPDATE rfp_responses SET filename = ? WHERE id = ?', (new_filename, rfp_id))
        except:
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
    
    # Try rfp_responses first (Supabase), then fallback to rfp_submissions (local)
    try:
        cursor.execute('''
            SELECT id, filename, company_name, created_at, extracted_data, win_status, deal_value, win_date, broker_consultant
            FROM rfp_responses
            ORDER BY created_at DESC
        ''')
    except:
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
    
    # Try rfp_responses first (Supabase), then fallback to rfp_submissions (local)
    try:
        cursor.execute('''
            SELECT id, filename, company_name, created_at, extracted_data, win_status, deal_value, win_date, broker_consultant
            FROM rfp_responses
            WHERE filename LIKE ? OR company_name LIKE ? OR content LIKE ?
            ORDER BY created_at DESC
        ''', (f'%{query}%', f'%{query}%', f'%{query}%'))
    except:
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
    
    # Extract actual sheet names from content if it's an Excel file
    actual_sheets = set()
    if "EXCEL FILE PROCESSING:" in content:
        import re
        sheet_matches = re.findall(r'=== SHEET: ([^=]+) ===', content)
        actual_sheets.update(sheet_matches)
        print(f"DEBUG: Found actual sheets in content: {list(actual_sheets)}")
    
    # Debug info
    print(f"DEBUG: Total content length: {len(content)} characters")
    print(f"DEBUG: Split into {len(chunks)} chunks")
    for i, chunk in enumerate(chunks):
        print(f"DEBUG: Chunk {i+1}: {len(chunk)} characters")
    
    # Debug: Show the full content for PDF files to see tables
    if "PDF" in content or "Page" in content:
        print(f"DEBUG: Full PDF content preview:")
        print("=" * 80)
        print(content[:2000])  # Show first 2000 characters
        print("=" * 80)
    
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
                
                # Track sheets and pages analyzed (but don't trust AI completely)
                if "sheets_analyzed" in chunk_data:
                    sheets_data = chunk_data["sheets_analyzed"]
                    if isinstance(sheets_data, str):
                        # Only add if it looks like a real sheet name (not AI hallucination)
                        sheet_list = sheets_data.split(", ") if sheets_data else []
                        for sheet in sheet_list:
                            if sheet and len(sheet) < 50 and not sheet.startswith("Sheet"):  # Basic validation
                                sheets_analyzed.add(sheet)
                    elif isinstance(sheets_data, list):
                        for sheet in sheets_data:
                            if isinstance(sheet, str) and len(sheet) < 50 and not sheet.startswith("Sheet"):
                                sheets_analyzed.add(sheet)
                
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
        "sheets_analyzed": list(actual_sheets) if actual_sheets else list(sheets_analyzed) if sheets_analyzed else [],
        "pages_analyzed": list(pages_analyzed) if pages_analyzed else [],
        "debug_info": {
            "total_chunks": len(chunks),
            "chunk_sizes": [len(chunk) for chunk in chunks],
            "total_content_length": len(content),
            "actual_sheets_found": len(actual_sheets),
            "ai_reported_sheets": len(sheets_analyzed)
        }
    }
    
    return final_result

def extract_numbered_questions(content: str) -> List[str]:
    """Extract all numbered questions from content, including breaking down table questions"""
    import re
    
    questions = []
    
    # Look for patterns like "1.", "2.", "3.", etc. - capture multi-line questions
    pattern1 = r'^(\d+)\.\s+(.+?)(?=^\d+\.\s+|^\d+\)\s+|^\d+:\s+|$)'
    matches1 = re.findall(pattern1, content, re.MULTILINE | re.DOTALL)
    for num, question in matches1:
        # Clean up random spaces in the question
        cleaned_question = clean_question_text(question.strip())
        
        # Check if this is a table question that should be broken down
        if is_table_question(cleaned_question):
            # Break down table questions into individual questions
            table_questions = break_down_table_question(cleaned_question)
            questions.extend(table_questions)
        else:
            questions.append(f"{num}. {cleaned_question}")
    
    # Look for patterns like "1)", "2)", "3)", etc. - capture multi-line questions
    pattern2 = r'^(\d+)\)\s+(.+?)(?=^\d+\.\s+|^\d+\)\s+|^\d+:\s+|$)'
    matches2 = re.findall(pattern2, content, re.MULTILINE | re.DOTALL)
    for num, question in matches2:
        # Clean up random spaces in the question
        cleaned_question = clean_question_text(question.strip())
        
        # Check if this is a table question that should be broken down
        if is_table_question(cleaned_question):
            # Break down table questions into individual questions
            table_questions = break_down_table_question(cleaned_question)
            questions.extend(table_questions)
        else:
            questions.append(f"{num}) {cleaned_question}")
    
    # Look for patterns like "1:", "2:", "3:", etc. - capture multi-line questions
    pattern3 = r'^(\d+):\s+(.+?)(?=^\d+\.\s+|^\d+\)\s+|^\d+:\s+|$)'
    matches3 = re.findall(pattern3, content, re.MULTILINE | re.DOTALL)
    for num, question in matches3:
        # Clean up random spaces in the question
        cleaned_question = clean_question_text(question.strip())
        
        # Check if this is a table question that should be broken down
        if is_table_question(cleaned_question):
            # Break down table questions into individual questions
            table_questions = break_down_table_question(cleaned_question)
            questions.extend(table_questions)
        else:
            questions.append(f"{num}: {cleaned_question}")
    
    # Sort by number (handle questions without numbers)
    def get_sort_key(question):
        match = re.search(r'^(\d+)', question)
        return int(match.group(1)) if match else 999  # Put unnumbered questions at the end
    
    questions.sort(key=get_sort_key)
    
    return questions

def break_down_table_question(question: str) -> List[str]:
    """Break down table questions into individual questions"""
    question_lower = question.lower()
    
    # Check if this is the network table question
    if 'complete the table below based on your current network' in question_lower:
        # Extract provider types from the content (we'll need to pass more context)
        provider_types = [
            'Mental health coaches',
            'Therapists — Adults', 
            'Therapists — Child and adolescents (ages 0 – 5)',
            'Therapists — Child and adolescents (ages 6 – 10)',
            'Therapists — Child and adolescents (ages 11 -12)',
            'Therapists — Child and adolescents (ages 13 – 18)',
            'Psychiatrists — Adults',
            'Psychiatrists — Child and adolescents',
            'Psychiatric mental health nurse practitioner'
        ]
        
        questions = []
        for provider_type in provider_types:
            questions.append(f"How many total {provider_type.lower()} in the US do you have?")
            questions.append(f"How many in-person {provider_type.lower()} in the US do you have?")
            questions.append(f"How many virtual {provider_type.lower()} in the US do you have?")
        
        return questions
    
    # For other table questions, return as-is for now
    return [question]

def clean_question_text(text: str) -> str:
    """Clean up random spaces and formatting issues in question text"""
    import re
    
    # Fix common spacing issues
    text = re.sub(r'\s+', ' ', text)  # Replace multiple spaces with single space
    text = re.sub(r'\s+([,.!?;:])', r'\1', text)  # Remove spaces before punctuation
    
    # Fix broken words by adding spaces between lowercase letters that should be separate words
    # This handles cases like "Pleasep rovideyourdefinitionofdependents"
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)  # Add space between lowercase and uppercase
    text = re.sub(r'([a-z])([a-z])([A-Z])', r'\1\2 \3', text)  # Fix "provideyour" -> "provide your"
    text = re.sub(r'([a-z])([a-z])([a-z])([A-Z])', r'\1\2\3 \4', text)  # Fix "definitionof" -> "definition of"
    
    # Fix specific common broken words
    text = re.sub(r'Pleasep\s*rovide', 'Please provide', text, flags=re.IGNORECASE)
    text = re.sub(r'definitionof', 'definition of', text, flags=re.IGNORECASE)
    text = re.sub(r'eligiblefor', 'eligible for', text, flags=re.IGNORECASE)
    text = re.sub(r'eligibility', 'eligibility', text, flags=re.IGNORECASE)
    text = re.sub(r'F\s*itness\s*-\s*for\s*-\s*duty', 'Fitness-for-duty', text, flags=re.IGNORECASE)
    text = re.sub(r'leave\s*of\s*absen\s*ce', 'leave of absence', text, flags=re.IGNORECASE)
    
    return text.strip()

def get_question_embedding(question: str) -> List[float]:
    """Get OpenAI embedding for a question"""
    try:
        import openai
        import time
        
        # Add timeout and retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = openai.embeddings.create(
                    input=question,
                    model="text-embedding-ada-002"
                )
                return response.data[0].embedding
            except Exception as e:
                print(f"DEBUG: Embedding attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)  # Wait 1 second before retry
                else:
                    raise e
    except Exception as e:
        print(f"DEBUG: Error getting embedding after {max_retries} attempts: {e}")
        return None

def calculate_cosine_similarity(embedding1: List[float], embedding2: List[float]) -> float:
    """Calculate cosine similarity between two embeddings"""
    try:
        import numpy as np
        # Convert to numpy arrays
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)
        
        # Calculate cosine similarity
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    except Exception as e:
        print(f"DEBUG: Error calculating cosine similarity: {e}")
        return 0.0

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
        'table including',
        'complete the table below based on your current network'  # Specific Barclays table question
    ]
    
    return any(indicator in question_lower for indicator in table_indicators)

def should_use_embeddings(question: str) -> bool:
    """Use embeddings for ALL questions - quality over speed"""
    return True  # Always use embeddings for best quality

def classify_question_type(question: str) -> str:
    """Classify the type of question for better matching"""
    question_lower = question.lower()
    
    # Network/Provider count questions
    if any(word in question_lower for word in ['how many', 'total', 'in-person', 'virtual', 'therapists', 'coaches', 'psychiatrists', 'nurse practitioner']):
        return 'network_count'
    
    # Demo/Login questions
    if any(word in question_lower for word in ['sample', 'demo', 'login', 'log-in', 'capabilities']):
        return 'demo_login'
    
    # Dependents/Eligibility questions
    if any(word in question_lower for word in ['dependents', 'definition', 'eligible', 'eligibility']):
        return 'dependents_eligibility'
    
    # Fitness-for-duty questions
    if any(word in question_lower for word in ['fitness-for-duty', 'fitness for duty', 'standards', 'process', 'delivery time']):
        return 'fitness_for_duty'
    
    # Implementation questions
    if any(word in question_lower for word in ['implementation', 'timeline', 'plan', 'timing']):
        return 'implementation'
    
    # Pricing/Fee questions
    if any(word in question_lower for word in ['fees', 'pricing', 'cost', 'guaranteed', 'roi', 'offset']):
        return 'pricing_fees'
    
    # Network table questions
    if any(word in question_lower for word in ['complete the table', 'geo access', 'wait times', 'appointment']):
        return 'network_table'
    
    # Account management questions
    if any(word in question_lower for word in ['account management', 'team', 'support']):
        return 'account_management'
    
    # LOA/CISM questions
    if any(word in question_lower for word in ['leave of absence', 'loa', 'cism', 'manager referrals']):
        return 'loa_cism'
    
    # Default
    return 'general'

def calculate_smart_match_score(new_question: str, historical_question: str, question_type: str, qa_pair: dict) -> float:
    """Calculate smart matching score based on question type and content"""
    new_lower = new_question.lower()
    hist_lower = historical_question.lower()
    answer_lower = qa_pair['answer'].lower()
    
    # Start with basic word overlap
    new_words = set(new_lower.split())
    hist_words = set(hist_lower.split())
    common_words = new_words & hist_words
    
    if not common_words:
        return 0.0
    
    base_score = len(common_words) / max(len(new_words), len(hist_words))
    
    # Question type specific scoring
    if question_type == 'network_count':
        # For network questions, boost if historical answer contains numbers
        if any(char.isdigit() for char in qa_pair['answer']):
            base_score += 0.3
        else:
            base_score -= 0.4  # Penalize non-numeric answers for count questions
    
    elif question_type == 'demo_login':
        # For demo questions, look for demo-related content
        if any(word in answer_lower for word in ['demo', 'sample', 'login', 'access', 'portal', 'platform']):
            base_score += 0.4
        elif any(word in answer_lower for word in ['engagement', 'assessment', 'matching']):
            base_score -= 0.3  # Penalize engagement answers for demo questions
    
    elif question_type == 'dependents_eligibility':
        # For dependents questions, look for eligibility/definition content
        if any(word in answer_lower for word in ['eligible', 'definition', 'dependents', 'family', 'spouse', 'children']):
            base_score += 0.4
        elif any(word in answer_lower for word in ['ages', 'support', '0+', '13+']):
            base_score += 0.2  # Age info is relevant for dependents
    
    elif question_type == 'fitness_for_duty':
        # For fitness-for-duty, look for process/standards content
        if any(word in answer_lower for word in ['process', 'standards', 'delivery', 'time', 'fitness', 'duty']):
            base_score += 0.4
        elif any(word in answer_lower for word in ['references', 'contact', 'reach out']):
            base_score -= 0.5  # Penalize contact info for process questions
    
    elif question_type == 'implementation':
        # For implementation questions, look for timeline/plan content
        if any(word in answer_lower for word in ['timeline', 'implementation', 'plan', 'weeks', 'months', 'phases']):
            base_score += 0.4
    
    elif question_type == 'pricing_fees':
        # For pricing questions, look for financial content
        if any(word in answer_lower for word in ['fees', 'pricing', 'cost', 'guaranteed', 'roi', 'offset', 'risk']):
            base_score += 0.4
    
    elif question_type == 'network_table':
        # For network table questions, look for geographic/network content
        if any(word in answer_lower for word in ['network', 'providers', 'coverage', 'states', 'countries', 'access']):
            base_score += 0.3
    
    elif question_type == 'account_management':
        # For account management questions, look for team/support content
        if any(word in answer_lower for word in ['team', 'manager', 'support', 'account', 'success']):
            base_score += 0.3
    
    elif question_type == 'loa_cism':
        # For LOA/CISM questions, look for process/crisis content
        if any(word in answer_lower for word in ['leave', 'absence', 'cism', 'crisis', 'incident', 'process']):
            base_score += 0.4
    
    # Boost for exact phrase matches
    if any(phrase in hist_lower for phrase in ['sample login', 'demo', 'dependents definition', 'fitness for duty', 'implementation timeline']):
        base_score += 0.2
    
    # Boost for very similar questions (high word overlap)
    if len(common_words) >= 3 and len(common_words) / max(len(new_words), len(hist_words)) > 0.6:
        base_score += 0.3
    
    # Penalize obviously wrong matches more heavily
    if question_type == 'demo_login' and any(word in answer_lower for word in ['engagement', 'assessment', 'matching']):
        base_score -= 0.6
    
    if question_type == 'dependents_eligibility' and any(word in answer_lower for word in ['engagement', 'assessment', 'matching']):
        base_score -= 0.6
    
    if question_type == 'fitness_for_duty' and any(word in answer_lower for word in ['references', 'contact', 'reach out']):
        base_score -= 0.7
    
    if question_type == 'network_count' and not any(char.isdigit() for char in qa_pair['answer']):
        base_score -= 0.5  # Heavy penalty for non-numeric answers to count questions
    
    if question_type == 'implementation' and any(word in answer_lower for word in ['financial', 'private', 'release']):
        base_score -= 0.6  # Penalize financial info for implementation questions
    
    return max(0.0, min(1.0, base_score))

def generate_contextual_answer(question: str) -> str:
    """Generate a contextual answer based on the question type and industry knowledge"""
    
    question_lower = question.lower()
    
    # Provider count questions
    if 'how many' in question_lower and any(word in question_lower for word in ['coaches', 'therapists', 'psychiatrists', 'providers', 'nurse practitioner']):
        if 'coaches' in question_lower:
            if 'in-person' in question_lower:
                return "Modern Health has 1,200+ in-person mental health coaches across all 50 states."
            elif 'virtual' in question_lower:
                return "Modern Health has 2,500+ virtual mental health coaches available across all 50 states."
            else:
                return "Modern Health has 2,500+ licensed mental health coaches across all 50 states, with both in-person and virtual options available."
        elif 'therapists' in question_lower:
            if 'in-person' in question_lower:
                return "Modern Health has 35,000+ in-person licensed therapists across all 50 states."
            elif 'virtual' in question_lower:
                return "Modern Health has 49,000+ virtual licensed therapists available across all 50 states."
            elif 'child' in question_lower or 'adolescent' in question_lower:
                return "Modern Health has 15,000+ licensed therapists specializing in child and adolescent care across all 50 states."
            else:
                return "Modern Health's network includes 84,000+ licensed therapists across the United States, covering all 50 states."
        elif 'psychiatrists' in question_lower:
            if 'in-person' in question_lower:
                return "Modern Health has 400+ in-person licensed psychiatrists across all 50 states."
            elif 'virtual' in question_lower:
                return "Modern Health has 800+ virtual licensed psychiatrists available across all 50 states."
            elif 'child' in question_lower or 'adolescent' in question_lower:
                return "Modern Health has 200+ licensed psychiatrists specializing in child and adolescent psychiatry across all 50 states."
            else:
                return "Modern Health has access to 1,200+ licensed psychiatrists across the United States."
        elif 'nurse practitioner' in question_lower:
            if 'in-person' in question_lower:
                return "Modern Health has 300+ in-person psychiatric mental health nurse practitioners across all 50 states."
            elif 'virtual' in question_lower:
                return "Modern Health has 500+ virtual psychiatric mental health nurse practitioners available across all 50 states."
            else:
                return "Modern Health has 800+ psychiatric mental health nurse practitioners across all 50 states."
        else:
            return "Modern Health's provider network includes 84,000+ licensed mental health professionals across all 50 states, including therapists, coaches, and psychiatrists, with both in-person and virtual care options available."
    
    # Geo Access questions
    elif 'geo access' in question_lower or 'geographic' in question_lower:
        return "Modern Health provides comprehensive geographic coverage across all 50 states and Washington D.C. Our GeoAccess reports detail the percentage of eligible employees that meet access criteria within specified drive times and geographic areas. We can provide detailed coverage analysis based on your specific employee locations and census data."
    
    # Implementation questions
    elif 'implementation' in question_lower:
        if 'health plan integration' in question_lower or 'hpi' in question_lower:
            return "Modern Health's health plan integration (HPI) implementation typically takes 6-8 weeks and includes: 1) Carrier interface setup and testing, 2) Claims processing integration, 3) Benefit coordination configuration, 4) Data exchange protocol establishment, and 5) Go-live support with carrier. We work directly with carriers like Anthem to ensure seamless integration and can provide detailed timelines based on your specific carrier requirements."
        elif 'timeline' in question_lower or 'plan' in question_lower:
            return "Modern Health's implementation timeline typically takes 4-6 weeks and includes: 1) Initial setup and configuration (Week 1), 2) Integration with your existing systems (Week 2-3), 3) Employee communication and training (Week 3-4), 4) Provider network activation (Week 4-5), and 5) Go-live support (Week 6). We provide dedicated implementation specialists and can customize the timeline based on your specific requirements and system complexity."
        else:
            return "Modern Health's implementation process typically takes 4-6 weeks and includes: 1) Initial setup and configuration, 2) Integration with your existing systems, 3) Employee communication and training, 4) Provider network activation, and 5) Go-live support. We provide dedicated implementation specialists to ensure a smooth transition."
    
    # Fee/Pricing questions
    elif any(word in question_lower for word in ['fee', 'cost', 'price', 'guarantee', 'risk']):
        if 'guarantee' in question_lower and 'three years' in question_lower:
            return "Modern Health can provide fee guarantees for three years with specific terms and conditions. Our standard guarantee includes fixed pricing for the initial term with options for renewal at predetermined rates. We can also offer performance-based guarantees tied to utilization and satisfaction metrics."
        elif 'guarantee' in question_lower or 'risk' in question_lower:
            return "Modern Health offers performance guarantees and can put fees at risk based on agreed-upon metrics such as utilization rates, member satisfaction, and clinical outcomes. We typically offer 20-25% of fees at risk in the first year, with specific performance targets tailored to your organization's needs."
        elif 'offset' in question_lower or 'carrier' in question_lower:
            return "Modern Health can work with carriers like Anthem to offset costs and provide integrated billing solutions. We offer carrier integration services that can help reduce administrative costs and provide seamless coordination of benefits. Our team can work directly with your carrier to establish the necessary interfaces and cost-sharing arrangements."
        elif 'roi' in question_lower or 'return on investment' in question_lower:
            return "Modern Health provides ROI estimates based on reduced healthcare costs, improved productivity, and decreased absenteeism. Our typical ROI ranges from 3:1 to 5:1 within the first year, with medical plan offsets of 15-25% through reduced claims and improved health outcomes. We can provide detailed ROI projections based on your specific employee population and utilization patterns."
        elif 'utilization' in question_lower:
            return "Modern Health's standard utilization assumptions are based on industry benchmarks and your specific employee population. We typically assume 8-12% annual utilization for EAP services, with higher rates for mental health services (15-20%). Our utilization assumptions are customized based on your employee demographics, industry, and historical usage patterns."
        else:
            return "Modern Health uses a PEPM (Per Employee Per Month) pricing model that provides transparent, predictable costs. Pricing is based on the number of eligible employees, session limits, and coverage options. We offer flexible pricing structures to meet your budget and utilization requirements."
    
    # Eligibility questions
    elif 'eligibility' in question_lower:
        return "Modern Health's eligibility file requirements include: employee ID, name, date of birth, hire date, employment status, and dependent information (if applicable). We accept standard file formats (CSV, Excel) and can integrate with most HRIS systems. Eligibility files are typically updated monthly or as needed."
    
    # Dependent questions
    elif 'dependent' in question_lower:
        if 'definition' in question_lower:
            return "Modern Health defines dependents as: Legal spouse or domestic partner, and children under age 26 (including natural children, stepchildren, adopted children, foster children, and children for whom the employee is legally responsible). All dependents are eligible for the same EAP services as employees."
        else:
            return "Modern Health defines dependents as: Legal spouse or domestic partner, and children under age 26 (including natural children, stepchildren, adopted children, foster children, and children for whom the employee is legally responsible). All dependents are eligible for the same EAP services as employees."
    
    # Wait time questions
    elif any(word in question_lower for word in ['wait time', 'appointment', 'schedule']):
        return "Modern Health provides rapid access to care with average wait times of less than 24 hours for the first available appointment. Our virtual care options often provide same-day or next-day availability, while in-person appointments may have slightly longer wait times depending on location and provider availability."
    
    # Sample login/demo questions
    elif any(word in question_lower for word in ['sample', 'login', 'demo']):
        return "Yes, Modern Health can provide a sample login for Barclays to demo our capabilities. We can set up a demo environment with sample login credentials to showcase our platform capabilities, including access to our mobile app, web portal, and key features such as provider matching, appointment scheduling, and digital resources. We can set up a personalized demo tailored to your specific needs."
    
    # Fitness-for-duty questions
    elif 'fitness for duty' in question_lower or 'fitness-for-duty' in question_lower:
        return "Modern Health provides fitness-for-duty evaluations through our network of licensed mental health professionals. Our process includes comprehensive assessment, evaluation, and recommendations for workplace accommodations or return-to-work plans. We follow industry standards and can provide detailed reports for HR and management review. Standard delivery time is typically 3-5 business days for initial assessment and 7-10 business days for comprehensive evaluation reports. Our fitness-for-duty services include psychological assessment, workplace accommodation recommendations, and return-to-work planning."
    
    # Leave of absence questions
    elif any(word in question_lower for word in ['leave', 'absence', 'loa']):
        return "Modern Health supports leave of absence processes through our EAP services, including manager referrals, CISM (Critical Incident Stress Management), and workplace consultations. We provide guidance on mental health-related leave, return-to-work planning, and ongoing support during and after leave periods."
    
    # Health plan integration questions
    elif any(word in question_lower for word in ['health plan', 'integration', 'hpi']):
        return "Modern Health integrates with major health plans and carriers, including Anthem, to provide seamless coordination of benefits. Our integration includes claims processing, benefit coordination, and data sharing to ensure comprehensive care delivery. We can work with your carrier to establish the necessary interfaces and data exchange protocols."
    
    # Account management questions
    elif any(word in question_lower for word in ['account', 'management', 'team']):
        return "Modern Health provides dedicated account management support including: a primary account manager, clinical support team, implementation specialists, and customer success representatives. Your account team will be your day-to-day point of contact for all program-related needs, reporting, and optimization."
    
    # Default response for other questions
    else:
        return "Modern Health provides comprehensive mental health and EAP services including therapy, coaching, crisis support, and digital resources. Our platform offers both virtual and in-person care options with a network of licensed professionals across all 50 states. We can customize our services to meet your specific organizational needs and requirements."
    
    return "Please provide a custom answer based on your specific requirements and capabilities."

def calculate_keyword_match_score(current_question: str, historical_question: str, answer: str) -> float:
    """Calculate keyword-based similarity score between questions and validate answer relevance"""
    
    # Extract key terms from current question
    current_words = set(current_question.lower().split())
    
    # Extract key terms from historical question
    hist_words = set(historical_question.lower().split())
    
    # Remove common stop words
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'please', 'provide', 'outline', 'discuss', 'detail', 'complete', 'use', 'attach', 'include', 'ensure', 'note', 'confirm', 'reconfirm'}
    current_words = current_words - stop_words
    hist_words = hist_words - stop_words
    
    # Calculate word overlap
    if not current_words or not hist_words:
        return 0.0
    
    overlap = len(current_words.intersection(hist_words))
    word_score = overlap / max(len(current_words), len(hist_words))
    
    # Boost for specific question types and keywords
    boost = 0.0
    
    # Geo Access questions
    if 'geo' in current_question and 'access' in current_question:
        if any(word in historical_question for word in ['geo', 'access', 'network', 'coverage', 'geographic']):
            boost += 0.3
        if any(word in answer for word in ['network', 'coverage', 'geographic', 'states', 'locations', 'providers', 'census']):
            boost += 0.2
    
    # Provider count questions
    if 'how many' in current_question and any(word in current_question for word in ['coaches', 'therapists', 'psychiatrists']):
        if any(word in historical_question for word in ['how many', 'coaches', 'therapists', 'psychiatrists', 'providers']):
            boost += 0.3
        if any(char.isdigit() for char in answer) or any(word in answer for word in ['coach', 'therapist', 'psychiatrist', 'provider', 'network']):
            boost += 0.2
    
    # Implementation questions
    if 'implementation' in current_question:
        if 'implementation' in historical_question:
            boost += 0.3
        if any(word in answer for word in ['implementation', 'timeline', 'process', 'plan', 'deployment', 'launch', 'weeks', 'months']):
            boost += 0.2
    
    # Fee/Financial questions
    if any(word in current_question for word in ['fee', 'cost', 'price', 'guarantee', 'risk', 'roi']):
        if any(word in historical_question for word in ['fee', 'cost', 'price', 'guarantee', 'risk', 'roi', 'financial']):
            boost += 0.3
        if any(word in answer for word in ['fee', 'cost', 'price', 'guarantee', 'risk', 'roi', 'financial', 'dollar', '$']):
            boost += 0.2
    
    # Eligibility questions
    if 'eligibility' in current_question:
        if 'eligibility' in historical_question:
            boost += 0.3
        if any(word in answer for word in ['eligibility', 'eligible', 'file', 'data', 'employee', 'member']):
            boost += 0.2
    
    # Dependent questions
    if 'dependent' in current_question:
        if 'dependent' in historical_question:
            boost += 0.3
        if any(word in answer for word in ['dependent', 'spouse', 'child', 'family', 'eligible']):
            boost += 0.2
    
    # Wait time questions
    if any(word in current_question for word in ['wait time', 'appointment', 'schedule']):
        if any(word in historical_question for word in ['wait', 'time', 'appointment', 'schedule']):
            boost += 0.3
        if any(word in answer for word in ['time', 'hour', 'day', 'appointment', 'schedule', 'wait', 'minutes', 'hours', 'days']):
            boost += 0.2
    
    # Sample login/demo questions
    if any(word in current_question for word in ['sample', 'login', 'demo']):
        if any(word in historical_question for word in ['sample', 'login', 'demo', 'portal', 'platform']):
            boost += 0.3
        if any(word in answer for word in ['login', 'demo', 'portal', 'platform', 'app', 'website', 'sample']):
            boost += 0.2
    
    # Fitness-for-duty questions
    if 'fitness' in current_question and 'duty' in current_question:
        if any(word in historical_question for word in ['fitness', 'duty', 'evaluation', 'assessment']):
            boost += 0.3
        if any(word in answer for word in ['fitness', 'duty', 'evaluation', 'assessment', 'process']):
            boost += 0.2
    
    # Leave of absence questions
    if any(word in current_question for word in ['leave', 'absence', 'loa']):
        if any(word in historical_question for word in ['leave', 'absence', 'loa', 'process']):
            boost += 0.3
        if any(word in answer for word in ['leave', 'absence', 'loa', 'process', 'flow']):
            boost += 0.2
    
    # Health plan integration questions
    if any(word in current_question for word in ['health plan', 'integration', 'hpi']):
        if any(word in historical_question for word in ['health', 'plan', 'integration', 'hpi']):
            boost += 0.3
        if any(word in answer for word in ['health', 'plan', 'integration', 'hpi', 'carrier']):
            boost += 0.2
    
    # Performance guarantee questions
    if 'performance' in current_question and 'guarantee' in current_question:
        if any(word in historical_question for word in ['performance', 'guarantee', 'risk']):
            boost += 0.3
        if any(word in answer for word in ['performance', 'guarantee', 'risk', 'fee', 'at risk']):
            boost += 0.2
    
    # Account management questions
    if any(word in current_question for word in ['account', 'management', 'team']):
        if any(word in historical_question for word in ['account', 'manager', 'team', 'support']):
            boost += 0.3
        if any(word in answer for word in ['account', 'manager', 'team', 'support', 'contact']):
            boost += 0.2
    
    # Penalize generic answers
    generic_phrases = ['enhance', 'program', 'resources', 'access points', 'employees', 'dependents', 'offers', 'provides', 'includes', 'features', 'capabilities', 'services', 'programs', 'confirmed', 'yes']
    if any(phrase in answer for phrase in generic_phrases):
        boost -= 0.3
    
    # Final score
    final_score = word_score + boost
    return max(0.0, min(1.0, final_score))

def is_answer_relevant_to_question(question_lower: str, answer_lower: str) -> bool:
    """Check if an answer is relevant to the question being asked - ENHANCED VERSION"""
    
    # Geo Access questions should have specific geographic/network info
    if 'geo access' in question_lower:
        return any(word in answer_lower for word in ['network', 'coverage', 'geographic', 'states', 'locations', 'providers', 'census', 'zip', 'county', 'region', 'nationwide', '50 states', 'coverage area'])
    
    # Sample login questions should have specific login/demo info
    if 'sample login' in question_lower or 'demo' in question_lower:
        return any(word in answer_lower for word in ['login', 'demo', 'portal', 'platform', 'app', 'website', 'username', 'password', 'credentials', 'access', 'sample', 'test'])
    
    # Visit limit questions should have specific visit/limit info
    if 'visit limit' in question_lower:
        return any(word in answer_lower for word in ['visit', 'limit', 'session', 'appointment', 'care', 'therapy', 'maximum', 'number', 'count', 'sessions'])
    
    # Network provider count questions should have specific numbers or provider info
    if any(word in question_lower for word in ['how many', 'total', 'in-person', 'virtual']) and any(word in question_lower for word in ['coaches', 'therapists', 'psychiatrists']):
        # Must have either numbers or specific provider terms, AND not be about general services
        has_numbers = any(char.isdigit() for char in answer_lower)
        has_provider_terms = any(word in answer_lower for word in ['coach', 'therapist', 'psychiatrist', 'provider', 'network', 'licensed', 'certified', 'practitioner'])
        is_not_general = not any(word in answer_lower for word in ['offers', 'provides', 'includes', 'features', 'capabilities', 'services', 'programs'])
        return (has_numbers or has_provider_terms) and is_not_general
    
    # Implementation questions should have specific timeline/process info
    if 'implementation' in question_lower:
        return any(word in answer_lower for word in ['implementation', 'timeline', 'process', 'plan', 'deployment', 'launch', 'weeks', 'months', 'phases', 'steps', 'schedule'])
    
    # Fee questions should have specific financial info
    if any(word in question_lower for word in ['fee', 'cost', 'price', 'guarantee', 'risk']):
        return any(word in answer_lower for word in ['fee', 'cost', 'price', 'guarantee', 'risk', 'financial', 'pricing', 'dollar', '$', 'per', 'annual', 'monthly', 'at risk'])
    
    # Eligibility questions should have specific eligibility info
    if 'eligibility' in question_lower:
        return any(word in answer_lower for word in ['eligibility', 'eligible', 'file', 'data', 'employee', 'member', 'enrollment', 'roster', 'requirements'])
    
    # Dependent questions should have specific dependent info
    if 'dependent' in question_lower:
        return any(word in answer_lower for word in ['dependent', 'spouse', 'child', 'family', 'eligible', 'age', 'relationship', 'definition'])
    
    # Wait time questions should have specific timing info
    if 'wait time' in question_lower or 'appointment' in question_lower:
        return any(word in answer_lower for word in ['time', 'hour', 'day', 'appointment', 'schedule', 'wait', 'minutes', 'hours', 'days', 'average', 'response'])
    
    # Fitness-for-duty questions should have specific process info
    if 'fitness for duty' in question_lower or 'fitness-for-duty' in question_lower:
        return any(word in answer_lower for word in ['fitness', 'duty', 'evaluation', 'assessment', 'process', 'standard', 'delivery', 'time', 'workplace'])
    
    # Leave of absence questions should have specific LOA info
    if 'leave of absence' in question_lower or 'loa' in question_lower:
        return any(word in answer_lower for word in ['leave', 'absence', 'loa', 'process', 'flow', 'manager', 'referral', 'cism', 'workplace'])
    
    # Health plan integration questions should have specific HPI info
    if 'health plan integration' in question_lower or 'hpi' in question_lower:
        return any(word in answer_lower for word in ['health', 'plan', 'integration', 'hpi', 'carrier', 'anthem', 'medical', 'benefit', 'coordination'])
    
    # Performance guarantee questions should have specific guarantee info
    if 'performance guarantee' in question_lower:
        return any(word in answer_lower for word in ['performance', 'guarantee', 'risk', 'fee', 'at risk', 'roi', 'offset', 'financial'])
    
    # ROI questions should have specific financial/return info
    if 'roi' in question_lower or 'return on investment' in question_lower:
        return any(word in answer_lower for word in ['roi', 'return', 'investment', 'financial', 'savings', 'cost', 'benefit', 'offset'])
    
    # Account management questions should have specific team/structure info
    if 'account management' in question_lower or 'team' in question_lower:
        return any(word in answer_lower for word in ['account', 'manager', 'team', 'support', 'contact', 'relationship', 'success'])
    
    # Default: be more restrictive - only allow if answer seems relevant and not generic
    generic_phrases = ['enhance', 'program', 'resources', 'access points', 'employees', 'dependents', 'offers', 'provides', 'includes', 'features', 'capabilities', 'services', 'programs', 'confirmed', 'yes']
    return len(answer_lower) > 20 and not any(phrase in answer_lower for phrase in generic_phrases)

def find_matching_answers_simple(questions: List[str], existing_submissions: List) -> Dict[str, Any]:
    """AI Knowledge System: Build comprehensive Modern Health knowledge base and recall intelligently"""
    print("DEBUG: Building AI knowledge system from historical RFP data")
    
    matches = []
    
    # Check if we have historical data to learn from
    if not existing_submissions:
        print("DEBUG: No historical submissions found, using contextual generation")
        # Fallback to contextual generation if no historical data
        for i, question in enumerate(questions):
            generated_answer = generate_contextual_answer(question)
            matches.append({
                "question": question,
                "suggested_answer": generated_answer or "Please provide a custom answer based on your specific requirements.",
                "confidence": 50,
                "source_rfp": "AI Generated",
                "category": "ai_contextual",
                "source_status": "generated",
                "matching_reason": "No historical data available, using AI contextual generation"
            })
        
        return {
            "matches": matches,
            "overall_confidence": 50,
            "total_questions_found": len(questions),
            "questions_answered": len(matches),
            "debug_info": {
                "qa_pairs_found": 0,
                "submissions_processed": 0,
                "method": "ai_contextual_fallback",
                "first_qa_pair": None
            }
        }
    
    # Build comprehensive Modern Health knowledge base
    modern_health_knowledge = build_modern_health_knowledge_base(existing_submissions)
    print(f"DEBUG: Built Modern Health knowledge base with {len(modern_health_knowledge)} knowledge entries")
    
    if not modern_health_knowledge:
        print("DEBUG: Knowledge base is empty, using contextual generation")
        # Fallback to contextual generation if knowledge base is empty
        for i, question in enumerate(questions):
            generated_answer = generate_contextual_answer(question)
            matches.append({
                "question": question,
                "suggested_answer": generated_answer or "Please provide a custom answer based on your specific requirements.",
                "confidence": 50,
                "source_rfp": "AI Generated",
                "category": "ai_contextual",
                "source_status": "generated",
                "matching_reason": "Empty knowledge base, using AI contextual generation"
            })
        
        return {
            "matches": matches,
            "overall_confidence": 50,
            "total_questions_found": len(questions),
            "questions_answered": len(matches),
            "debug_info": {
                "qa_pairs_found": 0,
                "submissions_processed": len(existing_submissions),
                "method": "ai_contextual_fallback",
                "first_qa_pair": None
            }
        }
    
    # Use AI knowledge system to generate answers from Modern Health knowledge
    for i, question in enumerate(questions):
        print(f"DEBUG: Using AI knowledge system for question {i+1}/{len(questions)}: {question[:50]}...")
        
        try:
            # Use AI to generate answer from Modern Health knowledge base
            print(f"DEBUG: Knowledge base length: {len(modern_health_knowledge)} characters")
            ai_answer = generate_answer_from_knowledge_base(question, modern_health_knowledge)
            
            if ai_answer and len(ai_answer) > 20:
                # Check if this is a provider count question that got a generic "not available" response
                if any(word in question.lower() for word in ['how many', 'coaches', 'therapists', 'psychiatrists', 'providers']) and ('not available' in ai_answer.lower() or 'does not have specific' in ai_answer.lower() or 'does not provide' in ai_answer.lower()):
                    print(f"DEBUG: AI knowledge system gave generic response for provider count question {i+1}, using contextual generation")
                    # Fallback to contextual generation for provider counts
                    generated_answer = generate_contextual_answer(question)
                    matches.append({
                        "question": question,
                        "suggested_answer": generated_answer or "Please provide a custom answer based on your specific requirements.",
                        "confidence": 80,
                        "source_rfp": "AI Generated",
                        "category": "ai_contextual",
                        "source_status": "generated",
                        "matching_reason": "AI knowledge system gave generic response for provider count, using contextual generation"
                    })
                # Check if this is a fitness-for-duty question that got a generic response
                elif 'fitness for duty' in question.lower() or 'fitness-for-duty' in question.lower():
                    if 'does not have specific' in ai_answer.lower() or 'not available' in ai_answer.lower():
                        print(f"DEBUG: AI knowledge system gave generic response for fitness-for-duty question {i+1}, using contextual generation")
                        # Fallback to contextual generation for fitness-for-duty
                        generated_answer = generate_contextual_answer(question)
                        matches.append({
                            "question": question,
                            "suggested_answer": generated_answer or "Please provide a custom answer based on your specific requirements.",
                            "confidence": 80,
                            "source_rfp": "AI Generated",
                            "category": "ai_contextual",
                            "source_status": "generated",
                            "matching_reason": "AI knowledge system gave generic response for fitness-for-duty, using contextual generation"
                        })
                    else:
                        print(f"DEBUG: AI knowledge system succeeded for fitness-for-duty question {i+1}")
                        matches.append({
                            "question": question,
                            "suggested_answer": ai_answer,
                            "confidence": 90,  # Very high confidence for AI knowledge-based answers
                            "source_rfp": "AI Knowledge System - Modern Health",
                            "category": "ai_knowledge",
                            "source_status": "learned",
                            "matching_reason": "AI generated answer from comprehensive Modern Health knowledge base"
                        })
                else:
                    print(f"DEBUG: AI knowledge system succeeded for question {i+1}")
                    matches.append({
                        "question": question,
                        "suggested_answer": ai_answer,
                        "confidence": 90,  # Very high confidence for AI knowledge-based answers
                        "source_rfp": "AI Knowledge System - Modern Health",
                        "category": "ai_knowledge",
                        "source_status": "learned",
                        "matching_reason": "AI generated answer from comprehensive Modern Health knowledge base"
                    })
            else:
                print(f"DEBUG: AI knowledge system failed for question {i+1}, using contextual generation")
                # Fallback to contextual generation
                generated_answer = generate_contextual_answer(question)
                matches.append({
                    "question": question,
                    "suggested_answer": generated_answer or "Please provide a custom answer based on your specific requirements.",
                    "confidence": 60,
                    "source_rfp": "AI Generated",
                    "category": "ai_contextual",
                    "source_status": "generated",
                    "matching_reason": f"AI knowledge system failed (answer length: {len(ai_answer) if ai_answer else 0}), using contextual generation"
                })
                
        except Exception as e:
            print(f"DEBUG: Error in AI knowledge system for question {i+1}: {e}")
            # Fallback to contextual generation
            generated_answer = generate_contextual_answer(question)
            matches.append({
                "question": question,
                "suggested_answer": generated_answer or "Please provide a custom answer based on your specific requirements.",
                "confidence": 50,
                "source_rfp": "AI Generated",
                "category": "ai_contextual",
                "source_status": "generated",
                "matching_reason": f"AI knowledge system error: {str(e)[:50]}"
            })
    
    # Calculate overall confidence
    overall_confidence = sum(m.get('confidence', 0) for m in matches) // len(matches) if matches else 0
    
    return {
        "matches": matches,
        "overall_confidence": overall_confidence,
        "total_questions_found": len(questions),
        "questions_answered": len(matches),
        "debug_info": {
            "qa_pairs_found": len(modern_health_knowledge.split('\n\n')) if modern_health_knowledge else 0,
            "submissions_processed": len(existing_submissions),
            "method": "ai_knowledge_system",
            "first_qa_pair": modern_health_knowledge[:500] if modern_health_knowledge else None
        }
    }

def build_modern_health_knowledge_base(existing_submissions: List) -> str:
    """Build a comprehensive Modern Health knowledge base from all historical submissions"""
    knowledge_entries = []
    
    for submission in existing_submissions:
        if len(submission) > 4 and submission[4]:
            try:
                data = json.loads(submission[4])
                print(f"DEBUG: Building knowledge from {submission[1]}")
                
                if 'question_answer_pairs' in data:
                    pairs = data['question_answer_pairs']
                    for pair in pairs:
                        if isinstance(pair, dict) and 'question' in pair and 'answer' in pair:
                            if pair['answer'] and len(pair['answer'].strip()) > 20:
                                knowledge_entries.append(f"Q: {pair['question']}\nA: {pair['answer']}\n")
                elif 'all_questions_found' in data:
                    questions_found = data['all_questions_found']
                    if isinstance(questions_found, list):
                        for pair in questions_found:
                            if isinstance(pair, dict) and 'question' in pair and 'answer' in pair:
                                if pair['answer'] and len(pair['answer'].strip()) > 20:
                                    knowledge_entries.append(f"Q: {pair['question']}\nA: {pair['answer']}\n")
            except Exception as e:
                print(f"DEBUG: Error parsing submission {submission[1]}: {e}")
                continue
    
    # Combine all knowledge into a comprehensive knowledge base
    knowledge_base = "MODERN HEALTH KNOWLEDGE BASE:\n\n"
    knowledge_base += "This knowledge base contains information about Modern Health's capabilities, processes, and services based on historical RFP responses.\n\n"
    
    for entry in knowledge_entries:
        knowledge_base += entry + "\n"
    
    print(f"DEBUG: Built knowledge base with {len(knowledge_entries)} entries")
    return knowledge_base

def generate_answer_from_knowledge_base(question: str, knowledge_base: str) -> str:
    """Use AI to generate answers from the comprehensive Modern Health knowledge base"""
    try:
        print(f"DEBUG: Starting AI knowledge generation for question: {question[:50]}...")
        print(f"DEBUG: Knowledge base length: {len(knowledge_base)} characters")
        
        # Test API key first with a simple call
        try:
            # Try new API format first (openai>=1.0.0)
            try:
                client = openai.OpenAI()
                test_response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": "Test"}],
                    max_tokens=10
                )
                print(f"DEBUG: API key test successful (New API)")
            except Exception as new_api_error:
                # Fallback to old API format (openai<1.0.0)
                test_response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": "Test"}],
                    max_tokens=10
                )
                print(f"DEBUG: API key test successful (Old API)")
        except Exception as api_error:
            print(f"DEBUG: API key test failed: {api_error}")
            return ""
        
        # Check if knowledge base is too large (limit to avoid token limits)
        if len(knowledge_base) > 8000:  # Conservative limit for gpt-3.5-turbo
            print(f"DEBUG: Knowledge base too large ({len(knowledge_base)} chars), truncating")
            knowledge_base = knowledge_base[:8000] + "\n\n[Knowledge base truncated for token limits]"
        
        prompt = f"""You are an expert RFP response writer for Modern Health. You have access to a comprehensive knowledge base about Modern Health's capabilities, processes, and services.

QUESTION: {question}

KNOWLEDGE BASE:
{knowledge_base}

INSTRUCTIONS:
1. Use the knowledge base above to answer the question concisely and directly
2. Keep answers focused and to the point - avoid unnecessary repetition or verbose explanations
3. If the knowledge base contains relevant information, provide a clear, specific answer
4. If the knowledge base doesn't contain specific information, provide a helpful, professional response based on Modern Health's general capabilities
5. Maintain consistency with Modern Health's capabilities and services
6. Do NOT mention other company names or brands
7. Focus on specific, actionable information from the knowledge base
8. If you find conflicting information, use the most recent or most detailed version
9. For provider count questions, look carefully through the knowledge base for any numbers or provider information, even if not exact matches
10. Be helpful and informative - avoid saying "not available" unless truly no relevant information exists
11. For questions about capabilities (like sample logins), provide positive, helpful responses

Generate a concise, professional RFP response based on the knowledge base:"""

        print(f"DEBUG: Calling OpenAI API with prompt length: {len(prompt)}")
        print(f"DEBUG: Prompt preview: {prompt[:200]}...")
        
        # Try new API format first (openai>=1.0.0)
        try:
            client = openai.OpenAI()
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an expert RFP response writer specializing in mental health and EAP services for Modern Health. Always provide accurate, specific answers based on the knowledge base provided."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.3
            )
        except Exception as new_api_error:
            # Fallback to old API format (openai<1.0.0)
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an expert RFP response writer specializing in mental health and EAP services for Modern Health. Always provide accurate, specific answers based on the knowledge base provided."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.3
            )
        
        print(f"DEBUG: OpenAI API response received")
        print(f"DEBUG: Response choices count: {len(response.choices)}")
        
        if not response.choices:
            print("DEBUG: No choices in OpenAI response")
            return ""
        
        answer = response.choices[0].message.content.strip()
        print(f"DEBUG: AI generated answer length: {len(answer)}")
        print(f"DEBUG: AI generated answer preview: {answer[:100]}...")
        
        # Clean up the answer
        if answer.startswith("Based on the knowledge base"):
            answer = answer.split("\n", 1)[1] if "\n" in answer else answer
        
        print(f"DEBUG: Final answer length after cleanup: {len(answer)}")
        return answer
        
    except Exception as e:
        print(f"DEBUG: Error in AI knowledge generation: {e}")
        print(f"DEBUG: Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        return ""

def test_openai_api_key() -> str:
    """Test if OpenAI API key is working and return status"""
    try:
        # Try new API format first (openai>=1.0.0)
        try:
            client = openai.OpenAI()
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=10
            )
            return "✅ API Key Working (New API)"
        except Exception as new_api_error:
            # Fallback to old API format (openai<1.0.0)
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=10
            )
            return "✅ API Key Working (Old API)"
    except Exception as e:
        return f"❌ API Key Failed: {str(e)[:100]}"

def find_relevant_historical_answers(question: str, knowledge_base: List[Dict]) -> List[Dict]:
    """Find relevant historical answers using semantic similarity and keyword matching"""
    relevant_answers = []
    question_lower = question.lower()
    
    # Extract key terms from the question
    question_words = set(question_lower.split())
    question_words.discard('the')
    question_words.discard('a')
    question_words.discard('an')
    question_words.discard('and')
    question_words.discard('or')
    question_words.discard('but')
    question_words.discard('in')
    question_words.discard('on')
    question_words.discard('at')
    question_words.discard('to')
    question_words.discard('for')
    question_words.discard('of')
    question_words.discard('with')
    question_words.discard('by')
    
    for qa_pair in knowledge_base:
        if not isinstance(qa_pair, dict) or 'question' not in qa_pair or 'answer' not in qa_pair:
            continue
            
        hist_question = qa_pair['question'].lower()
        hist_answer = qa_pair['answer']
        
        if not hist_answer or len(hist_answer.strip()) < 10:
            continue
        
        # Calculate relevance score
        relevance_score = 0
        
        # 1. Exact question match (highest priority)
        if question_lower == hist_question:
            relevance_score += 1.0
        # 2. Question contains most of the historical question
        elif len(question_words.intersection(set(hist_question.split()))) / len(set(hist_question.split())) > 0.7:
            relevance_score += 0.8
        # 3. Keyword overlap
        else:
            hist_words = set(hist_question.split())
            hist_words.discard('the')
            hist_words.discard('a')
            hist_words.discard('an')
            hist_words.discard('and')
            hist_words.discard('or')
            hist_words.discard('but')
            hist_words.discard('in')
            hist_words.discard('on')
            hist_words.discard('at')
            hist_words.discard('to')
            hist_words.discard('for')
            hist_words.discard('of')
            hist_words.discard('with')
            hist_words.discard('by')
            
            overlap = len(question_words.intersection(hist_words))
            if overlap > 0:
                relevance_score += overlap / max(len(question_words), len(hist_words))
        
        # 4. Boost for specific question types with more precise matching
        if any(word in question_lower for word in ['how many', 'count', 'number']):
            if any(word in hist_question for word in ['how many', 'count', 'number']):
                # Additional check: make sure they're asking about similar things
                if any(word in question_lower for word in ['coach', 'therapist', 'provider', 'psychiatrist']):
                    if any(word in hist_question for word in ['coach', 'therapist', 'provider', 'psychiatrist']):
                        relevance_score += 0.4
                else:
                    relevance_score += 0.3
        elif any(word in question_lower for word in ['implementation', 'timeline', 'plan']):
            if any(word in hist_question for word in ['implementation', 'timeline', 'plan']):
                relevance_score += 0.3
        elif any(word in question_lower for word in ['fee', 'cost', 'price', 'guarantee']):
            if any(word in hist_question for word in ['fee', 'cost', 'price', 'guarantee']):
                relevance_score += 0.3
        elif any(word in question_lower for word in ['coach', 'therapist', 'provider']):
            if any(word in hist_question for word in ['coach', 'therapist', 'provider']):
                relevance_score += 0.3
        elif any(word in question_lower for word in ['eligibility', 'file', 'requirements']):
            if any(word in hist_question for word in ['eligibility', 'file', 'requirements']):
                relevance_score += 0.4
        elif any(word in question_lower for word in ['dependent', 'dependents']):
            if any(word in hist_question for word in ['dependent', 'dependents']):
                # Additional check: make sure it's about definition, not eligibility
                if 'definition' in question_lower and 'definition' in hist_question:
                    relevance_score += 0.5
                elif 'definition' in question_lower and any(word in hist_question for word in ['spouse', 'child', 'domestic', 'partner', 'age']):
                    relevance_score += 0.4
                else:
                    relevance_score += 0.2  # Lower score for general dependent questions
        elif any(word in question_lower for word in ['fitness', 'duty']):
            if any(word in hist_question for word in ['fitness', 'duty']):
                relevance_score += 0.4
        elif any(word in question_lower for word in ['leave', 'absence', 'loa']):
            if any(word in hist_question for word in ['leave', 'absence', 'loa']):
                relevance_score += 0.4
        
        # Only include if relevance score is above threshold
        if relevance_score > 0.4:  # Increased threshold for better relevance
            relevant_answers.append({
                'question': qa_pair['question'],
                'answer': hist_answer,
                'source': qa_pair.get('source', 'Unknown'),
                'status': qa_pair.get('status', 'unknown'),
                'relevance_score': relevance_score
            })
    
    # Sort by relevance score and return top 5
    relevant_answers.sort(key=lambda x: x['relevance_score'], reverse=True)
    
    # Debug: Show what we found
    if relevant_answers:
        print(f"DEBUG: Found {len(relevant_answers)} relevant answers for: {question[:50]}...")
        for i, answer in enumerate(relevant_answers[:3]):
            print(f"DEBUG: Answer {i+1} (score: {answer['relevance_score']:.2f}): {answer['question'][:50]}...")
            print(f"DEBUG: Answer {i+1} content: {answer['answer'][:100]}...")
    else:
        print(f"DEBUG: No relevant answers found for: {question[:50]}...")
    
    return relevant_answers[:5]

def synthesize_answer_from_history(question: str, relevant_answers: List[Dict]) -> str:
    """Use AI to synthesize a comprehensive answer from relevant historical data"""
    if not relevant_answers:
        return ""
    
    try:
        # Prepare context from historical answers
        context = "Historical RFP Answers:\n\n"
        for i, answer in enumerate(relevant_answers):
            context += f"Source {i+1} ({answer['source']}):\n"
            context += f"Question: {answer['question']}\n"
            context += f"Answer: {answer['answer']}\n\n"
        
        # Create prompt for AI synthesis
        prompt = f"""You are an expert RFP response writer. Based on the historical RFP answers below, create a comprehensive, professional answer for the new question.

NEW QUESTION: {question}

{context}

INSTRUCTIONS:
1. Synthesize the best information from the historical answers
2. Create a comprehensive, professional response
3. Use specific details and numbers when available
4. Maintain consistency with Modern Health's capabilities
5. Do NOT mention other company names or brands
6. Focus on the most relevant and accurate information
7. If historical answers conflict, choose the most recent or most detailed one
8. Make sure the answer directly addresses the question asked
9. CRITICAL: Only use information that is directly relevant to the question. Do NOT include information about unrelated topics like kits, engagement metrics, or general service descriptions unless the question specifically asks about them
10. If the historical answers don't contain relevant information for the question, say so rather than including irrelevant details

Generate a professional RFP response:"""

        # Call OpenAI API with error handling
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert RFP response writer specializing in mental health and EAP services. Always provide direct, relevant answers to the specific question asked."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.3
        )
        
        synthesized_answer = response.choices[0].message.content.strip()
        
        # Clean up the answer
        if synthesized_answer.startswith("Based on the historical data"):
            synthesized_answer = synthesized_answer.split("\n", 1)[1] if "\n" in synthesized_answer else synthesized_answer
        
        # Validate that the answer is relevant to the question
        if len(synthesized_answer) < 20:
            print(f"DEBUG: AI synthesis returned too short answer: {synthesized_answer}")
            return ""
        
        # Check if answer seems relevant (basic validation)
        question_lower = question.lower()
        answer_lower = synthesized_answer.lower()
        
        # Reject answers that are clearly about different topics
        irrelevant_topics = {
            'kits': ['kits', 'topics', 'adoption', 'assisted living', 'career', 'college', 'financial fitness', 'grief', 'new parent', 'retirement', 'pet care', 'tobacco cessation', 'teens', 'toddlers', 'lifecycle', 'brochures', 'dvds', 'books', 'gift items'],
            'engagement': ['engagement', 'well-being assessment', 'matched with provider', 'listened to meditation', 'interacted with digital', 'viewed daily pause', 'attended session', 'rsvp\'d to circle'],
            'communication': ['customer agreement permits', 'communicate with eligible', 'member registration email', 'drive registration'],
            'general_services': ['comprehensive mental health', 'therapy', 'coaching', 'crisis support', 'digital resources', 'virtual and in-person care', 'network of licensed professionals']
        }
        
        # Check if answer is about irrelevant topics
        for topic, keywords in irrelevant_topics.items():
            if any(keyword in answer_lower for keyword in keywords):
                # But allow if the question is actually about that topic
                if not any(keyword in question_lower for keyword in keywords):
                    print(f"DEBUG: Answer is about {topic} but question is not")
                    return ""
        
        # If question is about specific topics, make sure answer addresses them
        if 'eligibility' in question_lower and 'file' in question_lower:
            # Must mention file requirements, not just eligibility
            if not any(word in answer_lower for word in ['file', 'format', 'data', 'employee', 'id', 'name', 'birth', 'hire']):
                print(f"DEBUG: Answer doesn't address eligibility file requirements")
                return ""
        elif 'dependent' in question_lower and 'definition' in question_lower:
            # Must mention specific dependent types, not just eligibility
            if not any(word in answer_lower for word in ['spouse', 'child', 'domestic', 'partner', 'age', '26', 'dependent']):
                print(f"DEBUG: Answer doesn't address dependent definition")
                return ""
            # Reject answers that are primarily about eligibility files
            if any(word in answer_lower for word in ['eligibility file', 'file formatting', 'verification', 'system agnostic']):
                print(f"DEBUG: Answer is about eligibility files, not dependent definition")
                return ""
        elif 'fitness' in question_lower and 'duty' in question_lower:
            # Must mention fitness-for-duty process, not kits or other topics
            if not any(word in answer_lower for word in ['fitness', 'duty', 'evaluation', 'assessment', 'standard', 'process']):
                print(f"DEBUG: Answer doesn't address fitness-for-duty")
                return ""
        elif 'leave' in question_lower and 'absence' in question_lower:
            # Must mention leave processes
            if not any(word in answer_lower for word in ['leave', 'absence', 'loa', 'process', 'manager', 'referral']):
                print(f"DEBUG: Answer doesn't address leave processes")
                return ""
        
        return synthesized_answer
        
    except Exception as e:
        print(f"DEBUG: Error in AI synthesis: {e}")
        # Fallback: return the best historical answer
        if relevant_answers:
            return relevant_answers[0]['answer']
        return ""

def generate_ai_answer_for_question(question: str, all_qa_pairs: List[Dict]) -> Dict[str, Any]:
    """Use AI to generate a relevant answer for a question based on the knowledge base"""
    try:
        # Find the most relevant Q&A pairs for this question
        relevant_pairs = find_most_relevant_qa_pairs(question, all_qa_pairs)
        
        if not relevant_pairs:
            return {
                'answer': 'No relevant information found in knowledge base.',
                'confidence': 10,
                'source': 'None',
                'status': 'unknown'
            }
        
        # Use AI to generate a synthesized answer
        synthesis_prompt = f"""
        You are an expert RFP response specialist. Based on the following question and relevant historical answers, generate the best possible response.

        NEW QUESTION: {question}

        RELEVANT HISTORICAL ANSWERS:
        """
        
        for i, pair in enumerate(relevant_pairs[:5]):  # Use top 5 most relevant
            synthesis_prompt += f"""
        Historical Answer {i+1} (from {pair['source']}):
        Question: {pair['question']}
        Answer: {pair['answer']}
        """
        
        synthesis_prompt += """
        
        INSTRUCTIONS:
        1. Generate a comprehensive answer that directly addresses the new question
        2. Use the most relevant information from the historical answers
        3. If the historical answers don't directly address the question, synthesize a reasonable response based on the available information
        4. Ensure the answer is specific and actionable
        5. Clean up any brand names or client-specific information
        6. Make the answer professional and complete
        7. If the question asks for specific numbers or data that isn't available, indicate that
        
        RESPONSE FORMAT (JSON only):
        {
            "answer": "Your synthesized answer here",
            "confidence": 85,
            "reasoning": "Why this answer is relevant and complete"
        }
        """
        
        print("DEBUG: About to call OpenAI API for answer generation")
        # Call OpenAI to synthesize the answer
        import openai
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": synthesis_prompt}],
            max_tokens=1000,
            temperature=0.3
        )
        print("DEBUG: OpenAI API call completed")
        
        result = json.loads(response.choices[0].message.content)
        print(f"DEBUG: AI generated answer with confidence: {result.get('confidence', 'unknown')}")
        
        return {
            'answer': clean_brand_names(result['answer']),
            'confidence': result['confidence'],
            'source': relevant_pairs[0]['source'],
            'status': relevant_pairs[0]['status']
        }
        
    except Exception as e:
        print(f"DEBUG: Error in AI answer generation: {e}")
        import traceback
        traceback.print_exc()
        return {
            'answer': 'Error generating AI answer.',
            'confidence': 10,
            'source': 'None',
            'status': 'unknown'
        }

def find_most_relevant_qa_pairs(question: str, all_qa_pairs: List[Dict]) -> List[Dict]:
    """Find the most relevant Q&A pairs for a given question"""
    question_lower = question.lower()
    question_words = set(question_lower.split())
    
    scored_pairs = []
    
    for qa_pair in all_qa_pairs:
        score = 0
        hist_question_lower = qa_pair['question'].lower()
        hist_words = set(hist_question_lower.split())
        
        # Calculate word overlap
        common_words = question_words & hist_words
        if common_words:
            word_score = len(common_words) / max(len(question_words), len(hist_words))
            score += word_score * 0.5
        
        # Boost for important phrases
        important_phrases = [
            'geo access', 'sample login', 'visit limit', 'eligibility file', 
            'definition of dependents', 'fitness for duty', 'leave of absence',
            'implementation timeline', 'health plan integration', 'fees',
            'performance guarantees', 'roi estimate', 'fees at risk',
            'mental health coaches', 'therapists', 'psychiatrists', 'nurse practitioner',
            'in-person', 'virtual', 'adults', 'child', 'adolescents', 'ages',
            'wait times', 'appointment', 'account management', 'team',
            'utilization assumption', 'financial template', 'guaranteed', 'three years',
            'offset costs', 'carrier', 'anthem', 'health plan integration'
        ]
        
        for phrase in important_phrases:
            if phrase in question_lower and phrase in hist_question_lower:
                score += 0.5
        
        if score > 0.1:  # Only include pairs with some relevance
            scored_pairs.append((score, qa_pair))
    
    # Sort by score and return top 10
    scored_pairs.sort(key=lambda x: x[0], reverse=True)
    return [pair for score, pair in scored_pairs[:10]]

def find_matching_answers_ai_agent(questions: List[str], existing_submissions: List) -> Dict[str, Any]:
    """AI agent that learns from all historical Q&A pairs to generate better answers"""
    print("DEBUG: Using AI learning agent with historical knowledge base")
    
    # Build knowledge base from all historical submissions
    knowledge_base = build_knowledge_base(existing_submissions)
    print(f"DEBUG: Built knowledge base with {len(knowledge_base)} Q&A pairs")
    
    # If knowledge base is empty, fall back to smart matching
    if len(knowledge_base) == 0:
        print("DEBUG: Knowledge base is empty, falling back to smart matching")
        return find_matching_answers_smart_matching(questions, existing_submissions)
    
    matches = []
    
    for i, question in enumerate(questions):
        print(f"DEBUG: AI agent processing question {i+1}/{len(questions)}: {question[:50]}...")
        
        # Use AI to find and synthesize the best answer from knowledge base
        ai_answer = generate_ai_answer(question, knowledge_base)
        
        if ai_answer['confidence'] > 30:  # AI found a good answer
            matches.append({
                "question": question,
                "suggested_answer": ai_answer['answer'],
                "confidence": ai_answer['confidence'],
                "source_rfp": ai_answer['source'],
                "category": "ai_generated",
                "source_status": ai_answer['status'],
                "matching_reason": f"AI agent synthesis (confidence: {ai_answer['confidence']}%)"
            })
        else:
            # Provide a fallback answer based on question type
            question_type = classify_question_type(question.lower())
            fallback_answer = get_fallback_answer(question, question_type)
            matches.append({
                "question": question,
                "suggested_answer": fallback_answer,
                "confidence": 10,
                "source_rfp": "None",
                "category": "no_match",
                "source_status": "unknown",
                "matching_reason": f"AI agent could not find good answer (confidence: {ai_answer['confidence']}%)"
            })
    
    return {
        "matches": matches,
        "overall_confidence": sum(m['confidence'] for m in matches) // len(matches) if matches else 0,
        "total_questions_found": len(questions),
        "questions_answered": len(matches),
        "debug_info": {
            "qa_pairs_found": len(knowledge_base),
            "submissions_processed": len(existing_submissions),
            "method": "ai_learning_agent",
            "first_qa_pair": knowledge_base[0] if knowledge_base else None
        }
    }

def build_knowledge_base(existing_submissions: List) -> List[Dict]:
    """Build a comprehensive knowledge base from all historical submissions"""
    knowledge_base = []
    
    for submission in existing_submissions:
        if len(submission) > 4 and submission[4]:
            try:
                data = json.loads(submission[4])
                print(f"DEBUG: Building knowledge base from {submission[1]}, keys: {list(data.keys())}")
                
                if 'question_answer_pairs' in data:
                    pairs = data['question_answer_pairs']
                    print(f"DEBUG: Found {len(pairs)} question_answer_pairs in {submission[1]}")
                    for pair in pairs:
                        if isinstance(pair, dict) and 'question' in pair and 'answer' in pair:
                            knowledge_base.append({
                                'question': pair['question'],
                                'answer': pair['answer'],
                                'source': submission[1],
                                'status': submission[5] if len(submission) > 5 else 'unknown',
                                'question_type': classify_question_type(pair['question'].lower())
                            })
                elif 'all_questions_found' in data:
                    questions_found = data['all_questions_found']
                    print(f"DEBUG: Found all_questions_found in {submission[1]}: {len(questions_found) if isinstance(questions_found, list) else 'not a list'}")
                    if isinstance(questions_found, list) and len(questions_found) > 0:
                        if isinstance(questions_found[0], dict) and 'question' in questions_found[0] and 'answer' in questions_found[0]:
                            for pair in questions_found:
                                if isinstance(pair, dict) and 'question' in pair and 'answer' in pair:
                                    knowledge_base.append({
                                        'question': pair['question'],
                                        'answer': pair['answer'],
                                        'source': pair.get('source', submission[1]),
                                        'status': submission[5] if len(submission) > 5 else 'unknown',
                                        'question_type': classify_question_type(pair['question'].lower())
                                    })
                else:
                    print(f"DEBUG: No Q&A data found in {submission[1]}. Available keys: {list(data.keys())}")
            except Exception as e:
                print(f"DEBUG: Error parsing submission {submission[1]}: {e}")
                continue
    
    print(f"DEBUG: Built knowledge base with {len(knowledge_base)} Q&A pairs")
    return knowledge_base

def generate_ai_answer(question: str, knowledge_base: List[Dict]) -> Dict[str, Any]:
    """Use AI to generate the best answer from the knowledge base"""
    try:
        print(f"DEBUG: Starting AI answer generation for question: {question[:50]}...")
        
        # Find relevant Q&A pairs using semantic similarity
        relevant_pairs = find_relevant_qa_pairs(question, knowledge_base)
        print(f"DEBUG: Found {len(relevant_pairs)} relevant pairs")
        
        if not relevant_pairs:
            print("DEBUG: No relevant pairs found, returning fallback")
            return {
                'answer': 'No relevant information found in knowledge base.',
                'confidence': 10,
                'source': 'None',
                'status': 'unknown'
            }
        
        # Use AI to synthesize the best answer from relevant pairs
        synthesis_prompt = f"""
        You are an expert RFP response specialist. Based on the following question and relevant historical answers, generate the best possible response.

        NEW QUESTION: {question}

        RELEVANT HISTORICAL ANSWERS:
        """
        
        for i, pair in enumerate(relevant_pairs[:5]):  # Use top 5 most relevant
            synthesis_prompt += f"""
        Historical Answer {i+1} (from {pair['source']}):
        Question: {pair['question']}
        Answer: {pair['answer']}
        """
        
        synthesis_prompt += """
        
        INSTRUCTIONS:
        1. Generate a comprehensive answer that directly addresses the new question
        2. Use the most relevant information from the historical answers
        3. Combine multiple relevant answers if needed
        4. Ensure the answer is specific and actionable
        5. Clean up any brand names or client-specific information
        6. Make the answer professional and complete
        
        RESPONSE FORMAT (JSON only):
        {
            "answer": "Your synthesized answer here",
            "confidence": 85,
            "reasoning": "Why this answer is relevant and complete"
        }
        """
        
        print("DEBUG: About to call OpenAI API")
        # Call OpenAI to synthesize the answer
        import openai
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": synthesis_prompt}],
            max_tokens=1000,
            temperature=0.3
        )
        print("DEBUG: OpenAI API call completed")
        
        result = json.loads(response.choices[0].message.content)
        print(f"DEBUG: AI generated answer with confidence: {result.get('confidence', 'unknown')}")
        
        return {
            'answer': clean_brand_names(result['answer']),
            'confidence': result['confidence'],
            'source': relevant_pairs[0]['source'],
            'status': relevant_pairs[0]['status']
        }
        
    except Exception as e:
        print(f"DEBUG: Error in AI answer generation: {e}")
        import traceback
        traceback.print_exc()
        return {
            'answer': 'Error generating AI answer.',
            'confidence': 10,
            'source': 'None',
            'status': 'unknown'
        }

def find_relevant_qa_pairs(question: str, knowledge_base: List[Dict]) -> List[Dict]:
    """Find the most relevant Q&A pairs for a given question"""
    question_lower = question.lower()
    question_words = set(question_lower.split())
    question_type = classify_question_type(question_lower)
    
    scored_pairs = []
    
    for pair in knowledge_base:
        # Calculate relevance score
        score = calculate_relevance_score(question, pair['question'], question_type, pair)
        
        if score > 0.2:  # Only include reasonably relevant pairs
            scored_pairs.append((score, pair))
    
    # Sort by relevance score and return top matches
    scored_pairs.sort(key=lambda x: x[0], reverse=True)
    return [pair for score, pair in scored_pairs[:10]]  # Return top 10 most relevant

def calculate_relevance_score(new_question: str, historical_question: str, question_type: str, pair: Dict) -> float:
    """Calculate how relevant a historical Q&A pair is to a new question"""
    new_lower = new_question.lower()
    hist_lower = historical_question.lower()
    answer_lower = pair['answer'].lower()
    
    # Start with word overlap
    new_words = set(new_lower.split())
    hist_words = set(hist_lower.split())
    common_words = new_words & hist_words
    
    if not common_words:
        return 0.0
    
    base_score = len(common_words) / max(len(new_words), len(hist_words))
    
    # Boost for same question type
    if pair.get('question_type') == question_type:
        base_score += 0.3
    
    # Boost for exact phrase matches
    if any(phrase in hist_lower for phrase in ['sample login', 'demo', 'dependents', 'fitness for duty', 'implementation']):
        base_score += 0.2
    
    # Boost for comprehensive answers
    if len(pair['answer']) > 100:
        base_score += 0.1
    
    # Penalize very short or generic answers
    if len(pair['answer']) < 20 or answer_lower in ['yes', 'no', 'n/a', 'tbd']:
        base_score -= 0.3
    
    return max(0.0, min(1.0, base_score))

# # def find_matching_answers_embeddings(questions: List[str], existing_submissions: List) -> Dict[str, Any]:
# #     """Find matching answers using embeddings for all questions - quality over speed"""
#     
#     try:
#         print(f"DEBUG: Starting embeddings matching for {len(questions)} questions")
#         
#         if not existing_submissions:
#             return {
#                 "matches": [], 
#                 "overall_confidence": 0,
#                 "total_questions_found": len(questions),
#                 "questions_answered": 0,
#                 "debug_info": {"qa_pairs_found": 0, "submissions_processed": 0}
#             }
#         
#         # Extract all Q&A pairs from existing submissions
#         all_qa_pairs = []
#     for submission in existing_submissions:
#         if len(submission) > 4 and submission[4]:
#             try:
#                 data = json.loads(submission[4])
#                 
#                 if 'question_answer_pairs' in data:
#                     for pair in data['question_answer_pairs']:
#                         if isinstance(pair, dict) and 'question' in pair and 'answer' in pair:
#                             all_qa_pairs.append({
#                                 'question': pair['question'],
#                                 'answer': pair['answer'],
#                                 'source': submission[1],
#                                 'status': submission[5] if len(submission) > 5 else 'unknown'
#                             })
#                 elif 'all_questions_found' in data:
#                     questions_found = data['all_questions_found']
#                     if isinstance(questions_found, list) and len(questions_found) > 0:
#                         if isinstance(questions_found[0], dict) and 'question' in questions_found[0] and 'answer' in questions_found[0]:
#                             for pair in questions_found:
#                                 if isinstance(pair, dict) and 'question' in pair and 'answer' in pair:
#                                     all_qa_pairs.append({
#                                         'question': pair['question'],
#                                         'answer': pair['answer'],
#                                         'source': submission[1],
#                                         'status': submission[5] if len(submission) > 5 else 'unknown'
#                                     })
#             except Exception as e:
#                 print(f"DEBUG: Error parsing submission {submission[1]}: {e}")
#                 continue
#     
#     print(f"DEBUG: Found {len(all_qa_pairs)} Q&A pairs from {len(existing_submissions)} submissions")
#     
#     if not all_qa_pairs:
#         return {
#             "matches": [], 
#             "overall_confidence": 0,
#             "total_questions_found": len(questions),
#             "questions_answered": 0,
#             "debug_info": {"qa_pairs_found": 0, "submissions_processed": len(existing_submissions)}
#         }
#     
#     matches = []
#     
#     # For each new question, find the best matching answer using embeddings
#     used_answers = set()
#     
#     for i, question in enumerate(questions):  # Process ALL questions
#         print(f"DEBUG: Processing question {i+1}/{len(questions)}: {question[:100]}...")
#         
#         # Use embeddings for ALL questions for best quality
#         print(f"DEBUG: Using embeddings for question: {question[:50]}...")
#         try:
#             new_question_embedding = get_question_embedding(question)
#             if new_question_embedding is None:
#                 print(f"DEBUG: Failed to get embedding for question {i+1}")
#                 # Provide fallback answer
#                 fallback_answer = get_fallback_answer(question, classify_question_type(question.lower()))
#                 matches.append({
#                     "question": question,
#                     "suggested_answer": fallback_answer,
#                     "confidence": 10,
#                     "source_rfp": "None",
#                     "category": "no_match",
#                     "source_status": "unknown",
#                     "matching_reason": "Failed to get embedding"
#                 })
#                 continue
#             
#             best_match = None
#             best_similarity = 0
#             
#             # Find the most similar historical question (check all for best quality)
#             for qa_pair in all_qa_pairs:
#                 # Skip if we've already used this exact answer
#                 answer_hash = hash(qa_pair['answer'][:200])
#                 if answer_hash in used_answers:
#                     continue
#                 
#                 # Skip obviously irrelevant answers
#                 answer_lower = qa_pair['answer'].lower()
#                 if len(answer_lower) < 10 or answer_lower in ['no answer provided', 'n/a', 'tbd', 'to be determined']:
#                     continue
#                 
#                 # Skip if answer is just a name/email
#                 if '@' in qa_pair['answer'] and len(qa_pair['answer']) < 100:
#                     continue
#                 
#                 # Get embedding for historical question
#                 try:
#                     hist_question_embedding = get_question_embedding(qa_pair['question'])
#                     if hist_question_embedding is None:
#                         continue
#                 except Exception as e:
#                     print(f"DEBUG: Error getting embedding for historical question: {e}")
#                     continue
#                 
#                 # Calculate cosine similarity
#                 similarity = calculate_cosine_similarity(new_question_embedding, hist_question_embedding)
#                 
#                 if similarity > best_similarity:
#                     best_similarity = similarity
#                     best_match = qa_pair
#             
#             # Apply similarity threshold
#             if best_match and best_similarity > 0.7:  # High threshold for quality matches
#                 # Mark this answer as used
#                 answer_hash = hash(best_match['answer'][:200])
#                 used_answers.add(answer_hash)
#                 
#                 # Clean brand names from the answer
#                 cleaned_answer = clean_brand_names(best_match['answer'])
#                 
#                 # Make answers more concise for certain question types
#                 cleaned_answer = make_answer_concise(question, cleaned_answer)
#                 
#                 matches.append({
#                     "question": question,
#                     "suggested_answer": cleaned_answer,
#                     "confidence": min(95, int(best_similarity * 100)),
#                     "source_rfp": best_match['source'],
#                     "category": "matched",
#                     "source_status": best_match['status'],
#                     "matching_reason": f"Embedding match (similarity: {best_similarity:.3f})"
#                 })
#             else:
#                 # Provide a fallback answer based on question type
#                 fallback_answer = get_fallback_answer(question, classify_question_type(question.lower()))
#                 print(f"DEBUG: No good match found for question {i+1}, best similarity was {best_similarity:.3f}")
#                 matches.append({
#                     "question": question,
#                     "suggested_answer": fallback_answer,
#                     "confidence": 10,
#                     "source_rfp": "None",
#                     "category": "no_match",
#                     "source_status": "unknown",
#                     "matching_reason": f"No match found (best similarity: {best_similarity:.3f})"
#                 })
#                 
#         except Exception as e:
#             print(f"DEBUG: Error with embeddings for question {i+1}: {e}")
#             # Provide fallback answer
#             fallback_answer = get_fallback_answer(question, classify_question_type(question.lower()))
#             matches.append({
#                 "question": question,
#                 "suggested_answer": fallback_answer,
#                 "confidence": 10,
#                 "source_rfp": "None",
#                 "category": "no_match",
#                 "source_status": "unknown",
#                 "matching_reason": f"Embedding error: {str(e)[:50]}"
#             })
#     
#         return {
#             "matches": matches,
#             "overall_confidence": sum(m['confidence'] for m in matches) // len(matches) if matches else 0,
#             "total_questions_found": len(questions),
#             "questions_answered": len(matches),
#             "debug_info": {
#                 "qa_pairs_found": len(all_qa_pairs),
#                 "submissions_processed": len(existing_submissions),
#                 "first_qa_pair": all_qa_pairs[0] if all_qa_pairs else None
#             }
#         }
#     
#     except Exception as e:
#         print(f"DEBUG: CRITICAL ERROR in embeddings matching: {e}")
#         import traceback
#         traceback.print_exc()
#         
#         # Use simple fallback matching instead of returning empty results
#         print("DEBUG: Falling back to simple keyword matching")
#         return find_matching_answers_simple_fallback(questions, existing_submissions)
# 
def calculate_direct_match_score(new_question: str, historical_question: str, question_type: str, qa_pair: dict) -> float:
    """Calculate direct matching score based on semantic similarity and question type"""
    new_q_lower = new_question.lower()
    hist_q_lower = historical_question.lower()
    
    score = 0.0
    
    # 1. Exact question match (highest confidence)
    if new_q_lower == hist_q_lower:
        return 1.0
    
    # 2. Check for completely incompatible question types first
    if is_incompatible_question_types(new_question, historical_question):
        return 0.0
    
    # 3. Extract key phrases from both questions
    new_phrases = extract_key_phrases(new_q_lower)
    hist_phrases = extract_key_phrases(hist_q_lower)
    
    # 4. Calculate phrase overlap
    common_phrases = set(new_phrases) & set(hist_phrases)
    if not common_phrases:
        return 0.0
    
    # 5. Calculate semantic similarity based on phrase overlap
    phrase_similarity = len(common_phrases) / max(len(new_phrases), len(hist_phrases))
    
    # 6. Require minimal overlap for a good match (very flexible)
    if phrase_similarity < 0.05:  # Need at least 5% phrase overlap
        return 0.0
    
    # 7. Boost score based on question type compatibility
    if question_type == classify_question_type(hist_q_lower):
        score = phrase_similarity * 0.8  # Good match
    else:
        score = phrase_similarity * 0.4  # Weaker match
    
    return min(1.0, score)

def is_incompatible_question_types(new_question: str, historical_question: str) -> bool:
    """Check if two questions are completely incompatible (should never match)"""
    new_lower = new_question.lower()
    hist_lower = historical_question.lower()
    
    # Login questions should never match pricing questions
    if ('sample' in new_lower and 'login' in new_lower) and ('pricing' in hist_lower or 'pepm' in hist_lower):
        return True
    
    # Geo access questions should never match IT security questions
    if ('geo' in new_lower and 'access' in new_lower) and ('rbac' in hist_lower or 'role-based' in hist_lower):
        return True
    
    # Network questions should never match pricing questions
    if ('network' in new_lower or 'provider' in new_lower) and ('pricing' in hist_lower or 'pepm' in hist_lower):
        return True
    
    # Implementation questions should never match pricing questions
    if ('implementation' in new_lower and 'timeline' in new_lower) and ('pricing' in hist_lower or 'pepm' in hist_lower):
        return True
    
    # Fees/ROI questions should never match cultural care questions
    if ('fees' in new_lower and 'risk' in new_lower) and ('cultural' in hist_lower or 'language' in hist_lower):
        return True
    
    # Network count questions should never match language questions
    if ('how many' in new_lower and ('coach' in new_lower or 'provider' in new_lower)) and ('language' in hist_lower or 'cultural' in hist_lower):
        return True
    
    return False

def find_fallback_match(question: str, all_qa_pairs: List[dict], question_type: str) -> dict:
    """Find the best available answer when strict matching fails"""
    question_lower = question.lower()
    best_fallback = None
    best_score = 0
    
    for qa_pair in all_qa_pairs:
        # Skip obviously irrelevant answers
        answer_lower = qa_pair['answer'].lower()
        if len(answer_lower) < 10 or answer_lower in ['no answer provided', 'n/a', 'tbd', 'to be determined']:
            continue
        
        # Skip if answer is just a name/email
        if '@' in qa_pair['answer'] and len(qa_pair['answer']) < 100:
            continue
        
        # Calculate a simple fallback score based on question type
        score = 0.0
        hist_q_lower = qa_pair['question'].lower()
        
        # Boost for same question type
        if question_type == classify_question_type(hist_q_lower):
            score += 0.3
        
        # Skip obviously wrong matches - check the ANSWER content, not question
        answer_lower = qa_pair['answer'].lower()
        if 'sample' in question_lower and 'login' in question_lower:
            if '2025' in answer_lower or 'roadmap' in answer_lower or 'innovation' in answer_lower:
                print(f"DEBUG: Skipping 2025/roadmap answer for login question: {answer_lower[:100]}...")
                continue  # Skip this answer entirely for login questions
        
        if 'fitness' in question_lower and 'duty' in question_lower:
            if 'adaptive care' in answer_lower or 'well-being assessment' in answer_lower or 'vision' in answer_lower:
                continue  # Skip this answer entirely for fitness-for-duty questions
        
        if 'leave' in question_lower and 'absence' in question_lower:
            if 'manager training' in answer_lower and 'loa' not in answer_lower:
                continue  # Skip this answer entirely for LOA questions
        
        # Skip network questions getting generic platform descriptions
        if 'how many' in question_lower and ('coach' in question_lower or 'provider' in question_lower or 'therapist' in question_lower):
            if 'digital platform' in answer_lower and '86,000' not in answer_lower and 'providers' not in answer_lower:
                continue  # Skip generic platform descriptions for network count questions
        
        # Boost for any keyword overlap
        question_words = set(question_lower.split())
        hist_words = set(hist_q_lower.split())
        common_words = question_words & hist_words
        if common_words:
            score += len(common_words) * 0.1
        
        # Boost for longer, more detailed answers
        if len(qa_pair['answer']) > 100:
            score += 0.1
        
        if score > best_score:
            best_score = score
            best_fallback = qa_pair
    
    # Only return if we found a reasonable fallback (score > 0.3) - be more selective
    return best_fallback if best_score > 0.3 else None

def extract_key_phrases(question: str) -> List[str]:
    """Extract key phrases from a question for matching"""
    # Remove common words and extract meaningful phrases
    common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'please', 'provide', 'any', 'your', 'you', 'we', 'our', 'their', 'this', 'that', 'these', 'those', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'must'}
    
    words = question.lower().split()
    key_phrases = []
    
    # Add individual important words (not just phrases)
    important_words = ['eligibility', 'dependent', 'definition', 'requirements', 'file', 'standards', 'process', 'delivery', 'time', 'fitness', 'duty', 'leave', 'absence', 'loa', 'cism', 'manager', 'referrals', 'implementation', 'timeline', 'plan', 'integration', 'hpi', 'health', 'plan', 'fees', 'performance', 'guarantees', 'geo', 'access', 'census', 'pricing', 'document', 'sample', 'login', 'demo', 'capabilities', 'experience', 'visit', 'limit', 'enrolled', 'medical', 'outline', 'include', 'attachment', 'standard', 'clearly', 'note', 'eligible', 'eap']
    
    for word in words:
        if word not in common_words and len(word) > 2:
            key_phrases.append(word)
    
    # Add 2-word phrases
    for i in range(len(words) - 1):
        phrase = f"{words[i]} {words[i+1]}"
        if not any(word in common_words for word in phrase.split()):
            key_phrases.append(phrase)
    
    # Add 3-word phrases for important terms
    for i in range(len(words) - 2):
        phrase = f"{words[i]} {words[i+1]} {words[i+2]}"
        if any(important in phrase for important in ['geo access', 'visit limit', 'fitness for', 'leave of', 'implementation timeline', 'standard leave', 'manager referrals', 'process flows', 'eligibility file', 'dependent definition', 'health plan', 'performance guarantees']):
            key_phrases.append(phrase)
    
    # Add 4-word phrases for very specific terms
    for i in range(len(words) - 3):
        phrase = f"{words[i]} {words[i+1]} {words[i+2]} {words[i+3]}"
        if any(important in phrase for important in ['leave of absence', 'critical incident', 'stress management', 'fitness for duty', 'health plan integration']):
            key_phrases.append(phrase)
    
    return key_phrases

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
    question_lower = question.lower()
    
    # Provide specific fallback answers for common question types
    if 'network' in question_lower or 'provider' in question_lower or 'table' in question_lower:
        if 'how many' in question_lower and 'total' in question_lower:
            return "Modern Health maintains a global network of 86,000+ licensed providers. Please provide specific provider counts for this category based on your current network data."
        elif 'how many' in question_lower and 'in-person' in question_lower:
            return "Modern Health has providers available both in-person and virtually. Please provide specific in-person provider counts for this category based on your current network data."
        elif 'how many' in question_lower and 'virtual' in question_lower:
            return "Modern Health offers virtual care through our digital platform. Please provide specific virtual provider counts for this category based on your current network data."
        else:
            return "Modern Health maintains a global network of 86,000+ licensed providers including therapists, coaches, and psychiatrists. Please provide specific network details and provider counts based on your current data."
    elif 'geo' in question_lower and 'access' in question_lower:
        return "Modern Health provides global access to mental health services. Please provide specific geographic access requirements and census data details."
    elif 'dependent' in question_lower and 'definition' in question_lower:
        return "Modern Health follows the eligibility requirements of each client. The Client determines dependent definitions and eligibility rules. Adult dependents can register themselves, while dependents under 18 need employee invitation."
    elif 'eligibility' in question_lower and 'file' in question_lower:
        return "Modern Health requires eligibility files containing employee information (name, email, ID). Files can be sent monthly, biweekly, or weekly via Box or SFTP. We integrate with Workday and other HR systems."
    elif 'fitness' in question_lower and 'duty' in question_lower:
        return "Modern Health can provide fitness-for-duty assessments and processes. We work with licensed providers who can conduct fitness-for-duty evaluations according to your organization's standards and requirements. Please provide specific details about your fitness-for-duty requirements and delivery timeframes."
    elif 'leave' in question_lower and 'absence' in question_lower:
        return "Modern Health supports leave of absence processes and critical incident stress management (CISM). We provide manager referrals, LOA process flows, and CISM services through our network of licensed providers. Please provide specific details about your LOA process flows and CISM requirements."
    elif 'implementation' in question_lower and 'timeline' in question_lower:
        return "Modern Health typically implements programs within 4-6 weeks. Implementation includes setup, integration, and employee launch. Please provide your specific implementation timeline and plan details."
    elif 'sample' in question_lower and 'login' in question_lower:
        return "Modern Health can provide a sample login or demo environment to showcase our platform capabilities. Please contact us to schedule a personalized demonstration of our mental health platform."
    elif 'geo' in question_lower and 'access' in question_lower:
        return "Modern Health provides global access to mental health services. Please provide specific geographic access requirements and census data details."
    elif 'financial' in question_lower and 'template' in question_lower:
        return "Modern Health can provide detailed financial templates and utilization assumptions. Please provide your specific financial requirements and utilization expectations."
    elif 'fees' in question_lower and ('guaranteed' in question_lower or 'risk' in question_lower):
        return "Modern Health offers flexible fee structures and performance guarantees. Please provide your specific requirements for fee guarantees and risk arrangements."
    elif 'performance' in question_lower and 'guarantee' in question_lower:
        return "Modern Health provides performance guarantees based on engagement and outcomes. Please provide your specific performance guarantee requirements."
    else:
        return "No specific answer found in historical RFPs. Please provide a custom answer based on your specific requirements."

def clean_brand_names(text: str) -> str:
    """Remove competitor brand names and update company information"""
    # List of competitor names to remove
    brand_names = [
        'Henry Schein', 'Voya Financial', 'Voya', 'Barclays', 'Boston Scientific', 
        'Mattel', 'Sunrun', 'Stripe', 'Uber', 'Palo Alto Networks', 'Electronic Arts',
        'McDermott Will & Emery', 'McDermott', 'AMD', 'JET', 'Central Texas Food Bank',
        'MWE', 'Loopio', 'EXHIBIT', 'Wellness Platform', 'PROPOSAL WORKBOOK'
    ]
    
    cleaned_text = text
    
    # Remove competitor brand names
    for brand in brand_names:
        cleaned_text = cleaned_text.replace(brand, '[Client]')
        cleaned_text = cleaned_text.replace(brand.lower(), '[client]')
        cleaned_text = cleaned_text.replace(brand.upper(), '[CLIENT]')
    
    # Update outdated company information
    cleaned_text = cleaned_text.replace('Modern Health Arizona, PLLC', 'Modern Health LLC')
    cleaned_text = cleaned_text.replace('Modern Health Arizona, PLLC,', 'Modern Health LLC,')
    cleaned_text = cleaned_text.replace('650 California Street, Fl. 7, Office 07-128, San Francisco, CA', '[Current Address]')
    cleaned_text = cleaned_text.replace('650 California Street, Fl. 7, Office 07-128, San Francisco, CA.', '[Current Address].')
    
    return cleaned_text

def make_answer_concise(question: str, answer: str) -> str:
    """Make answers more concise for certain question types"""
    question_lower = question.lower()
    
    # For visit limit questions, provide a more direct answer
    if 'visit' in question_lower and 'limit' in question_lower:
        if 'digital platform' in answer.lower() and len(answer) > 200:
            return "When members reach their visit limit, they can continue with digital programs, meditations, and Circles. They can also use health plan integration to continue with their provider, pay out-of-pocket, or seek care through their insurance network."
    
    # For implementation timeline questions, keep it short
    if 'implementation' in question_lower and 'timeline' in question_lower:
        if len(answer) > 100:
            # Extract just the timeline if it's buried in longer text
            import re
            timeline_match = re.search(r'(\d+[-–]\d+\s*weeks?)', answer, re.IGNORECASE)
            if timeline_match:
                return f"Implementation typically takes {timeline_match.group(1)}."
            else:
                return "Implementation typically takes 4-6 weeks."
    
    # For network questions, keep it focused on numbers
    if 'how many' in question_lower and ('provider' in question_lower or 'coach' in question_lower or 'therapist' in question_lower):
        if len(answer) > 150:
            # Extract numbers from the answer
            import re
            numbers = re.findall(r'\d+[,\d]*\+?', answer)
            if numbers:
                return f"Modern Health has {numbers[0]} providers available globally."
    
    return answer

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
        ["Dashboard", "Upload Historical RFP", "Process New RFP", "Upload Corrected RFP", "Browse Database", "Search", "Export Data", "Ask Questions"]
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
    elif page == "Ask Questions":
        show_question_page(client)

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
                
            print("DEBUG: Finished showing historical data, about to call AI learning agent")
            st.write("🔍 **Debug: About to call matching function**")
            print("DEBUG: About to call find_matching_answers_simple")
            print(f"DEBUG: Questions count: {len(questions)}")
            print(f"DEBUG: Existing submissions count: {len(existing_submissions)}")
            # Use simple matching with low threshold to get more matches
            st.write("🔍 **Debug: About to call AI knowledge system**")
            matches = find_matching_answers_simple(questions, existing_submissions)
            print("DEBUG: find_matching_answers_simple completed")
            
            # Show debug info about AI knowledge system
            if matches and 'debug_info' in matches:
                st.write(f"🔍 **Debug: AI Knowledge System Results**")
                st.write(f"Method: {matches['debug_info']['method']}")
                st.write(f"Knowledge base entries: {matches['debug_info']['qa_pairs_found']}")
                st.write(f"Submissions processed: {matches['debug_info']['submissions_processed']}")
                
                # Count how many answers came from AI knowledge vs contextual
                ai_knowledge_count = sum(1 for match in matches['matches'] if match.get('category') == 'ai_knowledge')
                contextual_count = sum(1 for match in matches['matches'] if match.get('category') == 'ai_contextual')
                st.write(f"AI Knowledge answers: {ai_knowledge_count}")
                st.write(f"Contextual fallback answers: {contextual_count}")
                
                # Show sample matching reasons to understand why AI knowledge failed
                if contextual_count > 0:
                    st.write("**Sample AI Knowledge System Failures:**")
                    sample_failures = [match for match in matches['matches'] if match.get('category') == 'ai_contextual'][:3]
                    for i, failure in enumerate(sample_failures):
                        st.write(f"{i+1}. {failure.get('matching_reason', 'Unknown reason')}")
                    
                    # Show API key test result
                    st.write("**API Key Test:**")
                    api_status = test_openai_api_key()
                    st.write(api_status)
            
            # Show debug info from AI agent
            if "debug_info" in matches:
                st.write("🔍 **Debug: AI Learning Agent Results**")
                st.write(f"Method: {matches['debug_info']['method']}")
                st.write(f"Knowledge base size: {matches['debug_info']['qa_pairs_found']} Q&A pairs")
                st.write(f"Submissions processed: {matches['debug_info']['submissions_processed']}")
                if matches['debug_info'].get('first_qa_pair'):
                    if isinstance(matches['debug_info']['first_qa_pair'], dict):
                        st.write(f"Sample knowledge: {matches['debug_info']['first_qa_pair']['question'][:100]}...")
                    else:
                        st.write(f"Knowledge base type: {type(matches['debug_info']['first_qa_pair'])}")
                        st.write(f"Knowledge base preview: {str(matches['debug_info']['first_qa_pair'])[:200]}...")
                else:
                    st.write("No knowledge base built from submissions")
                
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

def show_question_page(client):
    """Show the question answering interface"""
    st.header("🤖 Ask Questions")
    st.markdown("Ask any question about Modern Health's capabilities and get the best possible answer from our RFP knowledge base.")
    
    # Get existing submissions to build knowledge base
    try:
        existing_submissions = get_all_submissions()
        if not existing_submissions:
            st.warning("⚠️ No historical RFPs found. Upload some RFPs first to build the knowledge base.")
            return
        
        # Build knowledge base
        modern_health_knowledge = build_modern_health_knowledge_base(existing_submissions)
        
        if not modern_health_knowledge or len(modern_health_knowledge) < 100:
            st.warning("⚠️ Knowledge base is too small. Upload more RFPs to get better answers.")
            return
            
    except Exception as e:
        st.error(f"❌ Error building knowledge base: {str(e)}")
        return
    
    # Question input
    st.subheader("💬 Ask Your Question")
    question = st.text_area(
        "What would you like to know about Modern Health?",
        placeholder="e.g., How many therapists do you have? What's your implementation timeline? Do you offer fitness-for-duty evaluations?",
        height=100
    )
    
    if st.button("🔍 Get Answer", type="primary"):
        if not question.strip():
            st.warning("Please enter a question first.")
            return
        
        with st.spinner("🤔 Thinking... Generating the best possible answer..."):
            try:
                # Use the same logic as the main system
                ai_answer = generate_answer_from_knowledge_base(question, modern_health_knowledge)
                
                if ai_answer and len(ai_answer) > 20:
                    # Check if we should use fallback for specific question types
                    question_lower = question.lower()
                    
                    # Provider count questions
                    if any(word in question_lower for word in ['how many', 'coaches', 'therapists', 'psychiatrists', 'providers']) and ('not available' in ai_answer.lower() or 'does not have specific' in ai_answer.lower() or 'does not provide' in ai_answer.lower()):
                        st.info("🔄 AI knowledge system gave generic response, using contextual generation...")
                        generated_answer = generate_contextual_answer(question)
                        answer = generated_answer or "Please provide a custom answer based on your specific requirements."
                        confidence = 80
                        source = "AI Generated (Contextual Fallback)"
                        method = "Contextual Generation"
                        
                    # Fitness-for-duty questions
                    elif ('fitness for duty' in question_lower or 'fitness-for-duty' in question_lower) and ('does not have specific' in ai_answer.lower() or 'not available' in ai_answer.lower()):
                        st.info("🔄 AI knowledge system gave generic response, using contextual generation...")
                        generated_answer = generate_contextual_answer(question)
                        answer = generated_answer or "Please provide a custom answer based on your specific requirements."
                        confidence = 80
                        source = "AI Generated (Contextual Fallback)"
                        method = "Contextual Generation"
                        
                    else:
                        answer = ai_answer
                        confidence = 90
                        source = "AI Knowledge System - Modern Health"
                        method = "AI Knowledge Base"
                        
                else:
                    st.info("🔄 AI knowledge system couldn't find specific information, using contextual generation...")
                    generated_answer = generate_contextual_answer(question)
                    answer = generated_answer or "Please provide a custom answer based on your specific requirements."
                    confidence = 60
                    source = "AI Generated (Contextual Fallback)"
                    method = "Contextual Generation"
                
                # Display the answer
                st.subheader("📝 Answer")
                st.write(answer)
                
                # Show metadata
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Confidence", f"{confidence}%")
                with col2:
                    st.metric("Source", source)
                with col3:
                    st.metric("Method", method)
                
                # Show knowledge base info
                with st.expander("🔍 Knowledge Base Information"):
                    st.write(f"**Knowledge Base Size:** {len(modern_health_knowledge):,} characters")
                    st.write(f"**Historical RFPs:** {len(existing_submissions)} submissions")
                    st.write(f"**Answer Method:** {method}")
                    
                    if method == "AI Knowledge Base":
                        st.success("✅ Answer generated from comprehensive Modern Health knowledge base")
                    else:
                        st.info("ℹ️ Answer generated using contextual knowledge and industry standards")
                
            except Exception as e:
                st.error(f"❌ Error generating answer: {str(e)}")
                st.exception(e)
    
    # Show example questions
    st.subheader("💡 Example Questions")
    example_questions = [
        "How many mental health coaches do you have in the US?",
        "What's your implementation timeline?",
        "Do you provide fitness-for-duty evaluations?",
        "What are your eligibility file requirements?",
        "Can you provide a sample login for demos?",
        "What's your definition of dependents?",
        "Do you offer leave of absence support?",
        "What are your performance guarantees?",
        "How do you handle health plan integration?",
        "What's your ROI methodology?"
    ]
    
    cols = st.columns(2)
    for i, example in enumerate(example_questions):
        with cols[i % 2]:
            if st.button(f"📋 {example}", key=f"example_{i}"):
                st.session_state.example_question = example
                st.rerun()
    
    # Handle example question selection
    if hasattr(st.session_state, 'example_question'):
        st.text_area("Selected example:", value=st.session_state.example_question, disabled=True)
        if st.button("Use This Question"):
            question = st.session_state.example_question
            del st.session_state.example_question
            st.rerun()

if __name__ == "__main__":
    main()
