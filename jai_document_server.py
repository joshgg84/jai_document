"""JAI Document Intelligence Server - Microservice for document processing
Handles PDF, DOCX, TXT uploads with heavy libraries (PyPDF2, python-docx)
Runs as a separate server on Render
"""

import os
import base64
import tempfile
import re
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Try to import document processing libraries
try:
    import PyPDF2
    import docx
    DOCUMENT_SUPPORT = True
    logger.info("Document processing libraries loaded")
except ImportError as e:
    DOCUMENT_SUPPORT = False
    logger.warning(f"Document processing libraries not installed: {e}")

# Store documents per client
_user_documents = {}


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'JAI Document Intelligence',
        'version': '1.0.0',
        'libraries': {
            'PyPDF2': 'loaded' if DOCUMENT_SUPPORT else 'not available',
            'python-docx': 'loaded' if DOCUMENT_SUPPORT else 'not available'
        }
    })


@app.route('/api/upload', methods=['POST', 'OPTIONS'])
def upload_document():
    """Upload and process document"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        client_id = data.get('clientId', 'unknown')
        filename = data.get('filename', 'document.txt')
        base64_content = data.get('content', '')
        
        # Decode and extract text
        text = extract_text_from_base64(base64_content, filename)
        
        if not text or len(text.strip()) < 10:
            return jsonify({'error': 'File appears empty or unreadable'}), 400
        
        # Generate summary
        summary = generate_summary(text, filename)
        simplified = simplify_document(text, filename)
        
        # Store document
        _user_documents[client_id] = {
            'filename': filename,
            'content': text,
            'summary': summary,
            'simplified': simplified,
            'created_at': datetime.now().isoformat(),
            'size': len(text)
        }
        
        return jsonify({
            'success': True,
            'filename': filename,
            'size': len(text),
            'summary': summary,
            'simplified': simplified,
            'message': f'Document "{filename}" uploaded successfully'
        })
        
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/ask', methods=['POST', 'OPTIONS'])
def ask_question():
    """Answer questions about uploaded document"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        client_id = data.get('clientId', 'unknown')
        question = data.get('question', '')
        
        doc = _user_documents.get(client_id)
        if not doc:
            return jsonify({'error': 'No document loaded. Please upload first.'}), 400
        
        answer = answer_question(doc['content'], doc['filename'], question)
        
        return jsonify({
            'answer': answer,
            'filename': doc['filename']
        })
        
    except Exception as e:
        logger.error(f"Question error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/summarize', methods=['POST', 'OPTIONS'])
def get_summary():
    """Get document summary"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        client_id = data.get('clientId', 'unknown')
        
        doc = _user_documents.get(client_id)
        if not doc:
            return jsonify({'error': 'No document loaded'}), 400
        
        return jsonify({
            'summary': doc['summary'],
            'filename': doc['filename']
        })
        
    except Exception as e:
        logger.error(f"Summary error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/clear', methods=['POST', 'OPTIONS'])
def clear_document():
    """Clear uploaded document"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        client_id = data.get('clientId', 'unknown')
        
        if client_id in _user_documents:
            del _user_documents[client_id]
        
        return jsonify({'success': True, 'message': 'Document cleared'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def extract_text_from_base64(base64_content, filename):
    """Extract text from base64 encoded file"""
    try:
        file_content = base64.b64decode(base64_content)
        file_ext = filename.split('.')[-1].lower()
        
        if file_ext == 'txt':
            return file_content.decode('utf-8')
        
        elif file_ext == 'pdf' and DOCUMENT_SUPPORT:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                tmp_file.write(file_content)
                tmp_path = tmp_file.name
            
            text = ""
            with open(tmp_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
            os.unlink(tmp_path)
            return text if text.strip() else None
        
        elif file_ext == 'docx' and DOCUMENT_SUPPORT:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp_file:
                tmp_file.write(file_content)
                tmp_path = tmp_file.name
            
            doc = docx.Document(tmp_path)
            text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
            os.unlink(tmp_path)
            return text if text.strip() else None
        
        return None
    except Exception as e:
        logger.error(f"Extract error: {e}")
        return None


def detect_document_type(text, filename):
    """Detect document type"""
    text_lower = text.lower()
    filename_lower = filename.lower()
    
    if 'resume' in filename_lower or 'cv' in filename_lower:
        return "Resume/CV", "📄"
    if any(word in text_lower for word in ['contract', 'agreement', 'terms']):
        return "Legal Document", "⚖️"
    if any(word in text_lower for word in ['const', 'function', 'http', 'server']):
        return "Code File", "💻"
    if any(word in text_lower for word in ['meeting', 'agenda', 'action items']):
        return "Meeting Notes", "📝"
    return "Document", "📄"


def generate_summary(text, filename):
    """Generate document summary"""
    doc_type, icon = detect_document_type(text, filename)
    
    sentences = re.split(r'[.!?\n]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 30]
    
    summary = f"{icon} **DOCUMENT SUMMARY: '{filename}'**\n\n"
    summary += f"📊 **Stats:** {len(text)} characters, {len(text.split())} words\n"
    summary += f"📁 **Type:** {doc_type}\n\n"
    summary += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    summary += "**📖 MAIN CONTENT:**\n\n"
    
    for i, point in enumerate(sentences[:8], 1):
        if len(point) > 300:
            point = point[:300] + "..."
        summary += f"{i}. {point}\n\n"
    
    return summary


def simplify_document(text, filename):
    """Generate simplified version"""
    lines = [l.strip() for l in text.split('\n') if l.strip() and len(l.strip()) > 10][:8]
    
    simplified = f"📄 **Document:** {filename}\n"
    simplified += f"📊 **Size:** {len(text)} characters\n\n"
    
    for i, line in enumerate(lines, 1):
        clean_line = line[:200] + '...' if len(line) > 200 else line
        simplified += f"{i}. {clean_line}\n\n"
    
    return simplified


def answer_question(content, filename, question):
    """Answer questions about document"""
    q_lower = question.lower().strip()
    
    # Summary request
    if any(word in q_lower for word in ['summarize', 'summary', 'overview']):
        return generate_summary(content, filename)
    
    # Key points
    if any(word in q_lower for word in ['key points', 'main points', 'important']):
        sentences = re.split(r'[.!?\n]+', content)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 30][:6]
        
        response = f"📌 **KEY POINTS FROM '{filename}':**\n\n"
        for i, sent in enumerate(sentences, 1):
            response += f"{i}. {sent}\n\n"
        return response
    
    # Simple explanation
    if q_lower in ['explain', 'tell me', 'what is this']:
        sentences = re.split(r'[.!?\n]+', content)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 30][:5]
        
        response = f"📖 **ABOUT '{filename}':**\n\n"
        for i, sent in enumerate(sentences, 1):
            response += f"{i}. {sent}\n\n"
        return response
    
    # Search for specific content
    words = re.findall(r'\b[a-z]{4,}\b', q_lower)
    stopwords = {'what', 'does', 'this', 'that', 'tell', 'about', 'from', 'with', 'have', 'were', 'there', 'their', 'they', 'will', 'would', 'could', 'should', 'please', 'help', 'know', 'want', 'need', 'can', 'you', 'the', 'and', 'for', 'are', 'not'}
    keywords = [w for w in words if w not in stopwords]
    
    sentences = re.split(r'[.!?\n]+', content)
    relevant = []
    for sentence in sentences:
        if any(k in sentence.lower() for k in keywords[:3]):
            if len(sentence.strip()) > 20:
                relevant.append(sentence.strip())
    
    if relevant:
        response = f"📖 **From '{filename}':**\n\n"
        for sent in relevant[:3]:
            response += f"• {sent}\n\n"
        return response
    
    return f"📖 I can help you understand '{filename}'. Try asking:\n• 'Summarize this document'\n• 'What are the key points?'\n• 'Explain this document'"


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5003))
    logger.info(f"JAI Document Server starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)