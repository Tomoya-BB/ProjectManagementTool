from flask import Blueprint, request, jsonify
from flask_restful import Api, Resource
from datetime import datetime
from models import db, Task

api_bp = Blueprint('api', __name__)
api = Api(api_bp)

class TaskResource(Resource):
    def get(self, id):
        task = Task.query.get_or_404(id)
        return {
            'id': task.id,
            'name': task.name,
            'start_date': task.start_date.isoformat(),
            'end_date': task.end_date.isoformat(),
            'remarks': task.remarks,
            'release_version': task.release_version,
            'progress': task.progress,
            'assignee_id': task.assignee_id,
            'parent_id': task.parent_id,
        }

class UpdateTask(Resource):
    def post(self):
        data = request.get_json() or {}
        task = Task.query.get_or_404(data.get('id'))
        if 'name' in data:
            task.name = data['name']
        if 'start_date' in data:
            task.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        if 'end_date' in data:
            task.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
        if 'remarks' in data:
            task.remarks = data['remarks']
        if 'release_version' in data:
            task.release_version = data['release_version']
        if 'progress' in data:
            task.progress = int(data['progress'])
        if 'assignee_id' in data:
            task.assignee_id = data['assignee_id']
        if 'parent_id' in data:
            task.parent_id = data['parent_id']
        db.session.commit()
        return {'status': 'ok'}

class UpdateDates(Resource):
    def post(self):
        data = request.get_json() or {}
        task = Task.query.get_or_404(data.get('id'))
        if 'start_date' in data:
            task.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        if 'end_date' in data:
            task.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
        db.session.commit()
        return {'status': 'ok'}

class BulkEdit(Resource):
    def post(self):
        data = request.get_json() or {}
        ids = data.get('ids', [])
        updates = data.get('updates', {})
        tasks = Task.query.filter(Task.id.in_(ids)).all()
        for task in tasks:
            if 'progress' in updates:
                task.progress = updates['progress']
            if 'assignee_id' in updates:
                task.assignee_id = updates['assignee_id']
            if 'release_version' in updates:
                task.release_version = updates['release_version']
        db.session.commit()
        return {'status': 'ok'}

api.add_resource(TaskResource, '/task/<int:id>')
api.add_resource(UpdateTask, '/task/update')
api.add_resource(UpdateDates, '/task/update_dates')
api.add_resource(BulkEdit, '/bulk_edit')
