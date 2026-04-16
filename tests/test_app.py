import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import date, timedelta

TEST_ROOT = tempfile.mkdtemp(prefix="pmt-tests-")
os.environ.setdefault("PMT_DATA_DIR", os.path.join(TEST_ROOT, "data"))
os.environ.setdefault("PMT_PROJECTS_DIR", os.path.join(TEST_ROOT, "projects"))
os.environ.setdefault("PMT_MASTER_DB", os.path.join(TEST_ROOT, "data", "master.db"))

import app as app_module  # noqa: E402
from models import Member, Project, Task, TaskDependency, User, db  # noqa: E402


class ProjectManagementToolTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app_module.app.config.update(TESTING=True)
        app_module.init_db("test-project")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    def setUp(self):
        self.app = app_module.app
        self.client = self.app.test_client()
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        app_module.init_db("test-project")

    def create_user(self, username, role="Admin", password="secret"):
        with self.app.app_context():
            user = User(
                username=username,
                password_hash=app_module.hash_password(password),
                role=role,
            )
            db.session.add(user)
            db.session.commit()
            return user.id

    def create_member(self, name):
        with self.app.app_context():
            member = Member(name=name)
            db.session.add(member)
            db.session.commit()
            return member.id

    def create_task(
        self,
        name,
        assignee_id=None,
        release_version=None,
        progress=0,
        parent_id=None,
        start_date=None,
        end_date=None,
    ):
        with self.app.app_context():
            task = Task(
                name=name,
                start_date=start_date or date(2026, 4, 1),
                end_date=end_date or date(2026, 4, 5),
                remarks=f"remarks for {name}",
                release_version=release_version,
                progress=progress,
                assignee_id=assignee_id,
                parent_id=parent_id,
            )
            db.session.add(task)
            db.session.commit()
            return task.id

    def login(self, username="admin", password="secret"):
        return self.client.post(
            "/login",
            data={"username": username, "password": password},
            follow_redirects=False,
        )

    def open_selected_project(self, project_name="test-project"):
        return self.client.post(
            "/select",
            data={"project": project_name},
            follow_redirects=False,
        )

    def login_and_open_project(self, username="admin", password="secret"):
        self.login(username=username, password=password)
        return self.open_selected_project()

    def test_setup_creates_initial_admin(self):
        response = self.client.post(
            "/setup",
            data={"username": "bootstrap-admin", "password": "secret"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            user = User.query.filter_by(username="bootstrap-admin").first()
            self.assertIsNotNone(user)
            self.assertEqual(user.role, "Admin")

    def test_viewer_can_select_project_and_view_tasks(self):
        self.create_user("viewer", role="Viewer")

        self.login("viewer")
        page = self.client.get("/select")
        response = self.open_selected_project()
        tasks_page = self.client.get("/tasks")

        self.assertEqual(page.status_code, 200)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(tasks_page.status_code, 200)
        self.assertIn("タスク".encode(), tasks_page.data)

    def test_viewer_cannot_create_or_update_tasks(self):
        self.create_user("viewer", role="Viewer")
        task_id = self.create_task("Read only task")

        self.login_and_open_project("viewer")

        create_response = self.client.post(
            "/tasks",
            data={
                "name": "Blocked task",
                "start_date": "2026-04-01",
                "end_date": "2026-04-02",
                "progress": "10",
            },
        )
        api_response = self.client.post(
            "/api/task/update",
            json={"id": task_id, "progress": 50},
        )

        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(api_response.status_code, 403)

    def test_member_duplicates_are_rejected_without_500(self):
        self.create_user("admin")
        self.login_and_open_project()

        first = self.client.post("/members", data={"name": "Alice"}, follow_redirects=True)
        second = self.client.post("/members", data={"name": "Alice"}, follow_redirects=True)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        with self.app.app_context():
            self.assertEqual(Member.query.filter_by(name="Alice").count(), 1)

    def test_assignee_sort_keeps_unassigned_tasks_visible(self):
        self.create_user("admin")
        member_id = self.create_member("Bob")
        self.create_task("Assigned task", assignee_id=member_id)
        self.create_task("Unassigned task")

        self.login_and_open_project()
        response = self.client.get("/tasks?sort=assignee")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Assigned task".encode(), response.data)
        self.assertIn("Unassigned task".encode(), response.data)

    def test_new_project_manifest_can_be_uploaded_and_reopened(self):
        self.create_user("admin")
        self.login("admin")

        save_dir = os.path.join(TEST_ROOT, "workspace")
        os.makedirs(save_dir, exist_ok=True)
        create_response = self.client.post(
            "/project/new",
            data={"project_name": "RoundTrip", "save_path": save_dir},
            follow_redirects=False,
        )
        manifest_path = os.path.join(save_dir, "RoundTrip", "project.json")

        with open(manifest_path, "rb") as handle:
            upload_response = self.client.post(
                "/project/open",
                data={"project_file": (io.BytesIO(handle.read()), "project.json")},
                content_type="multipart/form-data",
                follow_redirects=False,
            )

        self.assertEqual(create_response.status_code, 302)
        self.assertEqual(upload_response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertEqual(session["project"], "RoundTrip")

        with open(manifest_path, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        self.assertEqual(manifest["project_dir"], os.path.join(save_dir, "RoundTrip"))
        self.assertTrue(os.path.exists(manifest["db_path"]))

    def test_api_get_and_update_task(self):
        self.create_user("admin")
        member_id = self.create_member("API Owner")
        task_id = self.create_task("API task", assignee_id=member_id, release_version="v1.0")

        self.login_and_open_project()

        get_response = self.client.get(f"/api/task/{task_id}")
        update_response = self.client.post(
            "/api/task/update",
            json={
                "id": task_id,
                "name": "Updated API task",
                "start_date": "2026-04-02",
                "end_date": "2026-04-06",
                "progress": 80,
                "remarks": "updated",
            },
        )

        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json["name"], "API task")
        self.assertEqual(update_response.status_code, 200)

        with self.app.app_context():
            task = db.session.get(Task, task_id)
            self.assertEqual(task.name, "Updated API task")
            self.assertEqual(task.progress, 80)
            self.assertEqual(task.remarks, "updated")

    def test_inline_task_update_accepts_partial_payload(self):
        self.create_user("admin")
        task_id = self.create_task("Inline update task", progress=10)

        self.login_and_open_project()
        response = self.client.post("/task/update", json={"id": task_id, "progress": 55})

        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            self.assertEqual(db.session.get(Task, task_id).progress, 55)

    def test_invalid_task_dates_are_rejected(self):
        self.create_user("admin")
        task_id = self.create_task("Validation target")

        self.login_and_open_project()

        create_response = self.client.post(
            "/tasks",
            data={
                "name": "Broken task",
                "start_date": "2026-04-05",
                "end_date": "2026-04-01",
                "progress": "0",
            },
            follow_redirects=True,
        )
        update_response = self.client.post(
            "/task/update",
            json={"id": task_id, "start_date": "2026-04-05", "end_date": "2026-04-01"},
        )

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(update_response.status_code, 400)
        with self.app.app_context():
            self.assertEqual(Task.query.filter_by(name="Broken task").count(), 0)

    def test_dashboard_and_gantt_pages_render(self):
        self.create_user("admin")
        self.create_task("Visible on charts", release_version="v2.0", progress=30)

        self.login_and_open_project()
        dashboard = self.client.get("/dashboard")
        gantt = self.client.get("/gantt")

        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(gantt.status_code, 200)
        self.assertIn("Visible on charts".encode(), dashboard.data)
        self.assertIn("plotly".encode(), gantt.data.lower())

    def test_compute_gantt_keeps_complete_label_text(self):
        with self.app.app_context():
            member = Member(name="Alice")
            db.session.add(member)
            db.session.flush()
            task = Task(
                name="Chart task",
                start_date=date(2026, 4, 1),
                end_date=date(2026, 4, 3),
                release_version="v1.0",
                progress=50,
                assignee_id=member.id,
            )
            db.session.add(task)
            db.session.commit()

            html = app_module.compute_gantt([task])

        self.assertIn("Alice (v1.0)", html)
        self.assertIn("rgba(20, 33, 61, 0.08)", html)

    def test_compute_member_availability_tracks_busy_and_free_members(self):
        with self.app.app_context():
            alice = Member(name="Alice")
            bob = Member(name="Bob")
            carol = Member(name="Carol")
            db.session.add_all([alice, bob, carol])
            db.session.flush()
            db.session.add_all([
                Task(
                    name="Alice active",
                    start_date=date(2026, 4, 1),
                    end_date=date(2026, 4, 3),
                    progress=10,
                    assignee_id=alice.id,
                ),
                Task(
                    name="Alice next",
                    start_date=date(2026, 4, 4),
                    end_date=date(2026, 4, 5),
                    progress=0,
                    assignee_id=alice.id,
                ),
                Task(
                    name="Carol future",
                    start_date=date(2026, 4, 10),
                    end_date=date(2026, 4, 12),
                    progress=0,
                    assignee_id=carol.id,
                ),
            ])
            db.session.commit()

            availability = app_module.compute_member_availability(
                Member.query.order_by(Member.name).all(),
                Task.query.order_by(Task.id).all(),
                reference_date=date(2026, 4, 2),
            )

        alice_slot = next(slot for slot in availability if slot["member"].name == "Alice")
        bob_slot = next(slot for slot in availability if slot["member"].name == "Bob")
        carol_slot = next(slot for slot in availability if slot["member"].name == "Carol")

        self.assertTrue(alice_slot["is_busy_today"])
        self.assertEqual(alice_slot["next_available_label"], "2026-04-06")
        self.assertEqual(alice_slot["next_task_label"], "2026-04-04 から")
        self.assertEqual(alice_slot["scheduled_days"], 4)
        self.assertFalse(bob_slot["is_busy_today"])
        self.assertEqual(bob_slot["next_available_label"], "今日")
        self.assertEqual(bob_slot["next_task_label"], "予定なし")
        self.assertEqual(carol_slot["next_task_label"], "2026-04-10 から")

    def test_build_member_schedule_rows_marks_busy_overbooked_and_free_days(self):
        with self.app.app_context():
            alice = Member(name="Alice")
            bob = Member(name="Bob")
            db.session.add_all([alice, bob])
            db.session.flush()
            db.session.add_all([
                Task(
                    name="Alice day 1",
                    start_date=date(2026, 4, 2),
                    end_date=date(2026, 4, 3),
                    progress=20,
                    assignee_id=alice.id,
                ),
                Task(
                    name="Alice overlap",
                    start_date=date(2026, 4, 3),
                    end_date=date(2026, 4, 4),
                    progress=0,
                    assignee_id=alice.id,
                ),
            ])
            db.session.commit()

            schedule_days, schedule_rows = app_module.build_member_schedule_rows(
                Member.query.order_by(Member.name).all(),
                Task.query.order_by(Task.id).all(),
                start_date=date(2026, 4, 2),
                days=3,
            )

        self.assertEqual(schedule_days[0], date(2026, 4, 2))
        self.assertEqual(schedule_days[-1], date(2026, 4, 4))
        alice_row = next(row for row in schedule_rows if row["member"].name == "Alice")
        bob_row = next(row for row in schedule_rows if row["member"].name == "Bob")

        self.assertEqual(alice_row["cells"][0]["cell_class"], "schedule-cell-busy")
        self.assertEqual(alice_row["cells"][1]["cell_class"], "schedule-cell-overbooked")
        self.assertEqual(alice_row["cells"][1]["summary_label"], "2件")
        self.assertEqual(alice_row["cells"][2]["task_names"], ["Alice overlap"])
        self.assertEqual(bob_row["cells"][0]["cell_class"], "schedule-cell-free")
        self.assertEqual(bob_row["cells"][0]["summary_label"], "空")

    def test_tasks_page_shows_member_availability_summary(self):
        self.create_user("admin")
        alice_id = self.create_member("Alice")
        self.create_member("Bob")
        today = date.today()
        self.create_task(
            "Assigned task",
            assignee_id=alice_id,
            start_date=today,
            end_date=today + timedelta(days=2),
        )

        self.login_and_open_project()
        response = self.client.get("/tasks")

        self.assertEqual(response.status_code, 200)
        self.assertIn("メンバー空き状況".encode(), response.data)
        self.assertIn("メンバー予定表".encode(), response.data)
        self.assertIn("今日 1 件対応中".encode(), response.data)
        self.assertIn("未割り当てなので、すぐにアサインできます。".encode(), response.data)

    def test_tasks_page_groups_children_under_parent_in_manual_sort(self):
        self.create_user("admin")
        parent_id = self.create_task("Parent task")
        self.create_task("Child task", parent_id=parent_id)

        self.login_and_open_project()
        response = self.client.get("/tasks?sort=manual")

        self.assertEqual(response.status_code, 200)
        parent_pos = response.data.find("Parent task".encode())
        child_pos = response.data.find("Child task".encode())
        self.assertNotEqual(parent_pos, -1)
        self.assertNotEqual(child_pos, -1)
        self.assertLess(parent_pos, child_pos)

    def test_move_task_swaps_sibling_order(self):
        self.create_user("admin")
        first_id = self.create_task("First task")
        second_id = self.create_task("Second task")

        self.login_and_open_project()
        response = self.client.post(
            f"/task/{second_id}/move",
            data={"direction": "up", "next": "/tasks?sort=manual"},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        first_pos = response.data.find("First task".encode())
        second_pos = response.data.find("Second task".encode())
        self.assertNotEqual(first_pos, -1)
        self.assertNotEqual(second_pos, -1)
        self.assertLess(second_pos, first_pos)

        with self.app.app_context():
            first_task = db.session.get(Task, first_id)
            second_task = db.session.get(Task, second_id)
            self.assertLess(second_task.order_index, first_task.order_index)


if __name__ == "__main__":
    unittest.main(verbosity=2)
