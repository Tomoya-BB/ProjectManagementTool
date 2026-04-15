import os
import json
import socket
from datetime import datetime, date, timedelta
from functools import wraps

from flask import Flask, render_template, redirect, url_for, request, session, abort, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text, func
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from models import db, Task, User, Project, Resource, Member, TaskDependency
from api import api_bp

app = Flask(__name__)
app.secret_key = 'dev'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Keep track of currently opened project directory
current_project_path = None

login_manager = LoginManager(app)
login_manager.login_view = 'login'
app.register_blueprint(api_bp, url_prefix='/api')


def hash_password(password):
    # Use a broadly compatible algorithm so setup/login also work on older Python builds.
    return generate_password_hash(password, method='pbkdf2:sha256')


def get_data_root():
    base = os.path.abspath(os.path.dirname(__file__))
    return os.environ.get('PMT_DATA_DIR', os.path.join(base, 'data'))


def get_projects_dir():
    return os.environ.get('PMT_PROJECTS_DIR', os.path.join(get_data_root(), 'projects'))


def get_master_db_path():
    return os.environ.get('PMT_MASTER_DB', os.path.join(get_data_root(), 'master.db'))


def build_project_manifest(project_name, project_dir, db_file='db.sqlite3'):
    db_path = os.path.join(project_dir, db_file)
    return {
        "name": project_name,
        "db_file": db_file,
        "project_dir": project_dir,
        "db_path": db_path,
    }


def resolve_project_db_path(proj_info, uploaded_filename=''):
    db_path = proj_info.get('db_path')
    if db_path:
        return db_path

    project_dir = proj_info.get('project_dir')
    if not project_dir and uploaded_filename:
        project_dir = os.path.dirname(uploaded_filename)
    if not project_dir:
        project_dir = os.path.join(get_projects_dir(), proj_info.get('name', ''))

    return os.path.join(project_dir, proj_info.get('db_file', 'db.sqlite3'))


def rebuild_sqlalchemy_engines():
    state = app.extensions.get('sqlalchemy')
    if state is None:
        return

    echo = app.config.setdefault("SQLALCHEMY_ECHO", False)
    basic_uri = app.config.setdefault("SQLALCHEMY_DATABASE_URI", None)
    basic_engine_options = state._engine_options.copy()
    basic_engine_options.update(app.config.setdefault("SQLALCHEMY_ENGINE_OPTIONS", {}))
    config_binds = app.config.setdefault("SQLALCHEMY_BINDS", {})
    engine_options = {}

    for key, value in config_binds.items():
        engine_options[key] = state._engine_options.copy()
        if isinstance(value, (str, sa.engine.URL)):
            engine_options[key]["url"] = value
        else:
            engine_options[key].update(value)

    if basic_uri is not None:
        basic_engine_options["url"] = basic_uri
    if "url" in basic_engine_options:
        engine_options.setdefault(None, {}).update(basic_engine_options)

    engines = state._app_engines.setdefault(app, {})
    for engine in engines.values():
        engine.dispose()
    engines.clear()

    for key, options in engine_options.items():
        state._make_metadata(key)
        options.setdefault("echo", echo)
        options.setdefault("echo_pool", echo)
        state._apply_driver_defaults(options, app)
        engines[key] = state._make_engine(key, options, app)

