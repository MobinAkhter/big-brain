import sys
import os
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import shutil
import json
from sentence_transformers import SentenceTransformer, util

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('backend.log')
    ]
)
logger = logging.getLogger(__name__)
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.setLevel(logging.DEBUG)

logger.info("Starting integration.py with updated CORS and debug=True")

# Determine the base path for PyInstaller or development
if getattr(sys, 'frozen', False):
    # Running as a PyInstaller bundle
    base_path = sys._MEIPASS
else:
    # Running as a script (development)
    base_path = os.path.abspath(os.path.dirname(__file__))

# Add the brain directory to the Python path
brain_path = os.path.join(base_path, '..', 'second-brain', 'brain')
sys.path.append(brain_path)
logger.info(f"Set brain_path to: {brain_path}")
logger.debug(f"sys.path: {sys.path}")

# Import storage and llm modules
try:
    from storage import (
        add, get_note, update_note, delete, filter_notes, topk,
        get_recent_notes, get_favorite_notes, toggle_favorite, export_notes, DB
    )
    from llm import chat
    logger.info("Successfully imported storage and llm modules")
except ImportError as e:
    logger.error(f"Failed to import modules: {e}")
    raise

app = Flask(__name__)
CORS(app, origins="*")  # Temporarily allow all origins for debugging

# Load the NLP model for AI-Powered Search
model = SentenceTransformer('all-MiniLM-L6-v2')
logger.info("NLP model loaded: all-MiniLM-L6-v2")

# Helper to format notes for JSON response
def format_note(note):
    logger.debug(f"Formatting note: {note}")
    nid, parent_id, ts, body, tags, is_favorite = note
    return {
        "id": nid,
        "parent_id": parent_id,
        "timestamp": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M"),
        "body": body,
        "tags": tags.split(',') if tags else [],
        "is_favorite": bool(is_favorite)
    }

