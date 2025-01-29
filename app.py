from flask import Flask, request, jsonify
from flask_cors import CORS
from io import BytesIO
import PyPDF2
import spacy
import pdfplumber
from spacy.matcher import PhraseMatcher

app = Flask(__name__)
CORS(app, origins=["https://kns-ats-resume-checker.vercel.app/"])

# Load spaCy model
nlp = spacy.load("en_core_web_sm")


# Function: Check formatting issues
def check_formatting(file):
    issues = []
    try:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                # Check for tables
                if page.extract_tables():
                    issues.append("Resume contains tables, which may not be ATS-friendly.")
                # Check for images
                if page.images:
                    issues.append("Resume contains images, which may not be ATS-friendly.")
    except Exception as e:
        issues.append(f"Error during formatting check: {str(e)}")
    return issues


# Function: Calculate overall score
def calculate_score(matched_keywords, jd_keywords, missing_sections, formatting_issues, category_scores):
    # Base score: Match of keywords between resume and job description
    base_score = (len(matched_keywords) / len(jd_keywords)) * 100 if jd_keywords else 0

    # Deduct for missing sections and formatting issues
    deductions = (len(missing_sections) * 5) + (len(formatting_issues) * 10)

    # Average category score (weighted more heavily)
    # Calculate the weighted average for category scores
    category_score_avg = sum(category_scores.values()) / len(category_scores) if category_scores else 0

    # We give a higher weight to category score, since it's essential for the matching process
    weighted_score = 0.7 * base_score + 0.3 * category_score_avg

    # Apply deductions and ensure final score is capped between 0 and 100
    final_score = weighted_score - deductions
    final_score = max(0, final_score)  # Ensure score does not go below 0
    return min(final_score, 100)  # Cap the score at 100




# Function: Generate feedback
def generate_feedback(matched_keywords, missing_keywords, formatting_issues, category_scores, jd_keywords):
    return {
        "overall_score": calculate_score(
            matched_keywords, 
            jd_keywords, 
            missing_sections=[], 
            formatting_issues=formatting_issues, 
            category_scores=category_scores
        ),
        "category_scores": category_scores,
        "matched_keywords": list(matched_keywords),
        "missing_keywords": list(missing_keywords),
        "issues": formatting_issues
    }


# Endpoint: Analyze resume
@app.route('/analyze', methods=['POST'])
def analyze_resume():
    try:
        # Get file and job description from request
        file = request.files.get('resume')
        job_description = request.form.get('job_description')

        if not file or not job_description:
            return jsonify({"error": "Resume file and job description are required"}), 400

        # Read file and perform formatting checks
        file_bytes = BytesIO(file.read())
        formatting_issues = check_formatting(file_bytes)

        # Parse resume and job description
        file_bytes.seek(0)  # Reset the file pointer
        reader = PyPDF2.PdfReader(file_bytes)
        resume_text = " ".join([page.extract_text() or "" for page in reader.pages])
        resume_doc = nlp(resume_text)
        jd_doc = nlp(job_description)

        # Extract keywords
        resume_keywords = {token.lemma_.lower() for token in resume_doc if token.is_alpha}
        jd_keywords = {token.lemma_.lower() for token in jd_doc if token.is_alpha}
        matched_keywords = resume_keywords & jd_keywords
        missing_keywords = jd_keywords - resume_keywords

        # Categorize keywords
        categories = {
            "skills": ["python", "flask", "teamwork", "django"],
            "experience": ["developer", "internship", "freelance", "project management"],
            "education": ["bachelor", "master", "mba"]
        }
        category_scores = {cat: 0 for cat in categories}
        for cat, keywords in categories.items():
            matches = [kw for kw in keywords if kw in resume_keywords]
            category_scores[cat] = len(matches) / len(keywords) * 100 if keywords else 0

        # Generate feedback
        feedback = generate_feedback(
            matched_keywords, missing_keywords, formatting_issues, category_scores, jd_keywords
        )
        return jsonify(feedback)

    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


# Run the app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