def compute_gantt(tasks):
    import pandas as pd
    import plotly.express as px

    records = []
    for t in tasks:
        records.append({
            'id': t.id,
            'Task': t.name,
            'Start': t.start_date,
            'Finish': t.end_date,
            'Progress': t.progress,
            'resource_name': t.assignee.name if t.assignee else '',
            'release_revision': t.release_version,
        })
    df = pd.DataFrame(records)
    if df.empty:
        return None
    df['release_revision'] = df['release_revision'].fillna('')
    def build_label(row):
        resource_name = row['resource_name']
        release_revision = row['release_revision']
        if resource_name and release_revision:
            return f"{resource_name} ({release_revision})"
        if resource_name:
            return resource_name
        if release_revision:
            return release_revision
        return ""

    df['label'] = df.apply(build_label, axis=1)
    fig = px.timeline(
        df,
        x_start='Start',
        x_end='Finish',
        y='Task',
        color='Progress',
        text='label',
        color_continuous_scale=['#dc3545', '#ffc107', '#28a745'],
        range_color=[0, 100],
    )
    fig.update_traces(textposition='inside', insidetextanchor='middle')
    fig.update_traces(customdata=df[['id']])
    fig.update_yaxes(autorange='reversed')
    fig.update_layout(
        height=max(360, 72 * len(df) + 120),
        margin=dict(l=24, r=24, t=24, b=24),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(255,255,255,0.92)',
    )
    return fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        default_height=f"{max(360, 72 * len(df) + 120)}px",
        default_width="100%",
        config={"responsive": True},
    )


