import os
from flask import Flask, render_template, request, redirect, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, User, Job, Application
from sqlalchemy import or_

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = 'resumes'
ALLOWED_EXTENSIONS = {'pdf', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db.init_app(app)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def serialize_job(job):
    return {
        'id': job.id,
        'title': job.title,
        'description': job.description,
        'employer_id': job.employer_id,
    }

def serialize_application(application):
    return {
        'id': application.id,
        'worker_id': application.worker_id,
        'job_id': application.job_id,
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        role = request.form['role']
        username = request.form['username']
        password = generate_password_hash(request.form['password'])

        if User.query.filter_by(username=username).first():
            return "The user already exists"

        user = User(username=username, password=password, role=role)
        db.session.add(user)
        db.session.commit()
        return redirect('/login')

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['role'] = user.role
            return redirect('/dashboard')
        else:
            return 'Incorrect data'

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')

    if session['role'] == 'employer':
        jobs = Job.query.filter_by(employer_id=session['user_id']).all()
        return render_template('dashboard_employer.html', jobs=jobs)
    else:
        query = request.args.get('q')
        if query:
            jobs = Job.query.filter(
                or_(
                    Job.title.ilike(f"%{query}%"),
                    Job.description.ilike(f"%{query}%")
                )
            ).all()
        else:
            jobs = Job.query.all()
        return render_template('dashboard_worker.html', jobs=jobs)

@app.route('/post_job', methods=['POST'])
def post_job():
    if 'user_id' not in session or session['role'] != 'employer':
        return redirect('/login')

    title = request.form['title']
    description = request.form['description']

    job = Job(title=title, description=description, employer_id=session['user_id'])
    db.session.add(job)
    db.session.commit()
    return redirect('/dashboard')

@app.route('/apply/<int:job_id>')
def apply(job_id):
    if 'user_id' not in session or session['role'] != 'worker':
        return redirect('/login')

    existing = Application.query.filter_by(worker_id=session['user_id'], job_id=job_id).first()
    if not existing:
        application = Application(worker_id=session['user_id'], job_id=job_id)
        db.session.add(application)
        db.session.commit()
    return redirect('/dashboard')

@app.route('/applications/<int:job_id>')
def view_applications(job_id):
    if 'user_id' not in session or session['role'] != 'employer':
        return redirect('/login')

    job = db.session.get(Job, job_id)
    if not job:
        return "Not Found", 404

    if job.employer_id != session['user_id']:
        return "Access Denied"

    applications = Application.query.filter_by(job_id=job_id).all()
    return render_template('applications.html', applications=applications, job=job)

@app.route('/upload_resume', methods=['GET', 'POST'])
def upload_resume():
    if 'user_id' not in session or session['role'] != 'worker':
        return redirect('/login')

    user = db.session.get(User, session['user_id'])

    if request.method == 'POST':
        file = request.files.get('resume')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{user.id}_{filename}")
            file.save(filepath)
            user.resume = filepath
            db.session.commit()
            return redirect('/dashboard')
        else:
            return "Unsupported file format"

    return render_template('upload_resume.html', user=user)

@app.route('/api/jobs', methods=['GET'])
def api_list_jobs():
    jobs = Job.query.all()
    return jsonify([serialize_job(job) for job in jobs])

@app.route('/api/jobs', methods=['POST'])
def api_create_job():
    if 'user_id' not in session or session['role'] != 'employer':
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()

    if not title or not description:
        return jsonify({'error': 'Title and description are required'}), 400

    job = Job(title=title, description=description, employer_id=session['user_id'])
    db.session.add(job)
    db.session.commit()
    return jsonify(serialize_job(job)), 201

@app.route('/api/applications', methods=['POST'])
def api_create_application():
    if 'user_id' not in session or session['role'] != 'worker':
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    job_id = data.get('job_id')
    if not job_id:
        return jsonify({'error': 'job_id is required'}), 400

    job = db.session.get(Job, job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404

    existing = Application.query.filter_by(worker_id=session['user_id'], job_id=job_id).first()
    if existing:
        return jsonify({'error': 'Application already exists'}), 409

    application = Application(worker_id=session['user_id'], job_id=job_id)
    db.session.add(application)
    db.session.commit()
    return jsonify(serialize_application(application)), 201

@app.route('/api/jobs/<int:job_id>/applications', methods=['GET'])
def api_job_applications(job_id):
    if 'user_id' not in session or session['role'] != 'employer':
        return jsonify({'error': 'Unauthorized'}), 401

    job = db.session.get(Job, job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    if job.employer_id != session['user_id']:
        return jsonify({'error': 'Forbidden'}), 403

    applications = Application.query.filter_by(job_id=job_id).all()
    return jsonify([serialize_application(application) for application in applications])

if __name__ == '__main__':
    # Create tables before running the app
    with app.app_context():
        db.create_all()
    app.run(debug=True)
