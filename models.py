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

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    progress = db.Column(db.Integer, default=0)
    remarks = db.Column(db.Text)
    parent_id = db.Column(db.Integer, db.ForeignKey('task.id'))
    parent = db.relationship('Task', remote_side=[id])
    assignee_id = db.Column(db.Integer, db.ForeignKey('member.id'))
    assignee = db.relationship('Member')
    resource_id = db.Column(db.Integer, db.ForeignKey('resource.id'))
    resource = db.relationship('Resource')
    depends_on_id = db.Column(db.Integer, db.ForeignKey('task.id'))
    depends_on = db.relationship('Task', remote_side=[id])
    is_milestone = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TaskDependency(db.Model):
    """Many-to-many dependency between tasks."""

    id = db.Column(db.Integer, primary_key=True)
    predecessor_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    successor_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    predecessor = db.relationship('Task', foreign_keys=[predecessor_id])
    successor = db.relationship('Task', foreign_keys=[successor_id])
    __table_args__ = (db.UniqueConstraint('predecessor_id', 'successor_id'),)


class Project(db.Model):
    """Project metadata stored in the master database."""

    __bind_key__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    path = db.Column(db.String(255), nullable=False)
