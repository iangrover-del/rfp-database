import os
import io
from typing import Dict, List, Any, Optional
from docx import Document
import PyPDF2
import pandas as pd
from openai import OpenAI
import json
import re
from datetime import datetime

class DocumentProcessor:
    """Handles document parsing and content extraction"""
    
    def __init__(self, openai_api_key: str):
        self.client = OpenAI(api_key=openai_api_key)
        
    def extract_text_from_file(self, file_path: str, filename: str) -> str:
        """Extract text content from various file formats"""
        file_extension = filename.lower().split('.')[-1]
        
        try:
            if file_extension == 'pdf':
                return self._extract_from_pdf(file_path)
            elif file_extension == 'docx':
                return self._extract_from_docx(file_path)
            elif file_extension in ['xlsx', 'xls']:
                return self._extract_from_excel(file_path)
            elif file_extension == 'txt':
                return self._extract_from_txt(file_path)
            else:
                raise ValueError(f"Unsupported file format: {file_extension}")
        except Exception as e:
            raise Exception(f"Error extracting text from {filename}: {str(e)}")
    
    def _extract_from_pdf(self, file_path: str) -> str:
        """Extract text from PDF file"""
        text = ""
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        return text
    
    def _extract_from_docx(self, file_path: str) -> str:
        """Extract text from DOCX file"""
        doc = Document(file_path)
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text
    
    def _extract_from_excel(self, file_path: str) -> str:
        """Extract text from Excel file"""
        df = pd.read_excel(file_path)
        return df.to_string()
    
    def _extract_from_txt(self, file_path: str) -> str:
        """Extract text from TXT file"""
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()

class RFPAnswerExtractor:
    """Extracts structured answers from RFP documents using AI"""
    
    def __init__(self, openai_api_key: str):
        self.client = OpenAI(api_key=openai_api_key)
        self.document_processor = DocumentProcessor(openai_api_key)
        
    def extract_answers_from_rfp(self, file_path: str, filename: str) -> Dict[str, Any]:
        """Extract structured answers from an RFP document"""
        
        # Extract text content
        content = self.document_processor.extract_text_from_file(file_path, filename)
        
        # Use AI to extract structured answers
        extracted_data = self._ai_extract_answers(content, filename)
        
        return {
            "filename": filename,
            "original_content": content,
            "extracted_answers": extracted_data,
            "company_name": self._extract_company_name(content),
            "is_processed": True
        }
    
    def _ai_extract_answers(self, content: str, filename: str) -> Dict[str, Any]:
        """Use OpenAI to extract structured answers from RFP content"""
        
        prompt = f"""
        Analyze this RFP document and extract key information in a structured format. 
        The document appears to be: {filename}
        
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
        {content[:8000]}  # Limit content to avoid token limits
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an expert at analyzing RFP documents and extracting structured information. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            # Parse the JSON response
            extracted_data = json.loads(response.choices[0].message.content)
            return extracted_data
            
        except Exception as e:
            print(f"Error in AI extraction: {str(e)}")
            return {
                "error": f"Failed to extract answers: {str(e)}",
                "raw_content": content[:1000]  # Store first 1000 chars as fallback
            }
    
    def _extract_company_name(self, content: str) -> Optional[str]:
        """Extract company name from content using simple heuristics"""
        
        # Look for common patterns
        patterns = [
            r"Company:\s*([^\n\r]+)",
            r"Organization:\s*([^\n\r]+)",
            r"Client:\s*([^\n\r]+)",
            r"Request for Proposal.*?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None

class RFPAnswerMatcher:
    """Matches new RFP questions with existing answers from the database"""
    
    def __init__(self, openai_api_key: str):
        self.client = OpenAI(api_key=openai_api_key)
    
    def find_matching_answers(self, new_rfp_content: str, existing_answers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Find matching answers for a new RFP based on existing submissions"""
        
        if not existing_answers:
            return {"matches": [], "confidence": 0}
        
        # Create a summary of existing answers
        existing_summary = self._create_answers_summary(existing_answers)
        
        prompt = f"""
        You are helping to fill out a new RFP based on previous submissions.
        
        Previous RFP answers database:
        {existing_summary}
        
        New RFP content:
        {new_rfp_content[:4000]}
        
        Please analyze the new RFP and suggest answers based on the previous submissions.
        For each question or section in the new RFP, provide:
        1. The question/section identified
        2. A suggested answer based on previous submissions
        3. A confidence score (0-100) for how well the answer matches
        4. The source RFP that provided the best answer
        
        Format your response as JSON with this structure:
        {{
            "matches": [
                {{
                    "question": "question text",
                    "suggested_answer": "answer text",
                    "confidence": 85,
                    "source_rfp": "filename.pdf",
                    "category": "company_info|technical|business|etc"
                }}
            ],
            "overall_confidence": 75
        }}
        """
        
        try:
            response = self.client.chat.completions.create(
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
            print(f"Error in answer matching: {str(e)}")
            return {"matches": [], "confidence": 0, "error": str(e)}
    
    def _create_answers_summary(self, existing_answers: List[Dict[str, Any]]) -> str:
        """Create a summary of existing answers for AI processing"""
        
        summary = "Previous RFP Submissions:\n\n"
        
        for i, answer in enumerate(existing_answers[:10]):  # Limit to first 10 for token management
            summary += f"RFP {i+1} ({answer.get('filename', 'Unknown')}):\n"
            summary += f"Company: {answer.get('company_name', 'Unknown')}\n"
            
            extracted = answer.get('extracted_answers', {})
            if isinstance(extracted, dict):
                for category, data in extracted.items():
                    if data and isinstance(data, (str, dict)):
                        summary += f"{category}: {str(data)[:200]}...\n"
            
            summary += "\n---\n\n"
        
        return summary