@app.route('/setup', methods=['GET', 'POST'])
def setup():
    """Create the initial admin user if none exist."""
    if User.query.first():
        return redirect(url_for('login'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        admin = User(username=username,
                     password_hash=hash_password(password),
                     role='Admin')
        db.session.add(admin)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('setup.html')


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


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


def init_db(project_name, db_path=None):
    """Initialize databases for the given project and master data."""

    if db_path is None:
        projects_dir = get_projects_dir()
        os.makedirs(projects_dir, exist_ok=True)
        db_path = os.path.join(projects_dir, f'{project_name}.db')
    else:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    master_path = get_master_db_path()
    os.makedirs(os.path.dirname(master_path), exist_ok=True)

    database_uri = f'sqlite:///{db_path}'
    bind_uris = {'users': f'sqlite:///{master_path}'}
    config_changed = (
        app.config.get('SQLALCHEMY_DATABASE_URI') != database_uri
        or app.config.get('SQLALCHEMY_BINDS') != bind_uris
    )

    app.config['SQLALCHEMY_DATABASE_URI'] = database_uri
    app.config['SQLALCHEMY_BINDS'] = bind_uris

    if not getattr(app, 'db_initialized', False):
        db.init_app(app)
        app.db_initialized = True
    elif config_changed:
        with app.app_context():
            db.session.remove()
        rebuild_sqlalchemy_engines()

    with app.app_context():
        db.create_all()

        engine = db.engine
        with engine.connect() as conn:
            cols = [c[1] for c in conn.execute(text("PRAGMA table_info(tasks)")).fetchall()]
        if 'remarks' not in cols:
            with engine.begin() as conn:
                conn.execute(text('ALTER TABLE tasks ADD COLUMN remarks TEXT'))
        if 'parent_id' not in cols:
            with engine.begin() as conn:
                conn.execute(text('ALTER TABLE tasks ADD COLUMN parent_id INTEGER'))
        if 'assignee_id' not in cols:
            with engine.begin() as conn:
                conn.execute(text('ALTER TABLE tasks ADD COLUMN assignee_id INTEGER'))
        if 'release_version' not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE tasks ADD COLUMN release_version VARCHAR"))

        user_engine = db.engines['users']
        with user_engine.connect() as conn:
            ucols = [c[1] for c in conn.execute(text("PRAGMA table_info(user)")).fetchall()]
        if 'role' not in ucols:
            with user_engine.begin() as conn:
                conn.execute(text("ALTER TABLE user ADD COLUMN role VARCHAR DEFAULT 'Viewer'"))
                conn.execute(text("UPDATE user SET role='Viewer'"))

        if not Project.query.filter_by(name=project_name).first():
            project = Project(name=project_name, path=db_path)
            db.session.add(project)

        db.session.commit()


def resolve_dev_port(default_port=5000, max_attempts=20):
    """Use the first available local port, starting from default_port."""
    if 'APP_RUN_PORT' in os.environ:
        return int(os.environ['APP_RUN_PORT'])

    requested_port = int(os.environ.get('PORT', default_port))
    if 'PORT' in os.environ:
        return requested_port

    for port in range(requested_port, requested_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(('127.0.0.1', port))
            except OSError:
                continue
            return port

    return requested_port


@app.before_request
def load_project():
    project = session.get('project')
    allowed = ('select_project', 'create_project', 'new_project', 'open_project', 'usage_guide', 'login', 'setup', 'static')
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
            return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/guide')
def usage_guide():
    return render_template('guide.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/select', methods=['GET', 'POST'])
@login_required
def select_project():
    projects = [p.name for p in Project.query.order_by(Project.name).all()]
    if request.method == 'POST':
        project = request.form['project']
        session['project'] = project
        init_db(project)
        return redirect(url_for('dashboard'))
    return render_template('project_select.html', projects=projects)


@app.route('/project/create', methods=['GET', 'POST'])
@login_required
@roles_required('Admin')
def create_project():
    if request.method == 'POST':
        name = request.form['name']
        session['project'] = name
        init_db(name)
        return redirect(url_for('dashboard'))
    return render_template('project_create.html')


@app.route('/project/new', methods=['GET', 'POST'])
@login_required
@roles_required('Admin')
def new_project():
    """Create a new project folder with sqlite db and json."""
    if request.method == 'POST':
        proj_name = request.form['project_name']
        save_dir = request.form['save_path']
        project_dir = os.path.join(save_dir, proj_name)
        os.makedirs(project_dir, exist_ok=True)
        proj_info = build_project_manifest(proj_name, project_dir)
        with open(os.path.join(project_dir, 'project.json'), 'w', encoding='utf-8') as f:
            json.dump(proj_info, f, ensure_ascii=False, indent=4)
        db_path = os.path.join(project_dir, 'db.sqlite3')
        init_db(proj_name, db_path)
        global current_project_path
        current_project_path = project_dir
        session['project'] = proj_name
        flash(f"New project '{proj_name}' created at {project_dir}", 'success')
        return redirect(url_for('dashboard'))
    return render_template('new_project.html')


@app.route('/project/open', methods=['GET', 'POST'])
@login_required
def open_project():
    if request.method == 'POST':
        file = request.files.get('project_file')
        if file:
            proj_info = json.load(file)
            db_path = resolve_project_db_path(proj_info, file.filename)
            if os.path.exists(db_path):
                proj_dir = os.path.dirname(db_path)
                init_db(proj_info.get('name'), db_path)
                global current_project_path
                current_project_path = proj_dir
                session['project'] = proj_info.get('name')
                flash(f"Project '{proj_info.get('name')}' opened.", 'info')
                return redirect(url_for('dashboard'))
            else:
                flash('Database file not found.', 'danger')
                return redirect(url_for('open_project'))
    return render_template('open_project.html')


@app.route('/resources')
@login_required
@roles_required('Admin', 'Editor')
def resources():
    res = Resource.query.all()
    return render_template('resources.html', resources=res)


@app.route('/members', methods=['GET', 'POST'])
@login_required
@roles_required('Admin')
def members():
    if request.method == 'POST':
        name = request.form['name'].strip()
        if name:
            try:
                db.session.add(Member(name=name))
                db.session.commit()
                flash(f"メンバー「{name}」を追加しました。", 'success')
            except IntegrityError:
                db.session.rollback()
                flash(f"メンバー「{name}」は既に存在します。", 'warning')
        return redirect(url_for('members'))
    all_members = Member.query.order_by(Member.name).all()
    return render_template('members.html', members=all_members)




@app.route('/member/<int:member_id>/edit', methods=['GET', 'POST'])
@login_required
@roles_required('Admin')
def edit_member(member_id):
    member = db.get_or_404(Member, member_id)
    if request.method == 'POST':
        member.name = request.form['name'].strip()
        try:
            db.session.commit()
            flash('メンバーを更新しました。', 'success')
        except IntegrityError:
            db.session.rollback()
            flash('同名のメンバーが既に存在します。', 'warning')
        return redirect(url_for('members'))
    return render_template('members.html', member=member, members=Member.query.all())


@app.route('/member/<int:member_id>/delete', methods=['POST'])
@login_required
@roles_required('Admin')
def delete_member(member_id):
    member = db.get_or_404(Member, member_id)
    db.session.delete(member)
    Task.query.filter_by(assignee_id=member.id).update({'assignee_id': None})
    db.session.commit()
    flash(f"メンバー「{member.name}」を削除しました。", 'info')
    return redirect(url_for('members'))


@app.route('/resource/add', methods=['GET', 'POST'])
@login_required
@roles_required('Admin', 'Editor')
def add_resource():
    if request.method == 'POST':
        name = request.form['name']
        role = request.form.get('role')
        color = request.form.get('color')
        utilization = int(request.form.get('utilization') or 100)
        r = Resource(name=name, role=role, color=color, utilization=utilization)
        db.session.add(r)
        db.session.commit()
        flash('Resource added', 'success')
        return redirect(url_for('resources'))
    return render_template('resource_form.html', resource=None)


@app.route('/resource/<int:resource_id>/edit', methods=['GET', 'POST'])
@login_required
@roles_required('Admin', 'Editor')
def edit_resource(resource_id):
    resource = db.get_or_404(Resource, resource_id)
    if request.method == 'POST':
        resource.name = request.form['name']
        resource.role = request.form.get('role')
        resource.color = request.form.get('color')
        resource.utilization = int(request.form.get('utilization') or 100)
        db.session.commit()
        flash('Resource updated', 'success')
        return redirect(url_for('resources'))
    return render_template('resource_form.html', resource=resource)


@app.route('/resource/<int:resource_id>/delete', methods=['POST'])
@login_required
@roles_required('Admin', 'Editor')
def delete_resource(resource_id):
    resource = db.get_or_404(Resource, resource_id)
    db.session.delete(resource)
    db.session.commit()
    flash('Resource deleted', 'success')
    return redirect(url_for('resources'))


@app.route('/index')
@login_required
def index():
    """Project overview metrics."""
    tasks = Task.query.all()
    total = len(tasks)
    completed = sum(1 for t in tasks if t.progress == 100)
    avg_progress = int(sum(t.progress for t in tasks) / total) if total else 0
    return render_template('index.html', total=total, completed=completed,
                           avg_progress=avg_progress)


@app.route('/tasks', methods=['GET', 'POST'])
@app.route('/', methods=['GET', 'POST'])
@login_required
def tasks():
    project = session.get('project')
    if not project:
        return redirect(url_for('select_project'))

    if request.method == 'POST':
        if current_user.role == 'Viewer':
            abort(403)
        name = request.form['name']
        start = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        end = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
        if end < start:
            flash('End date cannot be before start date.', 'danger')
            return redirect(url_for('tasks'))
        remarks = request.form.get('remarks', '')
        release_version = request.form.get('release_version')
        assignee_id = request.form.get('assignee_id', type=int)
        progress = int(request.form.get('progress', 0))
        parent_id = request.form.get('parent_id', type=int)
        task = Task(name=name, start_date=start, end_date=end,
                    remarks=remarks, release_version=release_version,
                    progress=progress,
                    assignee_id=assignee_id, parent_id=parent_id)
        db.session.add(task)
        db.session.commit()
        predecessors = request.form.getlist('predecessors')
        for pid in predecessors:
            try:
                pid = int(pid)
            except ValueError:
                continue
            if pid and pid != task.id:
                db.session.add(TaskDependency(predecessor_id=pid, successor_id=task.id))
        db.session.commit()
        flash(f"New task '{name}' added.", 'success')
        return redirect(url_for('tasks'))

    release = request.args.get('release')
    assignee = request.args.get('assignee', type=int)
    sort_by = request.args.get('sort', 'start_date')

    query = Task.query
    if release:
        query = query.filter(func.lower(func.trim(Task.release_version)) == release.strip().lower())
    if assignee:
        query = query.filter(Task.assignee_id == assignee)

    if sort_by == 'release':
        query = query.order_by(Task.release_version, Task.start_date)
    elif sort_by == 'assignee':
        query = query.outerjoin(Member, Task.assignee).order_by(Member.name.is_(None), Member.name, Task.start_date)
    else:
        query = query.order_by(Task.start_date)

    tasks = query.all()
    members = Member.query.all()
    releases = [r[0] for r in db.session.query(Task.release_version).distinct().all() if r[0]]
    deps = TaskDependency.query.all()
    current_date = date.today()
    day = timedelta(days=1)
    return render_template(
        'tasks.html',
        tasks=tasks,
        members=members,
        releases=releases,
        selected_release=release,
        selected_assignee=assignee,
        sort_by=sort_by,
        deps=deps,
        current_date=current_date,
        day=day,
    )


@app.route('/task/add', methods=['GET', 'POST'])
@login_required
@roles_required('Admin', 'Editor')
def add_task():
    if request.method == 'POST':
        name = request.form['name']
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
        if end_date < start_date:
            flash('End date cannot be before start date.', 'danger')
            return redirect(url_for('add_task'))
        progress = int(request.form.get('progress') or 0)
        release_version = request.form.get('release_version')
        assignee_id = request.form.get('assignee_id') or None
        depends_on_id = request.form.get('depends_on_id') or None
        is_milestone = 'is_milestone' in request.form
        if is_milestone:
            end_date = start_date
        task = Task(
            name=name,
            start_date=start_date,
            end_date=end_date,
            release_version=release_version,
            progress=progress,
            assignee_id=assignee_id,
            depends_on_id=depends_on_id,
            is_milestone=is_milestone,
        )
        db.session.add(task)
        db.session.commit()
        flash('Task added', 'success')
        return redirect(url_for('tasks'))
    tasks = Task.query.all()
    members = Member.query.all()
    return render_template('form.html', task=None, tasks=tasks, members=members)


@app.route('/task/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    task = db.get_or_404(Task, task_id)
    if current_user.role == 'Viewer':
        abort(403)
    if request.method == 'POST':
        task.name = request.form['name']
        task.start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        task.end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
        if task.end_date < task.start_date:
            flash('End date cannot be before start date.', 'danger')
            return redirect(url_for('edit_task', task_id=task.id))
        task.remarks = request.form.get('remarks', '')
        task.release_version = request.form.get('release_version')
        task.progress = int(request.form.get('progress', task.progress))
        task.assignee_id = request.form.get('assignee_id', type=int)
        task.parent_id = request.form.get('parent_id', type=int)
        task.is_milestone = 'is_milestone' in request.form
        if task.is_milestone:
            task.end_date = task.start_date
        db.session.commit()
        TaskDependency.query.filter_by(successor_id=task.id).delete()
        predecessors = request.form.getlist('predecessors')
        for pid in predecessors:
            try:
                pid = int(pid)
            except ValueError:
                continue
            if pid and pid != task.id:
                db.session.add(TaskDependency(predecessor_id=pid, successor_id=task.id))
        db.session.commit()
        flash('Task updated', 'success')
        return redirect(url_for('tasks'))
    tasks = Task.query.filter(Task.id != task_id).all()
    members = Member.query.all()
    deps = TaskDependency.query.all()
    return render_template('form.html', task=task, tasks=tasks, members=members, deps=deps)


@app.route('/task/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    if current_user.role not in ['Admin', 'Editor']:
        abort(403)
    task = db.get_or_404(Task, task_id)
    TaskDependency.query.filter((TaskDependency.predecessor_id == task.id) | (TaskDependency.successor_id == task.id)).delete()
    db.session.delete(task)
    db.session.commit()
    flash('Task deleted', 'success')
    return redirect(url_for('tasks'))


@app.route('/task/update', methods=['POST'])
@login_required
@roles_required('Admin', 'Editor')
def update_task():
    data = request.get_json()
    task_id = data.get('id')
    task = db.get_or_404(Task, task_id)
    task.name = data.get('name', task.name)
    start_value = data.get('start_date')
    end_value = data.get('end_date')
    if start_value:
        task.start_date = datetime.strptime(start_value, '%Y-%m-%d').date()
    if end_value:
        task.end_date = datetime.strptime(end_value, '%Y-%m-%d').date()
    if task.end_date < task.start_date:
        return {'status': 'error', 'message': 'End date cannot be before start date.'}, 400
    task.remarks = data.get('remarks', task.remarks)
    task.release_version = data.get('release_version', task.release_version)
    task.progress = int(data.get('progress', task.progress))
    task.assignee_id = data.get('assignee_id') or None
    task.parent_id = data.get('parent_id') or None
    task.is_milestone = data.get('is_milestone', False)
    if task.is_milestone:
        task.end_date = task.start_date
    TaskDependency.query.filter_by(successor_id=task.id).delete()
    for pid in data.get('predecessors', []):
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            continue
        if pid and pid != task.id:
            db.session.add(TaskDependency(predecessor_id=pid, successor_id=task.id))
    db.session.commit()
    return {'status': 'ok'}


@app.route('/dashboard')
@login_required
def dashboard():
    release = request.args.get('release')
    query = Task.query
    if release:
        query = query.filter(func.lower(func.trim(Task.release_version)) == release.strip().lower())
    tasks = query.all()
    releases = [r[0] for r in db.session.query(Task.release_version).distinct().all() if r[0]]
    total_tasks = len(tasks)
    completed_tasks = sum(1 for t in tasks if t.progress == 100)
    overdue_tasks = sum(1 for t in tasks if t.progress < 100 and t.end_date < date.today())
    progress_rate = int(completed_tasks / total_tasks * 100) if total_tasks else 0

    remaining_by_date = []
    if total_tasks:
        start_date = min(t.start_date for t in tasks)
        end_date = max(t.end_date for t in tasks)
        cur_date = start_date
        while cur_date <= end_date:
            remaining = sum(1 for t in tasks if t.progress < 100 and t.end_date >= cur_date)
            remaining_by_date.append({"date": cur_date.strftime("%Y-%m-%d"), "remaining": remaining})
            cur_date += timedelta(days=1)
    gantt = compute_gantt(tasks) if tasks else None
    return render_template('index.html', **{
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "overdue_tasks": overdue_tasks,
        "progress_rate": progress_rate,
        "remaining_by_date": remaining_by_date,
        "releases": releases,
        "selected_release": release,
        "gantt": gantt
    })


@app.route('/gantt')
@login_required
def gantt_chart():
    release = request.args.get('release')
    query = Task.query
    if release:
        query = query.filter(func.lower(func.trim(Task.release_version)) == release.strip().lower())
    tasks = query.all()
    releases = [r[0] for r in db.session.query(Task.release_version).distinct().all() if r[0]]
    gantt = compute_gantt(tasks) if tasks else None
    return render_template(
        "gantt.html",
        gantt=gantt,
        releases=releases,
        selected_release=release,
    )


if __name__ == '__main__':
    init_db('project1')
    port = resolve_dev_port()
    os.environ.setdefault('APP_RUN_PORT', str(port))
    if port != 5000:
        print(f"Port 5000 is busy. Starting on http://127.0.0.1:{port} instead.")
    app.run(debug=True, port=port)
