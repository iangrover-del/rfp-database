import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime
import os
from typing import Dict, Any, List

# Configure Streamlit page
st.set_page_config(
    page_title="RFP Database",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

def make_api_request(endpoint: str, method: str = "GET", data: Dict = None, files: Dict = None) -> Dict[str, Any]:
    """Make API request to the FastAPI backend"""
    url = f"{API_BASE_URL}{endpoint}"
    
    try:
        if method == "GET":
            response = requests.get(url)
        elif method == "POST":
            if files:
                response = requests.post(url, files=files)
            else:
                response = requests.post(url, json=data)
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"API Error: {str(e)}")
        return {"error": str(e)}

def main():
    st.title("📋 RFP Database System")
    st.markdown("AI-powered RFP database for automatic answer extraction and matching")
    
    # Sidebar navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.selectbox(
        "Choose a page",
        ["Dashboard", "Upload RFP", "Process New RFP", "Browse Submissions", "Search", "Statistics"]
    )
    
    if page == "Dashboard":
        show_dashboard()
    elif page == "Upload RFP":
        show_upload_page()
    elif page == "Process New RFP":
        show_process_page()
    elif page == "Browse Submissions":
        show_submissions_page()
    elif page == "Search":
        show_search_page()
    elif page == "Statistics":
        show_statistics_page()

def show_dashboard():
    """Show the main dashboard"""
    st.header("Dashboard")
    
    # Get statistics
    stats = make_api_request("/statistics")
    
    if "error" not in stats:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Submissions", stats.get("total_submissions", 0))
        
        with col2:
            st.metric("Processed", stats.get("processed_submissions", 0))
        
        with col3:
            st.metric("Processing Rate", f"{stats.get('processing_rate', 0):.1f}%")
        
        with col4:
            st.metric("Total Answers", stats.get("total_answers", 0))
        
        # Recent submissions
        st.subheader("Recent Submissions")
        recent_submissions = stats.get("recent_submissions", [])
        
        if recent_submissions:
            df = pd.DataFrame(recent_submissions)
            st.dataframe(df[["filename", "company_name", "created_at", "is_processed"]], use_container_width=True)
        else:
            st.info("No recent submissions found")
    
    # Quick actions
    st.subheader("Quick Actions")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📤 Upload New RFP", use_container_width=True):
            st.session_state.page = "Upload RFP"
            st.rerun()
    
    with col2:
        if st.button("🔄 Process New RFP", use_container_width=True):
            st.session_state.page = "Process New RFP"
            st.rerun()

def show_upload_page():
    """Show the RFP upload page"""
    st.header("Upload RFP Document")
    st.markdown("Upload historical RFP documents to build your knowledge base")
    
    uploaded_file = st.file_uploader(
        "Choose an RFP file",
        type=['pdf', 'docx', 'xlsx', 'xls', 'txt'],
        help="Supported formats: PDF, DOCX, XLSX, XLS, TXT"
    )
    
    if uploaded_file is not None:
        st.info(f"Selected file: {uploaded_file.name}")
        
        if st.button("Upload and Process", type="primary"):
            with st.spinner("Processing document..."):
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                result = make_api_request("/upload", method="POST", files=files)
            
            if "error" not in result:
                if result.get("success"):
                    st.success("✅ Document uploaded and processed successfully!")
                    st.json(result)
                else:
                    st.error(f"❌ Upload failed: {result.get('message', 'Unknown error')}")
            else:
                st.error("❌ Upload failed due to API error")

def show_process_page():
    """Show the new RFP processing page"""
    st.header("Process New RFP")
    st.markdown("Upload a new RFP to get AI-suggested answers based on your historical submissions")
    
    uploaded_file = st.file_uploader(
        "Choose a new RFP file",
        type=['pdf', 'docx', 'xlsx', 'xls', 'txt'],
        help="Upload a new RFP to get suggested answers"
    )
    
    if uploaded_file is not None:
        st.info(f"Selected file: {uploaded_file.name}")
        
        if st.button("Process RFP", type="primary"):
            with st.spinner("Analyzing RFP and finding matching answers..."):
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                result = make_api_request("/process", method="POST", files=files)
            
            if "error" not in result:
                if result.get("success"):
                    st.success("✅ RFP processed successfully!")
                    
                    # Display results
                    matches = result.get("matches", {})
                    filled_response = result.get("filled_response", {})
                    
                    st.subheader("Suggested Answers")
                    
                    if matches.get("matches"):
                        for i, match in enumerate(matches["matches"]):
                            with st.expander(f"Question {i+1}: {match.get('question', 'N/A')[:100]}..."):
                                st.write(f"**Suggested Answer:** {match.get('suggested_answer', 'N/A')}")
                                st.write(f"**Confidence:** {match.get('confidence', 0)}%")
                                st.write(f"**Source:** {match.get('source_rfp', 'N/A')}")
                                st.write(f"**Category:** {match.get('category', 'N/A')}")
                    
                    # Download filled response
                    if filled_response:
                        response_json = json.dumps(filled_response, indent=2)
                        st.download_button(
                            label="📥 Download Filled Response",
                            data=response_json,
                            file_name=f"filled_rfp_{uploaded_file.name}.json",
                            mime="application/json"
                        )
                else:
                    st.error(f"❌ Processing failed: {result.get('message', 'Unknown error')}")
            else:
                st.error("❌ Processing failed due to API error")

