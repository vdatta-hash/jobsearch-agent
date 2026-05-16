import os
import json
import csv
import io
from flask import Flask, render_template, request, jsonify, make_response
from job_agent import search_linkedin_jobs, generate_tailored_materials

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
    
    response = make_response(render_template('index.html', preferences=preferences, profile_text=profile_text))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route('/api/analyze', methods=['POST'])
def analyze():
    try:
        # Handle CSV file upload
        if 'profile_file' in request.files:
            file = request.files['profile_file']
            if file.filename == '':
                return jsonify({'success': False, 'error': 'No selected CSV file.'}), 400
            
            raw_content = file.stream.read()
            decoded_content = raw_content.decode("UTF-8") if isinstance(raw_content, bytes) else raw_content
            stream = io.StringIO(decoded_content, newline=None)
            reader = csv.DictReader(stream)
            profile_data = []
            for row in reader:
                clean_row = {k: v for k, v in row.items() if v}
                profile_data.append(str(clean_row))
            profile_text = "\n".join(profile_data)

            if not profile_text:
                return jsonify({'success': False, 'error': 'Uploaded CSV was empty or missing columns.'}), 400

            # Save locally as Profile.csv to persist the uploaded file
            try:
                file.stream.seek(0)
                file.save("Profile.csv")
            except Exception as e:
                print(f"Warning: Failed to save Profile.csv: {e}")

            # Parse preferences from multipart form
            preferences = {
                "domain": request.form.get("domain", "").strip(),
                "seniority_level": request.form.get("seniority_level", "").strip(),
                "role_type": request.form.get("role_type", "").strip(),
                "location": request.form.get("location", "").strip(),
                "optional_keywords": request.form.get("optional_keywords", "").strip()
            }
        else:
            # Handle JSON payload (fallback / backward compatibility)
            data = request.json or {}
            profile_text = data.get('profile_text', '').strip()
            preferences = data.get('preferences', {})
            
            if not profile_text:
                return jsonify({'success': False, 'error': 'Profile text cannot be empty.'}), 400

        # Save preferences locally
        try:
            with open("preferences.json", "w") as pref_file:
                json.dump(preferences, pref_file, indent=2)
        except Exception as e:
            print(f"Warning: Failed to save preferences.json: {e}")

        # Run the recruiter analysis and job search
        result = search_linkedin_jobs(profile_text, preferences)
        
        return jsonify({
            'success': True,
            'analysis': result.get('analysis'),
            'target_domains': result.get('target_domains', []),
            'seniority_level': result.get('seniority_level', ''),
            'target_locations': result.get('target_locations', []),
            'primary_query': result.get('primary_query'),
            'jobs': result.get('jobs', [])
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tailor', methods=['POST'])
def tailor():
    try:
        data = request.json or {}
        job_title = data.get("job_title", "").strip()
        company_name = data.get("company_name", "").strip()
        job_link = data.get("job_link", "").strip()
        
        if not job_title or not company_name:
            return jsonify({'success': False, 'error': 'job_title and company_name are required.'}), 400
            
        # Load profile text from CSV
        profile_text = load_default_profile()
        if not profile_text:
            return jsonify({'success': False, 'error': 'No professional profile found. Please upload Profile.csv on your dashboard first.'}), 400
            
        res = generate_tailored_materials(profile_text, job_title, company_name, job_link)
        return jsonify({
            'success': True,
            'tailored_resume_bullets': res.tailored_resume_bullets,
            'cover_letter': res.cover_letter
        })
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    error_trace = traceback.format_exc()
    print("CRITICAL RUNTIME ERROR:\n", error_trace)
    return jsonify({
        'success': False,
        'error': str(e),
        'traceback': error_trace
    }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
