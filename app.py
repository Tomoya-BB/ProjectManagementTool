import os
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, redirect, url_for, request, session, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, Task, User, Project
import pandas as pd
import plotly.figure_factory as ff
import plotly.express as px

app = Flask(__name__)
app.secret_key = 'dev'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

login_manager = LoginManager(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def init_db(project_name):
    """Initialize databases for the given project and master data."""

    base = os.path.abspath(os.path.dirname(__file__))
    projects_dir = os.path.join(base, 'data', 'projects')
    os.makedirs(projects_dir, exist_ok=True)
    db_path = os.path.join(projects_dir, f'{project_name}.db')
    master_path = os.path.join(base, 'data', 'master.db')

    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_BINDS'] = {'users': f'sqlite:///{master_path}'}

    if not getattr(app, 'db_initialized', False):
        db.init_app(app)
        app.db_initialized = True

    with app.app_context():
        db.create_all()

        if not Project.query.filter_by(name=project_name).first():
            project = Project(name=project_name, path=db_path)
            db.session.add(project)

        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', password_hash=generate_password_hash('admin'), role='Admin')
            db.session.add(admin)

        db.session.commit()


@app.before_request
def load_project():
    project = session.get('project')
    allowed = ('select_project', 'create_project', 'login', 'static')
    if not project and request.endpoint not in allowed:
        return redirect(url_for('select_project'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('tasks'))
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/select', methods=['GET', 'POST'])
@login_required
@roles_required('Admin', 'User')
def select_project():
    projects = [p.name for p in Project.query.order_by(Project.name).all()]
    if request.method == 'POST':
        project = request.form['project']
        session['project'] = project
        init_db(project)
        return redirect(url_for('tasks'))
    return render_template('project_select.html', projects=projects)


@app.route('/project/create', methods=['GET', 'POST'])
@login_required
@roles_required('Admin')
def create_project():
    if request.method == 'POST':
        name = request.form['name']
        session['project'] = name
        init_db(name)
        return redirect(url_for('tasks'))
    return render_template('project_create.html')


@app.route('/')
@login_required
def tasks():
    project = session.get('project')
    if not project:
        return redirect(url_for('select_project'))
    tasks = Task.query.all()
    df = pd.DataFrame([
        {
            'Task': t.name,
            'Start': t.start_date,
            'Finish': t.end_date,
            'Complete': t.progress
        }
        for t in tasks
    ])
    if not df.empty:
        fig = ff.create_gantt(
            df,
            index_col='Complete',
            show_colorbar=True,
            bar_width=0.2,
            showgrid_x=True,
            showgrid_y=True
        )
        gantt = fig.to_html(full_html=False)
    else:
        gantt = ''
    return render_template('tasks.html', tasks=tasks, gantt=gantt)


@app.route('/task/add', methods=['GET', 'POST'])
@login_required
@roles_required('Admin', 'User')
def add_task():
    if request.method == 'POST':
        name = request.form['name']
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
        progress = int(request.form['progress'])
        task = Task(name=name, start_date=start_date, end_date=end_date, progress=progress)
        db.session.add(task)
        db.session.commit()
        return redirect(url_for('tasks'))
    return render_template('form.html', task=None)


@app.route('/task/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
@roles_required('Admin', 'User')
def edit_task(task_id):
    task = Task.query.get_or_404(task_id)
    if request.method == 'POST':
        task.name = request.form['name']
        task.start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        task.end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
        task.progress = int(request.form['progress'])
        db.session.commit()
        return redirect(url_for('tasks'))
    return render_template('form.html', task=task)


@app.route('/task/<int:task_id>/delete', methods=['POST'])
@login_required
@roles_required('Admin', 'User')
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    return redirect(url_for('tasks'))


@app.route('/dashboard')
@login_required
def dashboard():
    tasks = Task.query.order_by(Task.end_date).all()
    if not tasks:
        chart = ''
    else:
        df = pd.DataFrame({
            'date': [t.end_date for t in tasks],
            'remaining': [100 - t.progress for t in tasks]
        })
        df = df.sort_values('date')
        df['remaining_total'] = df['remaining'].cumsum()
        fig = px.line(df, x='date', y='remaining_total', title='Burndown Chart')
        chart = fig.to_html(full_html=False)
    return render_template('dashboard.html', chart=chart)


if __name__ == '__main__':
    init_db('project1')
    app.run(debug=True)
