from flask import Flask, request, render_template, send_file, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from sympy import false
from werkzeug.security import generate_password_hash, check_password_hash
from textblob import TextBlob
import os
import sqlite3
import zipfile
import pdfplumber
import docx2txt
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import spacy
import json

# TEMPORARY: DB init
conn = sqlite3.connect('feedback.db')
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email TEXT NOT NULL,
    feedback_text TEXT NOT NULL,
    sentiment_score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

conn.commit()
conn.close()

# Skill to Course/Certification mapping (example entries)
course_recommendations = {
    "python": ["Coursera: Python for Everybody", "edX: Introduction to Python Programming"],
    "machine learning": ["Coursera: Machine Learning by Andrew Ng", "Udacity: Intro to Machine Learning"],
    "sql": ["Khan Academy: Intro to SQL", "Coursera: SQL for Data Science"],
    "project management": ["Coursera: Google Project Management", "edX: Fundamentals of Project Planning"],
    "excel": ["LinkedIn Learning: Excel Essential Training", "Udemy: Microsoft Excel Bootcamp"],
    "communication": ["Coursera: Improve Communication Skills", "edX: Business Communications"],
    "cloud computing": ["Coursera: AWS Cloud Practitioner", "Udacity: Cloud DevOps Nanodegree"],
    "data visualization": ["Tableau Training", "Google Data Analytics Certificate"],
}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['DOWNLOAD_FOLDER'] = 'matched_resumes/'
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

@app.before_request
def clear_flashes():
    # Clear flashes at the start of each request
    session.pop('_flashes', None)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['DOWNLOAD_FOLDER'], exist_ok=True)

sbert_model = SentenceTransformer('all-MiniLM-L6-v2')
nlp = spacy.load("en_core_web_sm")

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

class User(UserMixin):
    def __init__(self, id_, email, username, password, is_admin=False):  # Use False instead of false
        self.id = id_
        self.email = email
        self.username = username
        self.password = password
        self.is_admin = is_admin  # Ensure this is included

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, email,username, password, is_admin FROM users WHERE id = ?", (user_id,))
    user_data = cursor.fetchone()
    conn.close()
    if user_data:
        return User(*user_data)
    return None

# ------------------------ Text extraction ------------------------

def extract_text(file_path):
    if file_path.endswith('.pdf'):
        with pdfplumber.open(file_path) as pdf:
            return "\n".join([p.extract_text() for p in pdf.pages if p.extract_text()])
    elif file_path.endswith('.docx'):
        return docx2txt.process(file_path)
    elif file_path.endswith('.txt'):
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    return ""

def preprocess(text):
    doc = nlp(text)
    return " ".join([token.lemma_.lower() for token in doc if not token.is_stop and not token.is_punct])

def extract_skills(text):
    doc = nlp(text)
    return [ent.text.lower() for ent in doc.ents if ent.label_ in ['ORG', 'PRODUCT', 'WORK_OF_ART', 'SKILL', 'LANGUAGE']]

def extract_main_keywords(text):
    doc = nlp(text)
    keywords = set()
    for token in doc:
        if token.pos_ in ["NOUN", "PROPN", "VERB"] and not token.is_stop:
            keywords.add(token.lemma_.lower())
    for ent in doc.ents:
        if ent.label_ in ['ORG', 'PRODUCT', 'WORK_OF_ART', 'SKILL', 'LANGUAGE', 'PERSON']:
            keywords.add(ent.text.lower())
    return keywords

# ------------------------ Routes ------------------------

@app.route('/')
def home():
        return redirect(url_for('intro'))

