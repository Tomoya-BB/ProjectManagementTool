from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

# database instance
# 'db' is used for task databases (per project) and also binds to the user database

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __bind_key__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    # Default to Viewer permissions for regular users
    role = db.Column(db.String(20), nullable=False, default='Viewer')

class Resource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(100))
    color = db.Column(db.String(20))
    utilization = db.Column(db.Integer, default=100)


class Member(db.Model):
    """Project team member."""

    __tablename__ = 'members'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    def __repr__(self):
        return f'<Member {self.name}>'


class Task(db.Model):
    __tablename__ = 'tasks'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    remarks = db.Column(db.Text, nullable=True)
    progress = db.Column(db.Integer, nullable=False, default=0)
    parent_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=True)
    assignee_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=True)
    # relationships
    children = db.relationship(
        'Task', backref=db.backref('parent', remote_side=[id])
    )
    assignee = db.relationship(
        'Member', backref=db.backref('tasks', lazy='dynamic')
    )
    resource_id = db.Column(db.Integer, db.ForeignKey('resource.id'))
    resource = db.relationship('Resource')
    depends_on_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))
    depends_on = db.relationship('Task', remote_side=[id])
    is_milestone = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Task {self.name}>'


class TaskDependency(db.Model):
    __tablename__ = 'task_dependencies'

    id = db.Column(db.Integer, primary_key=True)
    predecessor_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    successor_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    # relationships
    predecessor = db.relationship(
        'Task', foreign_keys=[predecessor_id], backref='successor_links'
    )
    successor = db.relationship(
        'Task', foreign_keys=[successor_id], backref='predecessor_links'
    )


class Project(db.Model):
    """Project metadata stored in the master database."""

    __bind_key__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    path = db.Column(db.String(255), nullable=False)
