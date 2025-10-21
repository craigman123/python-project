from flask import Flask, render_template, request, redirect, session, url_for, send_from_directory, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import time, os, uuid
from datetime import datetime
from national import nationalities
from zipfile import ZipFile
from sqlalchemy import text

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['LAST_UPDATE'] = int(time.time())
app.secret_key = "aries_vincent_secret"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///iims_1.0.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

class Inmate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    nationality = db.Column(db.String(50), nullable=False)
    security_level = db.Column(db.String(50), nullable=False)
    date_apprehended = db.Column(db.Date, nullable=True)
    date_added = db.Column(db.Date, default=datetime.utcnow)
    evidence_file = db.Column(db.String(150), nullable=True)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    badge = db.Column(db.Integer, unique=True, nullable=False )
    posts = db.relationship('Post', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

def inject_now():
    """Adds a changing timestamp to all templates."""
    return {'now': int(time.time())}

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'username' not in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        
        name = f"{request.form.get('last', '').capitalize()} {request.form.get('first', '').capitalize()} {request.form.get('initial', '').capitalize()}".strip()
        age = int(request.form['age'])
        gender = request.form['gender']
        nationality = request.form['nationality']
        security_level_num = int(request.form['security_level'])

        SECURITY_LEVELS = {
            1: "Low Security Inmate",
            2: "Medium Security Inmate",
            3: "High Security Inmate",
            4: "Maximum Security Inmate",
            5: "Death Row Inmate"
        }
        security_level_str = SECURITY_LEVELS.get(security_level_num, "Unknown")

        date_apprehended_str = request.form.get('Apprehended')
        date_apprehended = datetime.strptime(date_apprehended_str, "%Y-%m-%d").date() if date_apprehended_str else None

        current_date_str = request.form.get('current_date')
        current_date = datetime.strptime(current_date_str, "%Y-%m-%d").date() if current_date_str else datetime.utcnow().date()

        file = request.files.get('evidence_file')
        filename = None
        if file and file.filename != '':
            ext = os.path.splitext(file.filename)[1]
            filename = f"{uuid.uuid4().hex}{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        inmate = Inmate(
            name=name,
            age=age,
            gender=gender,
            nationality=nationality,
            security_level=security_level_str,
            date_apprehended=date_apprehended,
            date_added=current_date,
            evidence_file=filename
        )
        
        db.session.add(inmate)
        db.session.commit()
        flash('Inmate added successfully!', 'success')
        return redirect(url_for('dashboard'))
    
    inmates = Inmate.query.order_by(Inmate.date_added.desc()).all()
    return render_template('dashboard.html', posts=inmates, nationalities=nationalities)

@app.route('/search', methods=['GET'])
def search_inmates():
    if 'username' not in session:
        return redirect(url_for('index'))

    query = request.args.get('q', '').strip().lower()
    all_inmates = Inmate.query.order_by(Inmate.date_added.desc()).all()

    if query:
        matches = []
        non_matches = []
        for inmate in all_inmates:
            if (query.isdigit() and int(query) == inmate.id) or (query in inmate.name.lower()):
                matches.append(inmate)
            else:
                non_matches.append(inmate)
        inmates = matches + non_matches
    else:
        inmates = all_inmates

    return render_template('dashboard.html', posts=inmates, nationalities=nationalities)

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    badge = int(request.form['badge'])
    user = User.query.filter_by(username=username, badge=badge).first()

    if user and user.check_password(password):
        session['username'] = username
        session['badge'] = badge
        return redirect(url_for('dashboard'))
    else:
        error = "Invalid username or password - Register First:"
        return render_template('index.html', error=error)

@app.route('/register', methods=['POST'])
def register():
    username = request.form['new_username']
    password = request.form['new_password']
    badge = int(request.form['new_badge'])
    
    existing_user = User.query.filter_by(username=username).first()
    existing_badge = User.query.filter_by(badge=badge).first()
    
    if existing_user:
        return render_template('index.html', error="Username already exists.")
    elif existing_badge:
        return render_template('index.html', error="Badge number already exists.")
    
    new_user = User(username=username, badge=badge)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    
    session['username'] = username
    session['badge'] = badge
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

@app.route('/inmate/delete/<int:inmate_id>', methods=['POST'])
def delete_inmate(inmate_id):
    if 'username' not in session:
        return redirect(url_for('index'))

    inmate = Inmate.query.get_or_404(inmate_id)

    if inmate.evidence_file:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], inmate.evidence_file)
        if os.path.exists(file_path):
            os.remove(file_path)

    db.session.delete(inmate)
    db.session.commit()
    flash('Inmate deleted successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/inmate/edit/<int:inmate_id>', methods=['GET', 'POST'])
def edit_inmate(inmate_id):
    if 'username' not in session:
        return redirect(url_for('index'))

    inmate = Inmate.query.get_or_404(inmate_id)

    if request.method == 'POST':
        inmate.name = f"{request.form['last'].capitalize()} {request.form['first'].capitalize()} {request.form['initial'].capitalize()}"
        inmate.age = int(request.form['age'])
        inmate.gender = request.form['gender']
        inmate.nationality = request.form['nationality']

        SECURITY_LEVELS = {
            1: "Low Security Inmate",
            2: "Medium Security Inmate",
            3: "High Security Inmate",
            4: "Maximum Security Inmate",
            5: "Death Row Inmate"
        }
        security_level_num = int(request.form['security_level'])
        inmate.security_level = SECURITY_LEVELS.get(security_level_num, "Unknown")

        date_apprehended_str = request.form.get('Apprehended')
        inmate.date_apprehended = datetime.strptime(date_apprehended_str, "%Y-%m-%d").date() if date_apprehended_str else None

        file = request.files.get('evidence_file')
        if file and file.filename != '':
            ext = os.path.splitext(file.filename)[1]
            filename = f"{uuid.uuid4().hex}{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            inmate.evidence_file = filename

        db.session.commit()
        flash('Inmate updated successfully!', 'success')
        return redirect(url_for('dashboard'))

    name_parts = inmate.name.split()
    last, first, initial = (name_parts + ["", "", ""])[:3]

    return render_template('edit_inmate.html', inmate=inmate, last=last, first=first, initial=initial, nationalities=nationalities)

if __name__ == '__main__':

    with app.app_context():
        db.create_all()
        db.session.commit()

    app.run(debug=True)