@app.route('/intro')
def intro():
    # Render the intro video page
    return render_template('intro.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('matcher'))

    if request.method == 'POST':
        login = request.form['login']
        password = request.form['password']

        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, username, password, is_admin FROM users WHERE email = ? OR username = ?",
                       (login, login))
        user_data = cursor.fetchone()

        if user_data and check_password_hash(user_data[3], password):
            user = User(*user_data)
            login_user(user)
            return redirect(url_for('matcher'))
        else:
            flash('Invalid email/username or password - Please try again', 'login-error')

        conn.close()

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Validation checks
        if not all([email, username, password, confirm_password]):
            flash('All fields are required', 'register-danger')
            return redirect(url_for('register'))

        if password != confirm_password:
            flash('Passwords do not match', 'register-warning')
            return redirect(url_for('register'))

        hashed_pw = generate_password_hash(password)

        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()

            # Check if email or username already exists
            cursor.execute("SELECT * FROM users WHERE email = ? OR username = ?", (email, username))
            if cursor.fetchone():
                flash('Email or username already exists', 'register-danger')
                return redirect(url_for('register'))

            cursor.execute("INSERT INTO users (email, username, password) VALUES (?, ?, ?)",
                           (email, username, hashed_pw))
            conn.commit()
            flash('Account created successfully!', 'register-success')
            return redirect(url_for('login'))

        except Exception as e:
            flash(f'Registration error: {str(e)}', 'register-danger')
            return redirect(url_for('register'))
        finally:
            conn.close()

    return render_template('register.html')


# Add these new routes to your Flask app

@app.route('/forgot_password', methods=['GET'])
def forgot_password():
    return render_template('forgot_password.html')


