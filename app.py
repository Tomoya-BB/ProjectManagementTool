import os
import json
from datetime import datetime, date, timedelta
from functools import wraps

from flask import Flask, render_template, redirect, url_for, request, session, abort, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, Task, User, Project, Resource, Member, TaskDependency

app = Flask(__name__)
app.secret_key = 'dev'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Keep track of currently opened project directory
current_project_path = None

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


def init_db(project_name, db_path=None):
    """Initialize databases for the given project and master data."""

    base = os.path.abspath(os.path.dirname(__file__))
    if db_path is None:
        projects_dir = os.path.join(base, 'data', 'projects')
        os.makedirs(projects_dir, exist_ok=True)
        db_path = os.path.join(projects_dir, f'{project_name}.db')
    else:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    master_path = os.path.join(base, 'data', 'master.db')

    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_BINDS'] = {'users': f'sqlite:///{master_path}'}

    if not getattr(app, 'db_initialized', False):
        db.init_app(app)
        app.db_initialized = True

    with app.app_context():
        db.create_all()

        engine = db.get_engine(app)
        cols = [c[1] for c in engine.execute("PRAGMA table_info(tasks)").fetchall()]
        if 'remarks' not in cols:
            engine.execute('ALTER TABLE tasks ADD COLUMN remarks TEXT')
        if 'parent_id' not in cols:
            engine.execute('ALTER TABLE tasks ADD COLUMN parent_id INTEGER')
        if 'assignee_id' not in cols:
            engine.execute('ALTER TABLE tasks ADD COLUMN assignee_id INTEGER')

        user_engine = db.get_engine(app, bind='users')
        ucols = [c[1] for c in user_engine.execute("PRAGMA table_info(user)").fetchall()]
        if 'role' not in ucols:
            user_engine.execute("ALTER TABLE user ADD COLUMN role VARCHAR DEFAULT 'Viewer'")
            user_engine.execute("UPDATE user SET role='Viewer'")

        if not Project.query.filter_by(name=project_name).first():
            project = Project(name=project_name, path=db_path)
            db.session.add(project)

        db.session.commit()


@app.before_request
def load_project():
    project = session.get('project')
    allowed = ('select_project', 'create_project', 'new_project', 'open_project', 'login', 'setup', 'static')
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


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/select', methods=['GET', 'POST'])
@login_required
@roles_required('Admin', 'Editor')
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
        proj_info = {"name": proj_name, "db_file": "db.sqlite3"}
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
            proj_dir = os.path.dirname(file.filename) or os.path.join(app.root_path, 'data', 'projects', proj_info.get('name'))
            db_path = os.path.join(proj_dir, proj_info.get('db_file', 'db.sqlite3'))
            if os.path.exists(db_path):
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
def members():
    if request.method == 'POST':
        if current_user.role != 'Admin':
            abort(403)
        name = request.form['name'].strip()
        if name:
            db.session.add(Member(name=name))
            db.session.commit()
            flash(f"メンバー「{name}」を追加しました。", 'success')
        return redirect(url_for('members'))
    all_members = Member.query.order_by(Member.name).all()
    return render_template('members.html', members=all_members)




@app.route('/member/<int:member_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_member(member_id):
    member = Member.query.get_or_404(member_id)
    if current_user.role != 'Admin':
        abort(403)
    if request.method == 'POST':
        member.name = request.form['name']
        db.session.commit()
        flash('Member updated', 'success')
        return redirect(url_for('members'))
    return render_template('members.html', member=member, members=Member.query.all())


@app.route('/member/<int:member_id>/delete', methods=['POST'])
@login_required
def delete_member(member_id):
    if current_user.role != 'Admin':
        abort(403)
    member = Member.query.get_or_404(member_id)
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
    resource = Resource.query.get_or_404(resource_id)
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
    resource = Resource.query.get_or_404(resource_id)
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
@app.route('/')
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
        remarks = request.form.get('remarks', '')
        assignee_id = request.form.get('assignee_id', type=int)
        progress = int(request.form.get('progress', 0))
        parent_id = request.form.get('parent_id', type=int)
        task = Task(name=name, start_date=start, end_date=end,
                    remarks=remarks, progress=progress,
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

    tasks = Task.query.order_by(Task.start_date).all()
    members = Member.query.all()
    deps = TaskDependency.query.all()
    current_date = date.today()
    day = timedelta(days=1)
    return render_template(
        'tasks.html',
        tasks=tasks,
        members=members,
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
        progress = int(request.form['progress'])
        assignee_id = request.form.get('assignee_id') or None
        depends_on_id = request.form.get('depends_on_id') or None
        is_milestone = 'is_milestone' in request.form
        if is_milestone:
            end_date = start_date
        task = Task(
            name=name,
            start_date=start_date,
            end_date=end_date,
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
    task = Task.query.get_or_404(task_id)
    if current_user.role == 'Viewer':
        abort(403)
    if request.method == 'POST':
        task.name = request.form['name']
        task.start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        task.end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
        task.remarks = request.form.get('remarks', '')
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
    task = Task.query.get_or_404(task_id)
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
    task = Task.query.get_or_404(task_id)
    task.name = data.get('name', task.name)
    task.start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d').date()
    task.end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d').date()
    task.remarks = data.get('remarks', task.remarks)
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
    tasks = Task.query.all()
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

    return render_template('index.html', **{
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "overdue_tasks": overdue_tasks,
        "progress_rate": progress_rate,
        "remaining_by_date": remaining_by_date
    })


if __name__ == '__main__':
    init_db('project1')
    app.run(debug=True)
