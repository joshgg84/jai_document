from flask import Flask, request, jsonify
import hashlib
from collections import Counter

app = Flask(__name__)

class DocumentProcessor:
    def __init__(self):
        self.documents = {}
        self.inverted_index = {}
    
    def process_document(self, filename: str, content: str) -> dict:
        """Index document with simple TF without ML"""
        doc_id = hashlib.md5(filename.encode()).hexdigest()
        
        # Simple tokenization
        words = content.lower().split()
        word_count = Counter(words)
        
        # Build inverted index
        for word, count in word_count.items():
            if word not in self.inverted_index:
                self.inverted_index[word] = {}
            self.inverted_index[word][doc_id] = count
        
        self.documents[doc_id] = {
            'name': filename,
            'content': content,
            'word_count': len(words),
            'unique_words': len(word_count)
        }
        
        return {'doc_id': doc_id, 'indexed_words': len(word_count)}
    
    def search(self, query: str) -> list:
        """Simple keyword search"""
        query_words = query.lower().split()
        results = []
        
        for word in query_words:
            if word in self.inverted_index:
                for doc_id, count in self.inverted_index[word].items():
                    results.append({
                        'document': self.documents[doc_id]['name'],
                        'relevance': count,
                        'snippet': self._get_snippet(doc_id, word)
                    })
        
        # Sort by relevance
        results.sort(key=lambda x: x['relevance'], reverse=True)
        return results[:5]
    
    def _get_snippet(self, doc_id: str, keyword: str, context_chars: int = 100):
        content = self.documents[doc_id]['content']
        idx = content.lower().find(keyword)
        if idx == -1:
            return ""
        start = max(0, idx - context_chars)
        end = min(len(content), idx + len(keyword) + context_chars)
        return f"...{content[start:end]}..."

processor = DocumentProcessor()

@app.route('/upload', methods=['POST'])
def upload():
    data = request.json
    result = processor.process_document(
        filename=data['filename'],
        content=data['content']
    )
    return jsonify(result)

@app.route('/search', methods=['POST'])
def search():
    data = request.json
    results = processor.search(data['query'])
    return jsonify({'results': results, 'count': len(results)})

@app.route('/documents', methods=['GET'])
def list_docs():
    return jsonify({'documents': list(processor.documents.values())})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8002)