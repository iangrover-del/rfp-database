# 📋 RFP Database Web App

A simple, AI-powered web application for managing RFP (Request for Proposal) documents. Upload historical RFPs to build a knowledge base, then get AI-suggested answers for new RFPs.

## ✨ Features

- **📤 Upload Historical RFPs**: Build your knowledge base with past submissions
- **🤖 AI-Powered Analysis**: Extract structured information from RFP documents
- **🔄 Smart Matching**: Get suggested answers for new RFPs based on historical data
- **🔍 Search & Browse**: Find and explore your RFP database
- **📱 Web Interface**: Easy-to-use responsive design
- **💾 Local Database**: SQLite database - no external setup needed

## 🚀 Quick Start

### Option 1: Streamlit Cloud (Recommended)

1. **Fork this repository** or create a new one with the files
2. **Go to [Streamlit Cloud](https://share.streamlit.io)**
3. **Connect your GitHub repository**
4. **Set your OpenAI API key** in the secrets section
5. **Deploy!** Your app will be live in minutes

### Option 2: Local Development

```bash
# Install dependencies
pip install streamlit openai python-docx PyPDF2 pandas

# Set your OpenAI API key
export OPENAI_API_KEY="sk-your-key-here"

# Run the app
streamlit run rfp_webapp.py
```

## 📋 How to Use

1. **Upload Historical RFPs**: Go to "Upload Historical RFP" and upload your past RFP documents (PDF, DOCX, TXT)
2. **Process New RFPs**: Go to "Process New RFP" and upload a new RFP to get AI-suggested answers
3. **Browse Database**: View all your uploaded RFPs in "Browse Database"
4. **Search**: Use the search function to find specific RFPs

## 🔧 Configuration

### Required:
- **OpenAI API Key**: Get from [OpenAI Platform](https://platform.openai.com/api-keys)

### Supported File Formats:
- PDF documents
- Microsoft Word documents (.docx)
- Text files (.txt)

## 💡 How It Works

1. **Document Processing**: Uploaded RFPs are processed to extract text content
2. **AI Analysis**: OpenAI GPT-4 analyzes the content and extracts structured information
3. **Knowledge Base**: Historical RFPs are stored in a searchable database
4. **Smart Matching**: New RFPs are compared against historical data to suggest answers
5. **Confidence Scoring**: Each suggestion includes a confidence score (0-100%)

## 🎯 Use Cases

- **Sales Teams**: Quickly respond to RFPs with consistent, high-quality answers
- **Proposal Writers**: Leverage past successful proposals for new opportunities
- **Business Development**: Maintain a centralized knowledge base of client requirements
- **Consulting Firms**: Standardize responses while maintaining customization

## 🔒 Privacy & Security

- All data is stored locally in your SQLite database
- No data is shared with third parties (except OpenAI for processing)
- API keys are stored securely in Streamlit secrets
- You maintain full control over your data

## 💰 Cost

- **Hosting**: Free on Streamlit Cloud
- **OpenAI API**: Pay-per-use (typically $5-20/month for moderate usage)
- **Total**: Very affordable for most organizations

## 🆘 Troubleshooting

**"OpenAI API key not found"**
- Make sure you've set the OPENAI_API_KEY environment variable or secret

**"Error extracting text"**
- Ensure your file is in a supported format (PDF, DOCX, TXT)
- Check that the file isn't corrupted

**"No matching answers found"**
- Upload more historical RFPs to improve matching accuracy
- Try different search terms

## 📞 Support

For issues or questions:
1. Check the troubleshooting section above
2. Verify your OpenAI API key and credits
3. Ensure file formats are supported

## 🔄 Updates

This is a standalone application that you can customize and extend as needed. The code is well-documented and modular for easy modifications.