@app.route('/handle_forgot_password', methods=['POST'])
def handle_forgot_password():
    session.pop('_flashes', None)
    email = request.form.get('email').strip()

    # Dummy check - in a real app, you would verify the email exists in your database
    if not email or '@' not in email:
        flash('Please enter a valid email address', 'reset-error')
        return redirect(url_for('forgot_password'))

    # In a real app, you would:
    # 1. Generate a token
    # 2. Send an email with reset link
    # 3. Store the token in database

    # For our dummy version:
    flash('Password reset link sent! Please check your inbox (and spam folder).', 'reset-success')
    return redirect(url_for('login'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/matcher', methods=['GET', 'POST'])
@login_required
def matcher():
    try:
        if request.method == "POST":
            job_desc = request.form['job_description']
            resumes = request.files.getlist('resumes')

            # Get number of resumes to display (default to 10 if not specified)
            try:
                num_resumes = int(request.form.get('num_resumes', 10))
            except ValueError:
                num_resumes = 10  # Fallback to default if invalid input

            # Input validation
            if num_resumes < 1 or num_resumes > 50:
                flash('Please select between 1 and 50 resumes to display', 'matcher-warning')
                return redirect(url_for('matcher'))

            if not job_desc or not resumes:
                flash('Missing job description or resumes.', 'matcher-warning')
                return redirect(url_for('matcher'))

            if len(resumes) > 50:  # or remove this check entirely if you want unlimited
                flash('You can only upload up to 10 resumes at a time.', 'matcher-warning')
                return redirect(url_for('matcher'))

            jd_clean = preprocess(job_desc)
            jd_keywords = extract_main_keywords(job_desc)
            jd_embedding = sbert_model.encode([jd_clean])[0]
            required_skills = set(extract_skills(job_desc))

            extracted_texts, original_texts, filenames, skill_scores = [], [], [], []

            for resume in resumes:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], resume.filename)
                resume.save(file_path)
                filenames.append(resume.filename)

                original = extract_text(file_path)
                cleaned = preprocess(original)
                extracted_texts.append(cleaned)
                original_texts.append(original)

                resume_skills = set(extract_skills(original))
                skill_scores.append(len(resume_skills & required_skills))

            resume_embeddings = sbert_model.encode(extracted_texts)
            similarities = cosine_similarity([jd_embedding], resume_embeddings)[0]

            combined = [(i, similarities[i] + 0.05 * skill_scores[i]) for i in range(len(resumes))]
            top_indices = [i for i, _ in sorted(combined, key=lambda x: x[1], reverse=True)[:num_resumes]]
            response = f"<h4 class='mt-4 mb-3'>Top {min(num_resumes, len(resumes))} Matching Resumes (out of {len(resumes)})</h4>"

            chart_labels, chart_scores = [], []
            response = "<h4 class='mt-4 mb-3'>Top Matching Resumes</h4>"

            for i in top_indices:
                score = similarities[i] * 100
                level = "High" if score > 85 else "Moderate" if score > 65 else "Low"
                chart_labels.append(filenames[i])
                chart_scores.append(float(f"{score:.2f}"))

                resume_doc = nlp(original_texts[i])
                matched_skills = list(set(skill for skill in extract_skills(original_texts[i]) if skill in required_skills))
                missing_skills = list(required_skills - set(matched_skills))
                recommended_courses = []

                for skill in missing_skills:
                    if skill in course_recommendations:
                        recommended_courses.extend(course_recommendations[skill])

                recommended_courses = list(set(recommended_courses))  # remove duplicates

                matched_experience = list(set(token.lemma_.lower() for token in resume_doc if token.lemma_.lower() in jd_keywords and token.pos_ in ["VERB", "NOUN"]))
                matched_tools = list(set(ent.text for ent in resume_doc.ents if ent.label_ == 'PRODUCT' and ent.text.lower() in jd_keywords))
                matched_titles = list(set(ent.text for ent in resume_doc.ents if ent.label_ in ['ORG', 'WORK_OF_ART', 'PERSON'] and ent.text.lower() in jd_keywords))

                stop_words = {"job", "experience", "required", "preferred", "degree", "field", "candidate", "support", "ability"}
                matched_experience = [word for word in matched_experience if word not in stop_words]
                matched_skills = [word for word in matched_skills if word not in stop_words]
                matched_tools = [word for word in matched_tools if word not in stop_words]
                matched_titles = [word for word in matched_titles if word not in stop_words]

                response += f"""
                <div class='resume-item mb-4 border p-3 rounded shadow-sm'>
                    <h5>{filenames[i]} — Score: {score:.2f}%, 
                        <span class='badge badge-info'>{level}</span>
                    </h5>
                    <details>
                        <summary>View Match Breakdown</summary>
                        <ul>
                            <li><strong>🔧 Tools/Technologies:</strong> <span style='color: teal;'>{', '.join(matched_tools) or 'None'}</span></li>
                            <li><strong>🧠 Skills Matched:</strong> <span style='color: darkgreen;'>{', '.join(matched_skills) or 'None'}</span></li>
                            <li><strong>💼 Experience Keywords:</strong> <span style='color: darkblue;'>{', '.join(matched_experience) or 'None'}</span></li>
                            <li><strong>🏷️ Titles/Certifications:</strong> <span style='color: purple;'>{', '.join(matched_titles) or 'None'}</span></li>
                            <li><strong>📚 Recommended Courses:</strong> <span style='color: brown;'>{'<br>'.join(recommended_courses) or 'None'}</span></li>
                        </ul>
                    </details>
                </div>
                """

            response += """
            <div class="chart-container mt-4">
                <h5 class='mb-3'>Match Scores Visualization</h5>
                <div style="height: 400px;">
                    <canvas id="matchChart"></canvas>
                </div>
            </div>
            """

            # ⬇️ Add the button here!
            response += """
                       <div class="text-center mt-4">
                           <a href='/download_matched_resumes' class="btn btn-success">
                               ⬇️ Download Matched Resumes (ZIP)
                           </a>
                       </div>
                       """

            response += """
            <div class="text-center mt-5">
                <h5>We'd love your feedback 💬</h5>
                <form action="/feedback" method="POST" style="max-width: 600px; margin: auto;">
                    <div class="form-group mb-3">
                        <label for="feedback">What did you think of the Resume Matcher?</label>
                        <textarea class="form-control" id="feedback" name="feedback" rows="4" required placeholder="Share your thoughts, suggestions, or issues..."></textarea>
                    </div>
                    <button type="submit" class="btn btn-primary">Submit Feedback</button>
                </form>
            </div>
            """

            response += f"""
            <script>
                const ctx = document.getElementById('matchChart');
                new Chart(ctx, {{
                    type: 'bar',
                    data: {{
                        labels: {json.dumps(chart_labels)},
                        datasets: [{{
                            label: 'Match Score (%)',
                            data: {json.dumps(chart_scores)},
                            backgroundColor: 'rgba(54, 162, 235, 0.7)',
                            borderColor: 'rgba(54, 162, 235, 1)',
                            borderWidth: 1
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {{
                            y: {{
                                beginAtZero: true,
                                max: 100,
                                title: {{
                                    display: true,
                                    text: 'Match Score (%)'
                                }}
                            }}
                        }},
                    }}
                }});
            </script>
            """
            return response

        return render_template("resume.html")

    except Exception as e:
        flash(f"Error: {str(e)}", 'danger')
        return redirect(url_for('matcher'))