def show_submissions_page():
    """Show the submissions browsing page"""
    st.header("Browse RFP Submissions")
    
    # Pagination controls
    col1, col2 = st.columns([1, 3])
    
    with col1:
        limit = st.selectbox("Items per page", [10, 25, 50, 100], index=1)
    
    with col2:
        offset = st.number_input("Offset", min_value=0, value=0, step=limit)
    
    if st.button("Load Submissions"):
        with st.spinner("Loading submissions..."):
            result = make_api_request(f"/submissions?limit={limit}&offset={offset}")
        
        if "error" not in result:
            submissions = result.get("submissions", [])
            
            if submissions:
                df = pd.DataFrame(submissions)
                
                # Display basic info
                st.dataframe(
                    df[["id", "filename", "company_name", "created_at", "is_processed"]],
                    use_container_width=True
                )
                
                # Allow viewing details
                selected_id = st.selectbox("Select submission to view details", [s["id"] for s in submissions])
                
                if selected_id:
                    with st.spinner("Loading submission details..."):
                        detail_result = make_api_request(f"/submissions/{selected_id}")
                    
                    if "error" not in detail_result:
                        st.subheader("Submission Details")
                        st.json(detail_result)
            else:
                st.info("No submissions found")
        else:
            st.error("Failed to load submissions")

def show_search_page():
    """Show the search page"""
    st.header("Search RFP Submissions")
    
    search_query = st.text_input("Enter search terms", placeholder="Search by content, company name, or filename")
    
    if search_query:
        if st.button("Search"):
            with st.spinner("Searching..."):
                result = make_api_request(f"/search?q={search_query}")
            
            if "error" not in result:
                results = result.get("results", [])
                
                if results:
                    st.success(f"Found {len(results)} results")
                    
                    df = pd.DataFrame(results)
                    st.dataframe(
                        df[["id", "filename", "company_name", "created_at"]],
                        use_container_width=True
                    )
                    
                    # Show detailed results
                    for i, submission in enumerate(results):
                        with st.expander(f"Result {i+1}: {submission.get('filename', 'N/A')}"):
                            st.write(f"**Company:** {submission.get('company_name', 'N/A')}")
                            st.write(f"**Created:** {submission.get('created_at', 'N/A')}")
                            st.write(f"**Processed:** {submission.get('is_processed', False)}")
                            
                            if submission.get('extracted_answers'):
                                st.write("**Extracted Answers:**")
                                st.json(submission['extracted_answers'])
                else:
                    st.info("No results found")
            else:
                st.error("Search failed")

def show_statistics_page():
    """Show the statistics page"""
    st.header("Statistics")
    
    with st.spinner("Loading statistics..."):
        stats = make_api_request("/statistics")
    
    if "error" not in stats:
        # Key metrics
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Total Submissions", stats.get("total_submissions", 0))
            st.metric("Processed Submissions", stats.get("processed_submissions", 0))
        
        with col2:
            st.metric("Processing Rate", f"{stats.get('processing_rate', 0):.1f}%")
            st.metric("Total Answers", stats.get("total_answers", 0))
        
        # Recent submissions chart
        st.subheader("Recent Activity")
        recent_submissions = stats.get("recent_submissions", [])
        
        if recent_submissions:
            df = pd.DataFrame(recent_submissions)
            df['created_at'] = pd.to_datetime(df['created_at'])
            
            # Group by date
            daily_counts = df.groupby(df['created_at'].dt.date).size()
            
            st.line_chart(daily_counts)
            
            # Show recent submissions table
            st.subheader("Recent Submissions")
            st.dataframe(df[["filename", "company_name", "created_at", "is_processed"]], use_container_width=True)
        else:
            st.info("No recent activity found")
    else:
        st.error("Failed to load statistics")

if __name__ == "__main__":
    main()
