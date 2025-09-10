#!/usr/bin/env python3
"""
Diagnostic tool to check database content and structure
"""

import sqlite3
import json
import os

def diagnose_database():
    """Diagnose the database structure and content"""
    
    db_path = 'rfp_database.db'
    
    if not os.path.exists(db_path):
        print(f"❌ Database file not found: {db_path}")
        return
    
    print(f"✅ Database file found: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check database schema
        print("\n📋 Database Schema:")
        cursor.execute('PRAGMA table_info(rfp_submissions)')
        columns = cursor.fetchall()
        for col in columns:
            print(f"  {col[1]} ({col[2]})")
        
        # Check total records
        cursor.execute('SELECT COUNT(*) FROM rfp_submissions')
        count = cursor.fetchone()[0]
        print(f"\n📊 Total submissions: {count}")
        
        if count == 0:
            print("❌ No submissions found in database!")
            return
        
        # Check recent submissions
        print("\n📝 Recent submissions:")
        cursor.execute('SELECT id, filename, company_name, created_at FROM rfp_submissions ORDER BY created_at DESC LIMIT 5')
        submissions = cursor.fetchall()
        
        for sub in submissions:
            print(f"  ID: {sub[0]} | File: {sub[1]} | Company: {sub[2]} | Date: {sub[3]}")
        
        # Check content structure
        print("\n🔍 Content structure analysis:")
        cursor.execute('SELECT id, filename, extracted_data FROM rfp_submissions WHERE extracted_data IS NOT NULL LIMIT 3')
        content_subs = cursor.fetchall()
        
        if not content_subs:
            print("❌ No submissions with extracted_data found!")
            
            # Try alternative column names
            cursor.execute('PRAGMA table_info(rfp_submissions)')
            columns = [col[1] for col in cursor.fetchall()]
            print(f"Available columns: {columns}")
            
            # Try to find content in other columns
            for col in ['content', 'extracted_answers', 'original_content']:
                if col in columns:
                    print(f"Trying column: {col}")
                    cursor.execute(f'SELECT id, filename, {col} FROM rfp_submissions WHERE {col} IS NOT NULL LIMIT 1')
                    result = cursor.fetchone()
                    if result:
                        print(f"  Found content in {col}: {len(str(result[2]))} characters")
                        try:
                            data = json.loads(result[2])
                            print(f"  JSON keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
                        except:
                            print(f"  Not valid JSON")
                    else:
                        print(f"  No content in {col}")
        else:
            for sub in content_subs:
                print(f"  Submission {sub[0]}: {sub[1]}")
                try:
                    data = json.loads(sub[2])
                    if isinstance(data, dict):
                        print(f"    JSON keys: {list(data.keys())}")
                        for key, value in data.items():
                            if value and isinstance(value, (str, dict)):
                                print(f"    {key}: {str(value)[:100]}...")
                    else:
                        print(f"    Content: {str(data)[:100]}...")
                except Exception as e:
                    print(f"    Error parsing: {e}")
        
        # Check rfp_answers table
        print("\n📋 RFP Answers table:")
        cursor.execute('SELECT COUNT(*) FROM rfp_answers')
        answer_count = cursor.fetchone()[0]
        print(f"  Total answers: {answer_count}")
        
        if answer_count > 0:
            cursor.execute('SELECT question_category, question_text, answer_text FROM rfp_answers LIMIT 3')
            answers = cursor.fetchall()
            for answer in answers:
                print(f"  Category: {answer[0]} | Question: {answer[1][:50]}... | Answer: {answer[2][:50]}...")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error accessing database: {e}")

if __name__ == "__main__":
    diagnose_database()