@app.route("/download_matched_resumes")
@login_required
def download():
    try:
        zip_filename = 'matched_resumes.zip'
        zip_file_path = os.path.join(app.config['DOWNLOAD_FOLDER'], zip_filename)

        with zipfile.ZipFile(zip_file_path, 'w') as zipf:
            for filename in os.listdir(app.config['UPLOAD_FOLDER']):
                zipf.write(os.path.join(app.config['UPLOAD_FOLDER'], filename), filename)

        return send_file(zip_file_path, as_attachment=True)

    except Exception as e:
        flash(f"Error: {str(e)}", 'danger')
        return redirect(url_for('matcher'))

@app.route('/thankyou')
def thankyou():
    return render_template('thankyou.html')


@app.route('/reviews')
@login_required
def reviews():
    if current_user.is_admin:
        return redirect(url_for('view_feedback'))

    conn = sqlite3.connect('feedback.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT user_email, feedback_text, sentiment_score, created_at FROM feedback ORDER BY created_at DESC')
    feedbacks = cursor.fetchall()
    conn.close()

    return render_template('reviews.html', feedbacks=feedbacks)

@app.route('/feedback', methods=['POST'])
@login_required
def feedback():
    feedback_text = request.form['feedback']
    sentiment = TextBlob(feedback_text).sentiment.polarity
    user_email = current_user.email

    # Save feedback to SQLite database
    conn = sqlite3.connect('feedback.db')
    cursor = conn.cursor()
    cursor.execute(''' 
        INSERT INTO feedback (user_email, feedback_text, sentiment_score)
        VALUES (?, ?, ?)
    ''', (user_email, feedback_text, sentiment))
    conn.commit()
    conn.close()

    # Save feedback to .txt log file
    with open("feedback_log.txt", "a", encoding="utf-8") as f:
        f.write(f"{user_email}: {feedback_text} (Sentiment: {sentiment})\n")

    name = user_email.split('@')[0].capitalize()

    if sentiment < 0:
        return render_template('feedback_negative.html', name=name)
    else:
        flash("Thank you for your feedback!", "feedback-success")
        return render_template('thankyou.html', name=name)

@app.route('/admin/feedback')
@login_required
def view_feedback():
    print("✅ Admin Route Hit")
    if not current_user.is_admin:
        return redirect(url_for('matcher'))

    conn = sqlite3.connect('feedback.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM feedback')
    feedbacks = cursor.fetchall()
    conn.close()

    print("📝 Feedbacks fetched:")
    for f in feedbacks:
        print(f)

    return render_template('view_feedback.html', feedbacks=feedbacks)

@app.route('/admin/delete_feedback/<int:feedback_id>', methods=['POST'])
@login_required
def delete_feedback(feedback_id):
    if not current_user.is_admin:
        return redirect(url_for('matcher'))

    conn = sqlite3.connect('feedback.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM feedback WHERE id = ?', (feedback_id,))
    conn.commit()
    conn.close()

    flash('Feedback deleted successfully', 'feedback-success')
    return redirect(url_for('view_feedback'))

if __name__ == "__main__":
    app.run(debug=True)