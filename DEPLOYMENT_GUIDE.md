# RFP Database Web App - Deployment Guide

## 🚀 Quick Deployment Options

### Option 1: Streamlit Cloud (Recommended - Free)

1. **Push to GitHub:**
   ```bash
   git init
   git add .
   git commit -m "Initial RFP Database app"
   git remote add origin https://github.com/yourusername/rfp-database.git
   git push -u origin main
   ```

2. **Deploy on Streamlit Cloud:**
   - Go to https://share.streamlit.io
   - Sign in with GitHub
   - Click "New app"
   - Select your repository: `yourusername/rfp-database`
   - Main file path: `rfp_webapp.py`
   - Add your OpenAI API key in the secrets section:
     ```
     OPENAI_API_KEY = "sk-your-actual-key-here"
     ```
   - Click "Deploy"

3. **Your app will be live at:** `https://yourusername-rfp-database-rfp-webapp-xxxxx.streamlit.app`

### Option 2: Heroku (Alternative)

1. **Create Heroku app:**
   ```bash
   heroku create your-rfp-database
   ```

2. **Set environment variables:**
   ```bash
   heroku config:set OPENAI_API_KEY="sk-your-actual-key-here"
   ```

3. **Deploy:**
   ```bash
   git push heroku main
   ```

### Option 3: Local Development

1. **Install dependencies:**
   ```bash
   pip install -r requirements-webapp.txt
   ```

2. **Set environment variable:**
   ```bash
   export OPENAI_API_KEY="sk-your-actual-key-here"
   ```

3. **Run the app:**
   ```bash
   streamlit run rfp_webapp.py
   ```

## 🔧 Configuration

### Required Environment Variables:
- `OPENAI_API_KEY`: Your OpenAI API key (required for AI processing)

### Features:
- ✅ Upload historical RFP documents (PDF, DOCX, TXT)
- ✅ AI-powered content extraction
- ✅ Process new RFPs and get suggested answers
- ✅ Search and browse your RFP database
- ✅ SQLite database (no external database needed)
- ✅ Responsive web interface

## 📱 Usage

1. **Upload Historical RFPs:** Build your knowledge base by uploading past RFP submissions
2. **Process New RFPs:** Upload new RFPs to get AI-suggested answers
3. **Browse Database:** View all your uploaded RFPs
4. **Search:** Find specific RFPs by content, company, or filename

## 🔒 Security

- API keys are stored securely in Streamlit secrets
- All data is stored locally in SQLite database
- No external database connections required

## 💰 Cost

- **Streamlit Cloud:** Free hosting
- **OpenAI API:** Pay-per-use (very affordable for RFP processing)
- **Total cost:** Typically under $10/month for moderate usage

## 🆘 Support

If you encounter any issues:
1. Check that your OpenAI API key is valid
2. Ensure you have sufficient OpenAI credits
3. Verify file formats are supported (PDF, DOCX, TXT)
