from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
import plotly.figure_factory as ff
import plotly.express as px

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///project.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    progress = db.Column(db.Integer, default=0)


@app.route('/')
def index():
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
    return render_template('index.html', tasks=tasks, gantt=gantt)


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
        return redirect(url_for('index'))
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
        return redirect(url_for('index'))
    return render_template('form.html', task=task)


@app.route('/task/<int:task_id>/delete', methods=['POST'])
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    return redirect(url_for('index'))


@app.route('/burndown')
def burndown():
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
    return render_template('burndown.html', chart=chart)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
