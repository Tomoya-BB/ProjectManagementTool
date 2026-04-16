from flask import Blueprint, request, abort
from flask_restful import Api, Resource
from datetime import datetime
from flask_login import login_required, current_user
from models import db, Task
from task_ordering import append_task_to_parent

api_bp = Blueprint('api', __name__)
api = Api(api_bp)

class TaskResource(Resource):
    method_decorators = [login_required]

    def get(self, id):
        task = db.get_or_404(Task, id)
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
    method_decorators = [login_required]

    def post(self):
        if current_user.role == 'Viewer':
            abort(403)
        data = request.get_json() or {}
        task = db.get_or_404(Task, data.get('id'))
        original_parent_id = task.parent_id
        if 'name' in data:
            task.name = data['name']
        if 'start_date' in data:
            task.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        if 'end_date' in data:
            task.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
        if task.end_date < task.start_date:
            return {'status': 'error', 'message': 'End date cannot be before start date.'}, 400
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
        if task.parent_id != original_parent_id:
            append_task_to_parent(task)
        db.session.commit()
        return {'status': 'ok'}

class UpdateDates(Resource):
    method_decorators = [login_required]

    def post(self):
        if current_user.role == 'Viewer':
            abort(403)
        data = request.get_json() or {}
        task = db.get_or_404(Task, data.get('id'))
        if 'start_date' in data:
            task.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        if 'end_date' in data:
            task.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
        if task.end_date < task.start_date:
            return {'status': 'error', 'message': 'End date cannot be before start date.'}, 400
        db.session.commit()
        return {'status': 'ok'}

class BulkEdit(Resource):
    method_decorators = [login_required]

    def post(self):
        if current_user.role == 'Viewer':
            abort(403)
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
