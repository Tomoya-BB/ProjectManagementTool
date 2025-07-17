import os
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, redirect, url_for, request, session, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, Task, User, Project, Resource
import pandas as pd
import plotly.express as px

app = Flask(__name__)
app.secret_key = 'dev'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

login_manager = LoginManager(app)
login_manager.login_view = 'login'


@app.route('/setup', methods=['GET', 'POST'])
def setup():
    """Create the initial admin user if none exist."""
    if User.query.first():
        return redirect(url_for('login'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        admin = User(username=username,
                     password_hash=generate_password_hash(password),
                     role='Admin')
        db.session.add(admin)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('setup.html')


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

        db.session.commit()


@app.before_request
def load_project():
    project = session.get('project')
    allowed = ('select_project', 'create_project', 'login', 'setup', 'static')
    if not project and request.endpoint not in allowed:
        return redirect(url_for('select_project'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if not getattr(app, 'db_initialized', False):
        init_db('project1')
    if not User.query.first():
        return redirect(url_for('setup'))
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


@app.route('/resources')
@login_required
@roles_required('Admin', 'User')
def resources():
    res = Resource.query.all()
    return render_template('resources.html', resources=res)


@app.route('/resource/add', methods=['GET', 'POST'])
@login_required
@roles_required('Admin', 'User')
def add_resource():
    if request.method == 'POST':
        name = request.form['name']
        role = request.form.get('role')
        color = request.form.get('color')
        utilization = int(request.form.get('utilization') or 100)
        r = Resource(name=name, role=role, color=color, utilization=utilization)
        db.session.add(r)
        db.session.commit()
        return redirect(url_for('resources'))
    return render_template('resource_form.html', resource=None)


@app.route('/resource/<int:resource_id>/edit', methods=['GET', 'POST'])
@login_required
@roles_required('Admin', 'User')
def edit_resource(resource_id):
    resource = Resource.query.get_or_404(resource_id)
    if request.method == 'POST':
        resource.name = request.form['name']
        resource.role = request.form.get('role')
        resource.color = request.form.get('color')
        resource.utilization = int(request.form.get('utilization') or 100)
        db.session.commit()
        return redirect(url_for('resources'))
    return render_template('resource_form.html', resource=resource)


@app.route('/resource/<int:resource_id>/delete', methods=['POST'])
@login_required
@roles_required('Admin', 'User')
def delete_resource(resource_id):
    resource = Resource.query.get_or_404(resource_id)
    db.session.delete(resource)
    db.session.commit()
    return redirect(url_for('resources'))


@app.route('/')
@login_required
def tasks():
    project = session.get('project')
    if not project:
        return redirect(url_for('select_project'))
    tasks = Task.query.all()
    df = pd.DataFrame([
        {
            'name': f'\u25C6 {t.name}' if t.is_milestone else t.name,
            'start': t.start_date,
            'finish': t.end_date if not t.is_milestone else t.start_date,
            'Resource': t.resource.name if t.resource else 'Unassigned',
            'progress': t.progress,
            'depends': t.depends_on.name if t.depends_on else '',
            'type': 'Milestone' if t.is_milestone else 'Task'
        }
        for t in tasks
    ])
    if not df.empty:
        color_map = {r.name: r.color for r in Resource.query.all() if r.color}
        fig = px.timeline(
            df,
            x_start="start",
            x_end="finish",
            y="name",
            color="Resource",
            hover_data={"progress": True, "depends": True},
            color_discrete_map=color_map,
        )
        fig.update_yaxes(autorange="reversed")
        gantt = fig.to_html(full_html=False, include_plotlyjs=False)
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
        resource_id = request.form.get('resource_id') or None
        depends_on_id = request.form.get('depends_on_id') or None
        is_milestone = 'is_milestone' in request.form
        if is_milestone:
            end_date = start_date
        task = Task(
            name=name,
            start_date=start_date,
            end_date=end_date,
            progress=progress,
            resource_id=resource_id,
            depends_on_id=depends_on_id,
            is_milestone=is_milestone,
        )
        db.session.add(task)
        db.session.commit()
        return redirect(url_for('tasks'))
    tasks = Task.query.all()
    resources = Resource.query.all()
    return render_template('form.html', task=None, tasks=tasks, resources=resources)


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
        task.resource_id = request.form.get('resource_id') or None
        depends_on_id = request.form.get('depends_on_id') or None
        task.depends_on_id = depends_on_id
        task.is_milestone = 'is_milestone' in request.form
        if task.is_milestone:
            task.end_date = task.start_date
        db.session.commit()
        return redirect(url_for('tasks'))
    tasks = Task.query.filter(Task.id != task_id).all()
    resources = Resource.query.all()
    return render_template('form.html', task=task, tasks=tasks, resources=resources)


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
