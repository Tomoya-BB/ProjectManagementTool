from collections import defaultdict

from sqlalchemy import func

from models import Task, db


def _task_sort_key(task):
    return (
        task.order_index if task.order_index is not None else 10**9,
        task.start_date,
        task.id,
    )


def next_task_order_index(parent_id, exclude_task_id=None):
    query = db.session.query(func.max(Task.order_index)).filter(Task.parent_id == parent_id)
    if exclude_task_id is not None:
        query = query.filter(Task.id != exclude_task_id)
    max_order = query.scalar()
    return (max_order or 0) + 1


def append_task_to_parent(task, parent_id=None):
    if parent_id is not None:
        task.parent_id = parent_id
    task.order_index = next_task_order_index(task.parent_id, exclude_task_id=task.id)


def get_siblings(parent_id):
    siblings = Task.query.filter(Task.parent_id == parent_id).all()
    siblings.sort(key=_task_sort_key)
    return siblings


def move_task_within_siblings(task, direction):
    if direction not in {"up", "down"}:
        return False

    siblings = get_siblings(task.parent_id)
    current_index = next((index for index, sibling in enumerate(siblings) if sibling.id == task.id), None)
    if current_index is None:
        return False

    target_index = current_index - 1 if direction == "up" else current_index + 1
    if target_index < 0 or target_index >= len(siblings):
        return False

    siblings[current_index], siblings[target_index] = siblings[target_index], siblings[current_index]
    for index, sibling in enumerate(siblings, start=1):
        sibling.order_index = index
    return True


def sort_tasks_hierarchically(tasks):
    task_ids = {task.id for task in tasks}
    children_by_parent = defaultdict(list)
    for task in tasks:
        parent_key = task.parent_id if task.parent_id in task_ids else None
        children_by_parent[parent_key].append(task)

    ordered = []
    visited = set()

    def walk(parent_id, depth):
        for task in sorted(children_by_parent.get(parent_id, []), key=_task_sort_key):
            if task.id in visited:
                continue
            task.display_depth = depth
            ordered.append(task)
            visited.add(task.id)
            walk(task.id, depth + 1)

    walk(None, 0)

    for task in sorted((task for task in tasks if task.id not in visited), key=_task_sort_key):
        task.display_depth = 0
        ordered.append(task)

    return ordered
