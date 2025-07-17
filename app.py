import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, session
from models import db, Task
import pandas as pd
import plotly.figure_factory as ff
import plotly.express as px

app = Flask(__name__)
app.secret_key = 'dev'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


def init_db(project_name):
    base = os.path.abspath(os.path.dirname(__file__))
    os.makedirs(os.path.join(base, 'data', 'projects'), exist_ok=True)
    db_path = os.path.join(base, 'data', 'projects', f'{project_name}.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    db.init_app(app)
    with app.app_context():
        db.create_all()


@app.before_request
def load_project():
    project = session.get('project')
    if not project and request.endpoint not in ('select_project', 'static'):
        return redirect(url_for('select_project'))


@app.route('/select', methods=['GET', 'POST'])
def select_project():
    projects = [p[:-3] for p in os.listdir('data/projects') if p.endswith('.db')]
    if request.method == 'POST':
        project = request.form['project']
        session['project'] = project
        init_db(project)
        return redirect(url_for('tasks'))
    return render_template('project_select.html', projects=projects)


@app.route('/')
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
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    return redirect(url_for('tasks'))


@app.route('/dashboard')
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
