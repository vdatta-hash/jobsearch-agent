import os
import json
import csv
from flask import Flask, render_template, request, jsonify
from job_agent import search_linkedin_jobs

app = Flask(__name__)

# Ensure app directories exist
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
if not os.path.exists(TEMPLATES_DIR):
    os.makedirs(TEMPLATES_DIR)

def load_default_profile():
    profile_path = "Profile.csv"
    if not os.path.exists(profile_path):
        return ""
    try:
        profile_data = []
        with open(profile_path, mode='r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                clean_row = {k: v for k, v in row.items() if v}
                profile_data.append(str(clean_row))
        return "\n".join(profile_data)
    except Exception as e:
        print(f"Error loading default profile: {e}")
        return ""

@app.route('/')
def index():
    # Load existing preferences
    preferences = {
        "domain": "sales engineering, presales, and solutions architect world",
        "seniority_level": "mid-management to senior-management level",
        "role_type": "strictly people management and leadership roles (e.g., Manager, Senior Manager, Director, Head of, VP) in pre-sales or post-sales organizations. Absolutely NO individual contributor roles (such as SWE, Software Engineer, Staff Engineer, Principal Architect, Sales Engineer)",
        "location": "United States",
        "optional_keywords": "security"
    }
    
    if os.path.exists("preferences.json"):
        try:
            with open("preferences.json", "r") as pref_file:
                file_prefs = json.load(pref_file)
                # Merge loaded preferences
                preferences.update(file_prefs)
        except Exception:
            pass
            
    # Load profile text
    profile_text = load_default_profile()
    
    return render_template('index.html', preferences=preferences, profile_text=profile_text)

@app.route('/api/analyze', methods=['POST'])
def analyze():
    try:
        data = request.json or {}
        profile_text = data.get('profile_text', '').strip()
        preferences = data.get('preferences', {})
        
        if not profile_text:
            return jsonify({'success': False, 'error': 'Profile text cannot be empty.'}), 400
            
        # Save the updated preferences and profile text locally to persist state
        try:
            # Save preferences.json
            with open("preferences.json", "w") as pref_file:
                json.dump(preferences, pref_file, indent=2)
                
            # Save a plain text copy of profile text if needed (keep existing Profile.csv untouched)
            with open("LastProfile.txt", "w", encoding="utf-8") as profile_file:
                profile_file.write(profile_text)
        except Exception as e:
            print(f"Warning: Failed to persist preferences locally: {e}")

        # Run the recruiter analysis and job search
        result = search_linkedin_jobs(profile_text, preferences)
        
        return jsonify({
            'success': True,
            'analysis': result.get('analysis'),
            'primary_query': result.get('primary_query'),
            'jobs': result.get('jobs', [])
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