@app.route('/add_note', methods=['POST'])
def add_note():
    logger.info("Received /add_note request")
    data = request.json
    logger.debug(f"Request data: {data}")
    
    body = data.get('body', '')
    tags = data.get('tags', '')
    
    if not body:
        logger.warning("Body is required but not provided")
        return jsonify({"error": "Body is required"}), 400
    
    try:
        add(body, tags)
        logger.info("Note added successfully")
        return jsonify({"message": "Note added successfully"}), 200
    except Exception as e:
        logger.error(f"Error adding note: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/get_note/<int:nid>', methods=['GET'])
def get_note_route(nid):
    logger.info(f"Received /get_note/{nid} request")
    try:
        note = get_note(nid)
        if not note:
            logger.warning(f"Note {nid} not found")
            return jsonify({"error": "Note not found"}), 404
        logger.debug(f"Retrieved note: {note}")
        return jsonify(format_note(note)), 200
    except Exception as e:
        logger.error(f"Error retrieving note {nid}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/update_note/<int:nid>', methods=['POST'])
def update_note_route(nid):
    logger.info(f"Received /update_note/{nid} request")
    data = request.json
    logger.debug(f"Request data: {data}")
    
    body = data.get('body', '')
    tags = data.get('tags', '')
    
    if not body:
        logger.warning("Body is required but not provided")
        return jsonify({"error": "Body is required"}), 400
    
    try:
        update_note(nid, body, tags)
        logger.info(f"Note {nid} updated successfully")
        return jsonify({"message": "Note updated successfully"}), 200
    except Exception as e:
        logger.error(f"Error updating note {nid}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/delete_note/<int:nid>', methods=['DELETE'])
def delete_note(nid):
    logger.info(f"Received /delete_note/{nid} request")
    try:
        delete(nid)
        logger.info(f"Note {nid} deleted successfully")
        return jsonify({"message": "Note deleted successfully"}), 200
    except Exception as e:
        logger.error(f"Error deleting note {nid}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/filter_notes', methods=['POST'])
def filter_notes_route():
    logger.info("Received /filter_notes request")
    data = request.json
    logger.debug(f"Request data: {data}")
    
    text = data.get('text', None)
    tags = ','.join(data.get('tags', []))
    date_start = data.get('date_start', None)
    if date_start:
        date_start = datetime.strptime(date_start, "%Y-%m-%d").timestamp()
    date_end = data.get('date_end', None)
    if date_end:
        date_end = datetime.strptime(date_end, "%Y-%m-%d").timestamp() + 86399
    
    try:
        notes = filter_notes(text, tags, date_start, date_end)
        logger.info(f"Retrieved {len(notes)} notes")
        return jsonify([format_note(note) for note in notes]), 200
    except Exception as e:
        logger.error(f"Error filtering notes: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/recent_notes', methods=['GET'])
def recent_notes_route():
    logger.info("Received /recent_notes request")
    try:
        notes = get_recent_notes(limit=10)
        logger.info(f"Retrieved {len(notes)} recent notes")
        return jsonify([format_note(note) for note in notes]), 200
    except Exception as e:
        logger.error(f"Error retrieving recent notes: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/favorite_notes', methods=['GET'])
def favorite_notes_route():
    logger.info("Received /favorite_notes request")
    try:
        notes = get_favorite_notes()
        logger.info(f"Retrieved {len(notes)} favorite notes")
        return jsonify([format_note(note) for note in notes]), 200
    except Exception as e:
        logger.error(f"Error retrieving favorite notes: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/toggle_favorite/<int:nid>', methods=['POST'])
def toggle_favorite_route(nid):
    logger.info(f"Received /toggle_favorite/{nid} request")
    try:
        is_favorite = toggle_favorite(nid)
        logger.info(f"Note {nid} favorite status toggled to {is_favorite}")
        return jsonify({"message": f"Note {nid} {'added to' if is_favorite else 'removed from'} favorites", "is_favorite": is_favorite}), 200
    except Exception as e:
        logger.error(f"Error toggling favorite for note {nid}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/ask', methods=['POST'])
def ask_route():
    logger.info("Received /ask request")
    try:
        data = request.get_json()
        if data is None:
            raise ValueError("No JSON data in request or invalid Content-Type")
        logger.debug(f"Request data: {data}")
        
        query = data.get('query', '')
        tags = ','.join(data.get('tags', []))
        date_start = data.get('date_start', None)
        if date_start:
            date_start = datetime.strptime(date_start, "%Y-%m-%d").timestamp()
        date_end = data.get('date_end', None)
        if date_end:
            date_end = datetime.strptime(date_end, "%Y-%m-%d").timestamp() + 86399
        
        if not query:
            logger.warning("Query is required but not provided")
            return jsonify({"error": "Query is required"}), 400
        
        # Generate query embedding
        query_embedding = model.encode(query, convert_to_tensor=True)
        
        # Retrieve notes with filters (text=None to get all notes within filters)
        notes = filter_notes(text=None, tags=tags, date_start=date_start, date_end=date_end)
        
        if not notes:
            return jsonify({"answer": "No notes available", "context": []}), 200
        
        # Generate embeddings for note bodies
        note_embeddings = model.encode([note[3] for note in notes], convert_to_tensor=True)
        
        # Compute cosine similarities
        similarities = util.pytorch_cos_sim(query_embedding, note_embeddings)[0]
        
        # Get top-k indices
        k = 6
        top_k_indices = similarities.topk(k).indices
        
        # Get top-k notes
        ctx = [(notes[i][0], notes[i][3]) for i in top_k_indices]
        
        ctx_block = "\n".join(f"[[{nid}]] {b}" for nid, b in ctx)
        prompt = (
            "Here are my notes:\n" + ctx_block + "\n\n"
            "Using ONLY these notes, answer the question below. "
            "If the answer isn’t in the notes, say 'I don’t know.' "
            "Cite notes with [[nid]].\n\n"
            f"Question: {query}\nAnswer:"
        )
        logger.debug(f"Generated prompt: {prompt}")
        
        answer = chat(prompt)
        logger.info("Generated answer from LLM")
        
        response = {
            "answer": answer,
            "context": [{"id": nid, "body": body} for nid, body in ctx]
        }
        logger.debug(f"Response: {response}")
        return jsonify(response), 200
    except ValueError as e:
        logger.error(f"Invalid request: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Error processing ask request: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/export_notes', methods=['POST'])
def export_notes_route():
    logger.info("Received /export_notes request")
    data = request.json
    logger.debug(f"Request data: {data}")
    
    file_path = data.get('file_path', '')
    file_type = data.get('file_type', '')
    
    if not file_path or not file_type:
        logger.warning("File path and type are required but not provided")
        return jsonify({"error": "File path and type are required"}), 400
    
    try:
        if file_type == "db":
            shutil.copy(str(DB), file_path)
            logger.info(f"Database backed up to {file_path}")
            return jsonify({"message": "Database backed up successfully"}), 200
        elif file_type == "json":
            notes = export_notes()
            with open(file_path, 'w') as f:
                json.dump(notes, f, indent=2)
            logger.info(f"Notes exported to JSON at {file_path}")
            return jsonify({"message": "Notes exported to JSON successfully"}), 200
        else:
            logger.warning(f"Unsupported file type: {file_type}")
            return jsonify({"error": "Unsupported file type"}), 400
    except Exception as e:
        logger.error(f"Error exporting notes: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    logger.info("Starting Flask server")
    app.run(host='127.0.0.1', port=5001, debug=True)
    logger.info("Flask server stopped")