import io
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash

import app as job_portal_app
from app import app, db, allowed_file, serialize_application, serialize_job
from models import Application, Job, User


# Shared test fixture: create an isolated database and upload folder for every test.
class BaseTestCase(unittest.TestCase):
    # Shared setup: create a temporary workspace so every test starts clean.
    def setUp(self):
        # Shared setup purpose: create a temporary root folder for the current test.
        self.temp_dir = tempfile.mkdtemp(prefix="job-portal-tests-")
        # Shared setup purpose: point the test database to a disposable SQLite file.
        self.db_path = os.path.join(self.temp_dir, "test.db")
        # Shared setup purpose: point uploads to a disposable folder.
        self.upload_dir = os.path.join(self.temp_dir, "uploads")
        # Shared setup purpose: make sure the temporary upload folder exists.
        os.makedirs(self.upload_dir, exist_ok=True)

        # Shared setup purpose: switch Flask into testing mode with isolated resources.
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret-key",
            SQLALCHEMY_DATABASE_URI=f"sqlite:///{self.db_path}",
            UPLOAD_FOLDER=self.upload_dir,
        )

        # Shared setup purpose: create a reusable HTTP client for the current test.
        self.client = app.test_client()
        # Shared setup purpose: rebuild the schema so the database is empty.
        with app.app_context():
            # Shared setup purpose: clear any previous SQLAlchemy session state.
            db.session.remove()
            # Shared setup purpose: drop stale tables if they exist.
            db.drop_all()
            # Shared setup purpose: create a fresh schema for this test only.
            db.create_all()

    # Shared teardown: remove the database and files created during the test.
    def tearDown(self):
        # Shared teardown purpose: release open SQLAlchemy state before cleanup.
        with app.app_context():
            # Shared teardown purpose: clear the active SQLAlchemy session.
            db.session.remove()
            # Shared teardown purpose: drop all tables created for the test.
            db.drop_all()
            # Shared teardown purpose: dispose the SQLite engine connection.
            db.engine.dispose()
        # Shared teardown purpose: delete the temporary workspace from disk.
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # Shared helper: create a user record directly in the test database.
    def create_user(self, username, role, password="password123"):
        # Shared helper purpose: insert a user with a hashed password.
        with app.app_context():
            # Shared helper purpose: build a new user model instance.
            user = User(
                username=username,
                password=generate_password_hash(password),
                role=role,
            )
            # Shared helper purpose: stage the user for insertion.
            db.session.add(user)
            # Shared helper purpose: commit so the user gets a real primary key.
            db.session.commit()
            # Shared helper purpose: return the generated user ID for later use.
            return user.id

    # Shared helper: create a job record directly in the test database.
    def create_job(self, title, description, employer_id):
        # Shared helper purpose: insert a job owned by the specified employer.
        with app.app_context():
            # Shared helper purpose: build a new job model instance.
            job = Job(title=title, description=description, employer_id=employer_id)
            # Shared helper purpose: stage the job for insertion.
            db.session.add(job)
            # Shared helper purpose: commit so the job gets a real primary key.
            db.session.commit()
            # Shared helper purpose: return the generated job ID for later use.
            return job.id

    # Shared helper: simulate a logged-in user by writing directly to the session.
    def login_session(self, client, user_id, role):
        # Shared helper purpose: open the session for the provided test client.
        with client.session_transaction() as session:
            # Shared helper purpose: mark the current user as authenticated.
            session["user_id"] = user_id
            # Shared helper purpose: attach the current user's role for route checks.
            session["role"] = role


# Unit tests: verify isolated helpers and patched dependencies without full user flows.
class UnitTests(BaseTestCase):
    # Unit Test: verify that allowed_file accepts valid extensions and rejects invalid ones.
    def test_allowed_file_accepts_supported_extensions(self):
        # Unit Test step: confirm that PDF resumes are allowed.
        self.assertTrue(allowed_file("resume.pdf"))
        # Unit Test step: confirm that extension checks are case-insensitive.
        self.assertTrue(allowed_file("portfolio.DOCX"))
        # Unit Test step: confirm that unsupported extensions are rejected.
        self.assertFalse(allowed_file("notes.txt"))
        # Unit Test step: confirm that filenames without an extension are rejected.
        self.assertFalse(allowed_file("resume"))

    # Unit Test: verify that serializer helpers return the expected dictionary shapes.
    def test_serialize_helpers_return_expected_fields(self):
        # Unit Test step: create in-memory model objects to serialize.
        with app.app_context():
            # Unit Test step: build a sample job object with known values.
            job = Job(id=7, title="QA Engineer", description="Write tests", employer_id=3)
            # Unit Test step: build a sample application object with known values.
            application = Application(id=9, worker_id=4, job_id=7)

        # Unit Test step: assert that the job serializer returns the correct payload.
        self.assertEqual(
            serialize_job(job),
            {"id": 7, "title": "QA Engineer", "description": "Write tests", "employer_id": 3},
        )
        # Unit Test step: assert that the application serializer returns the correct payload.
        self.assertEqual(
            serialize_application(application),
            {"id": 9, "worker_id": 4, "job_id": 7},
        )

    # Unit Test with patching: verify that registration calls the hashing function once.
    def test_register_uses_password_hasher_patch(self):
        # Unit Test step: replace the real hasher so the test can inspect the exact call.
        with patch.object(job_portal_app, "generate_password_hash", return_value="patched-hash") as mock_hash:
            # Unit Test step: submit a registration request with a plain-text password.
            response = self.client.post(
                "/register",
                data={"role": "worker", "username": "amira", "password": "plain-pass"},
                follow_redirects=False,
            )

        # Unit Test step: verify that successful registration redirects to login.
        self.assertEqual(response.status_code, 302)
        # Unit Test step: verify that the patched hash function received the plain password.
        mock_hash.assert_called_once_with("plain-pass")
        # Unit Test step: verify that the patched hash value was stored in the database.
        with app.app_context():
            # Unit Test step: load the newly created user from the database.
            user = User.query.filter_by(username="amira").first()
            # Unit Test step: confirm that the user was actually created.
            self.assertIsNotNone(user)
            # Unit Test step: confirm that the stored password matches the patched value.
            self.assertEqual(user.password, "patched-hash")

    # Unit Test with patching: verify that login uses the password-check function and sets the session.
    def test_login_uses_password_checker_patch(self):
        # Unit Test step: create a user with a deterministic stored hash value.
        with app.app_context():
            # Unit Test step: build the user record that the login route will load.
            user = User(username="login-user", password="stored-hash", role="worker")
            # Unit Test step: stage the user record for insertion.
            db.session.add(user)
            # Unit Test step: commit so the user gets a real ID.
            db.session.commit()
            # Unit Test step: remember the new user ID for later session assertions.
            user_id = user.id

        # Unit Test step: patch password verification so the route logic can be observed directly.
        with patch.object(job_portal_app, "check_password_hash", return_value=True) as mock_check:
            # Unit Test step: submit a login request with a known password.
            response = self.client.post(
                "/login",
                data={"username": "login-user", "password": "plain-pass"},
                follow_redirects=False,
            )

        # Unit Test step: verify that successful login redirects to the dashboard.
        self.assertEqual(response.status_code, 302)
        # Unit Test step: verify that the password checker was called with stored and submitted values.
        mock_check.assert_called_once_with("stored-hash", "plain-pass")
        # Unit Test step: inspect the Flask session to confirm that authentication state was written.
        with self.client.session_transaction() as session:
            # Unit Test step: confirm that the correct user ID was stored in the session.
            self.assertEqual(session["user_id"], user_id)
            # Unit Test step: confirm that the correct role was stored in the session.
            self.assertEqual(session["role"], "worker")


# Integration tests: verify routes, templates, session state, and database behavior together.
class IntegrationTests(BaseTestCase):
    # Integration Test: verify that an employer can post a job and a worker can apply for it.
    def test_employer_can_post_job_and_worker_can_apply(self):
        # Integration Test step: create one employer and one worker in the test database.
        employer_id = self.create_user("employer1", "employer")
        worker_id = self.create_user("worker1", "worker")

        # Integration Test step: open a separate client for the employer flow.
        employer_client = app.test_client()
        # Integration Test step: mark the employer client as logged in.
        self.login_session(employer_client, employer_id, "employer")
        # Integration Test step: submit a new job through the employer route.
        post_response = employer_client.post(
            "/post_job",
            data={"title": "SDET", "description": "Automation and API testing"},
            follow_redirects=False,
        )

        # Integration Test step: verify that posting redirects back to the dashboard.
        self.assertEqual(post_response.status_code, 302)
        # Integration Test step: load the posted job from the database.
        with app.app_context():
            # Integration Test step: query the job by title so the worker can apply to it.
            job = Job.query.filter_by(title="SDET").first()
            # Integration Test step: confirm that the job was persisted.
            self.assertIsNotNone(job)
            # Integration Test step: remember the generated job ID for the apply route.
            job_id = job.id

        # Integration Test step: open a separate client for the worker flow.
        worker_client = app.test_client()
        # Integration Test step: mark the worker client as logged in.
        self.login_session(worker_client, worker_id, "worker")
        # Integration Test step: submit an application through the worker route.
        apply_response = worker_client.get(f"/apply/{job_id}", follow_redirects=False)
        # Integration Test step: verify that applying redirects back to the dashboard.
        self.assertEqual(apply_response.status_code, 302)

        # Integration Test step: load the new application from the database.
        with app.app_context():
            # Integration Test step: query the application created by the worker.
            application = Application.query.filter_by(worker_id=worker_id, job_id=job_id).first()
            # Integration Test step: confirm that the application was persisted.
            self.assertIsNotNone(application)

    # Integration Test with patching: verify resume upload wiring without writing a real file.
    def test_worker_resume_upload_uses_secure_filename_and_save_patch(self):
        # Integration Test step: create a worker who is allowed to upload a resume.
        worker_id = self.create_user("worker-upload", "worker")
        # Integration Test step: mark the shared client as logged in as that worker.
        self.login_session(self.client, worker_id, "worker")

        # Integration Test step: patch filename sanitization to keep the saved path deterministic.
        with patch.object(job_portal_app, "secure_filename", return_value="safe_resume.pdf") as mock_secure:
            # Integration Test step: patch file saving so the test stays fast and isolated.
            with patch("werkzeug.datastructures.FileStorage.save") as mock_save:
                # Integration Test step: submit a multipart resume upload request.
                response = self.client.post(
                    "/upload_resume",
                    data={"resume": (io.BytesIO(b"pdf-bytes"), "resume.pdf")},
                    content_type="multipart/form-data",
                    follow_redirects=False,
                )

        # Integration Test step: verify that successful upload redirects to the dashboard.
        self.assertEqual(response.status_code, 302)
        # Integration Test step: confirm that the filename sanitizer was called with the original name.
        mock_secure.assert_called_once_with("resume.pdf")
        # Integration Test step: confirm that the file save method was invoked.
        mock_save.assert_called_once()
        # Integration Test step: load the worker to confirm the stored resume path.
        with app.app_context():
            # Integration Test step: retrieve the worker record after upload.
            user = db.session.get(User, worker_id)
            # Integration Test step: verify that the saved resume path matches the patched filename.
            self.assertEqual(user.resume, os.path.join(self.upload_dir, f"{worker_id}_safe_resume.pdf"))

    # Integration Test: verify that worker search filters dashboard results by query text.
    def test_worker_search_filters_dashboard_results(self):
        # Integration Test step: create an employer who owns the jobs.
        employer_id = self.create_user("employer2", "employer")
        # Integration Test step: create a worker who will search the dashboard.
        worker_id = self.create_user("worker2", "worker")
        # Integration Test step: insert a matching job into the database.
        self.create_job("Backend QA", "API regression suite", employer_id)
        # Integration Test step: insert a non-matching job into the database.
        self.create_job("Frontend Developer", "React user interface work", employer_id)

        # Integration Test step: mark the shared client as the logged-in worker.
        self.login_session(self.client, worker_id, "worker")
        # Integration Test step: request the dashboard with a search term.
        response = self.client.get("/dashboard?q=backend")

        # Integration Test step: convert the HTML response to text for content assertions.
        body = response.get_data(as_text=True)
        # Integration Test step: verify that the dashboard was rendered successfully.
        self.assertEqual(response.status_code, 200)
        # Integration Test step: verify that the matching job appears in the results.
        self.assertIn("Backend QA", body)
        # Integration Test step: verify that the non-matching job is excluded from the results.
        self.assertNotIn("Frontend Developer", body)

    # Integration Test: verify that anonymous users are redirected away from the dashboard.
    def test_dashboard_redirects_anonymous_user_to_login(self):
        # Integration Test step: request the dashboard without logging in first.
        response = self.client.get("/dashboard", follow_redirects=False)
        # Integration Test step: confirm that anonymous access is redirected.
        self.assertEqual(response.status_code, 302)
        # Integration Test step: confirm that the redirect target is the login page.
        self.assertTrue(response.headers["Location"].endswith("/login"))

    # Integration Test: verify that an employer sees only their own jobs on the dashboard.
    def test_employer_dashboard_only_lists_own_jobs(self):
        # Integration Test step: create two employers with separate job ownership.
        employer_id = self.create_user("owner-employer", "employer")
        other_employer_id = self.create_user("other-employer", "employer")
        # Integration Test step: create a job owned by the logged-in employer.
        self.create_job("Owned Role", "Visible to the owner", employer_id)
        # Integration Test step: create a job owned by a different employer.
        self.create_job("Other Role", "Should not appear here", other_employer_id)

        # Integration Test step: mark the shared client as the first employer.
        self.login_session(self.client, employer_id, "employer")
        # Integration Test step: request the employer dashboard.
        response = self.client.get("/dashboard")

        # Integration Test step: convert the rendered page into text for assertions.
        body = response.get_data(as_text=True)
        # Integration Test step: verify that the dashboard renders successfully.
        self.assertEqual(response.status_code, 200)
        # Integration Test step: verify that the employer's own job is displayed.
        self.assertIn("Owned Role", body)
        # Integration Test step: verify that another employer's job is hidden.
        self.assertNotIn("Other Role", body)

    # Integration Test: verify that the HTML apply route prevents duplicate applications.
    def test_duplicate_application_is_not_created_in_html_flow(self):
        # Integration Test step: create one employer and one worker.
        employer_id = self.create_user("dup-owner", "employer")
        worker_id = self.create_user("dup-worker", "worker")
        # Integration Test step: create a job that the worker can apply to.
        job_id = self.create_job("Manual Tester", "Exploratory testing", employer_id)

        # Integration Test step: mark the shared client as the worker.
        self.login_session(self.client, worker_id, "worker")
        # Integration Test step: send the first application request.
        first_response = self.client.get(f"/apply/{job_id}", follow_redirects=False)
        # Integration Test step: send the same application request a second time.
        second_response = self.client.get(f"/apply/{job_id}", follow_redirects=False)

        # Integration Test step: verify that both route calls complete with redirects.
        self.assertEqual(first_response.status_code, 302)
        # Integration Test step: verify that the second call also returns cleanly.
        self.assertEqual(second_response.status_code, 302)
        # Integration Test step: verify that only one application exists in the database.
        with app.app_context():
            # Integration Test step: count how many applications were stored for this worker/job pair.
            application_count = Application.query.filter_by(worker_id=worker_id, job_id=job_id).count()
            # Integration Test step: confirm that the route did not create duplicates.
            self.assertEqual(application_count, 1)

    # Integration Test: verify that workers cannot use the employer-only job posting route.
    def test_worker_cannot_post_job_through_employer_route(self):
        # Integration Test step: create a worker account with no employer privileges.
        worker_id = self.create_user("blocked-worker", "worker")
        # Integration Test step: mark the shared client as that worker.
        self.login_session(self.client, worker_id, "worker")

        # Integration Test step: try to post a job through the employer-only endpoint.
        response = self.client.post(
            "/post_job",
            data={"title": "Invalid Post", "description": "Workers should not create jobs"},
            follow_redirects=False,
        )

        # Integration Test step: confirm that the route redirects instead of creating a job.
        self.assertEqual(response.status_code, 302)
        # Integration Test step: confirm that the worker is redirected to login.
        self.assertTrue(response.headers["Location"].endswith("/login"))
        # Integration Test step: confirm that no job was inserted into the database.
        with app.app_context():
            # Integration Test step: count all jobs after the unauthorized request.
            self.assertEqual(Job.query.count(), 0)

    # Integration Test: verify that unsupported resume formats are rejected cleanly.
    def test_upload_resume_rejects_unsupported_file_format(self):
        # Integration Test step: create a worker who will attempt the invalid upload.
        worker_id = self.create_user("worker-invalid-upload", "worker")
        # Integration Test step: mark the shared client as that worker.
        self.login_session(self.client, worker_id, "worker")

        # Integration Test step: submit a text file instead of a supported resume file.
        response = self.client.post(
            "/upload_resume",
            data={"resume": (io.BytesIO(b"text-bytes"), "notes.txt")},
            content_type="multipart/form-data",
            follow_redirects=False,
        )

        # Integration Test step: verify that the route rejects the upload with an explanatory message.
        self.assertEqual(response.status_code, 200)
        # Integration Test step: verify that the response body mentions the unsupported format.
        self.assertIn("Unsupported file format", response.get_data(as_text=True))
        # Integration Test step: verify that no resume path was stored for the worker.
        with app.app_context():
            # Integration Test step: load the worker after the invalid upload attempt.
            user = db.session.get(User, worker_id)
            # Integration Test step: confirm that the resume field was left empty.
            self.assertIsNone(user.resume)

    # Integration Test: verify that duplicate usernames are blocked at registration time.
    def test_register_rejects_duplicate_username(self):
        # Integration Test step: create the original user in the database.
        self.create_user("duplicate-user", "worker")

        # Integration Test step: submit a second registration with the same username.
        response = self.client.post(
            "/register",
            data={"role": "worker", "username": "duplicate-user", "password": "new-pass"},
            follow_redirects=False,
        )

        # Integration Test step: verify that the route responds without redirecting.
        self.assertEqual(response.status_code, 200)
        # Integration Test step: verify that the duplicate-user message is shown.
        self.assertIn("The user already exists", response.get_data(as_text=True))
        # Integration Test step: verify that only one user record remains in the database.
        with app.app_context():
            # Integration Test step: count users with the duplicated username.
            duplicate_count = User.query.filter_by(username="duplicate-user").count()
            # Integration Test step: confirm that no duplicate record was created.
            self.assertEqual(duplicate_count, 1)


# System tests: verify realistic end-to-end flows across multiple routes and roles.
class SystemTests(BaseTestCase):
    # System Test: verify the full employer-to-worker browser-like flow from registration to review.
    def test_full_browser_flow_for_employer_and_worker(self):
        # System Test step: register an employer through the public registration route.
        register_employer = self.client.post(
            "/register",
            data={"role": "employer", "username": "manager", "password": "secret123"},
            follow_redirects=False,
        )
        # System Test step: confirm that employer registration succeeds.
        self.assertEqual(register_employer.status_code, 302)

        # System Test step: register a worker through the public registration route.
        register_worker = self.client.post(
            "/register",
            data={"role": "worker", "username": "candidate", "password": "secret123"},
            follow_redirects=False,
        )
        # System Test step: confirm that worker registration succeeds.
        self.assertEqual(register_worker.status_code, 302)

        # System Test step: open a fresh browser-like client for the employer.
        employer_client = app.test_client()
        # System Test step: log the employer into the application.
        login_employer = employer_client.post(
            "/login",
            data={"username": "manager", "password": "secret123"},
            follow_redirects=False,
        )
        # System Test step: confirm that the employer reaches the dashboard flow.
        self.assertEqual(login_employer.status_code, 302)
        # System Test step: post a job as the logged-in employer.
        employer_client.post(
            "/post_job",
            data={"title": "Test Analyst", "description": "Create and maintain test plans"},
            follow_redirects=False,
        )

        # System Test step: load the posted job from the database so the worker can apply to it.
        with app.app_context():
            # System Test step: query the job created through the UI flow.
            job = Job.query.filter_by(title="Test Analyst").first()
            # System Test step: confirm that the job exists after posting.
            self.assertIsNotNone(job)
            # System Test step: remember the job ID for the worker application step.
            job_id = job.id

        # System Test step: open a fresh browser-like client for the worker.
        worker_client = app.test_client()
        # System Test step: log the worker into the application.
        login_worker = worker_client.post(
            "/login",
            data={"username": "candidate", "password": "secret123"},
            follow_redirects=False,
        )
        # System Test step: confirm that the worker login succeeds.
        self.assertEqual(login_worker.status_code, 302)

        # System Test step: load the worker dashboard to confirm the job is visible.
        dashboard_response = worker_client.get("/dashboard")
        # System Test step: confirm that the posted job appears in the worker view.
        self.assertIn("Test Analyst", dashboard_response.get_data(as_text=True))

        # System Test step: apply to the job through the worker flow.
        worker_client.get(f"/apply/{job_id}", follow_redirects=False)
        # System Test step: load the employer's application-review page.
        applications_response = employer_client.get(f"/applications/{job_id}")
        # System Test step: capture the rendered HTML for assertions.
        body = applications_response.get_data(as_text=True)

        # System Test step: confirm that the employer can open the applications page.
        self.assertEqual(applications_response.status_code, 200)
        # System Test step: confirm that the submitted application is rendered on the page.
        self.assertIn("Candidate ID", body)

    # System Test: verify that logout removes access to protected pages.
    def test_logout_revokes_dashboard_access(self):
        # System Test step: register a worker through the public route.
        register_response = self.client.post(
            "/register",
            data={"role": "worker", "username": "logout-user", "password": "secret123"},
            follow_redirects=False,
        )
        # System Test step: confirm that registration succeeds.
        self.assertEqual(register_response.status_code, 302)

        # System Test step: log the same worker into the application.
        login_response = self.client.post(
            "/login",
            data={"username": "logout-user", "password": "secret123"},
            follow_redirects=False,
        )
        # System Test step: confirm that login succeeds before logout is tested.
        self.assertEqual(login_response.status_code, 302)

        # System Test step: perform the logout action through the public route.
        logout_response = self.client.get("/logout", follow_redirects=False)
        # System Test step: confirm that logout redirects to the home page.
        self.assertEqual(logout_response.status_code, 302)

        # System Test step: try to revisit the protected dashboard after logout.
        dashboard_response = self.client.get("/dashboard", follow_redirects=False)
        # System Test step: confirm that the logged-out user is redirected to login.
        self.assertEqual(dashboard_response.status_code, 302)
        # System Test step: confirm that the redirect target is the login page.
        self.assertTrue(dashboard_response.headers["Location"].endswith("/login"))


# REST API tests: verify JSON endpoints, authorization, validation, and edge cases.
class RestApiTests(BaseTestCase):
    # REST API Test: verify that listing jobs returns JSON data for existing jobs.
    def test_api_lists_jobs(self):
        # REST API Test step: create an employer who owns the API-visible job.
        employer_id = self.create_user("api-employer", "employer")
        # REST API Test step: create a job that should appear in the JSON response.
        self.create_job("Automation Engineer", "Own REST checks", employer_id)

        # REST API Test step: request the job listing endpoint.
        response = self.client.get("/api/jobs")
        # REST API Test step: parse the JSON payload.
        payload = response.get_json()

        # REST API Test step: confirm that the endpoint responds successfully.
        self.assertEqual(response.status_code, 200)
        # REST API Test step: confirm that exactly one job is returned.
        self.assertEqual(len(payload), 1)
        # REST API Test step: confirm that the returned job title matches the inserted data.
        self.assertEqual(payload[0]["title"], "Automation Engineer")

    # REST API Test: verify that listing jobs returns an empty JSON array when no jobs exist.
    def test_api_lists_jobs_returns_empty_array_when_no_jobs(self):
        # REST API Test step: request the job listing endpoint against an empty database.
        response = self.client.get("/api/jobs")
        # REST API Test step: parse the JSON payload from the empty response.
        payload = response.get_json()

        # REST API Test step: confirm that the endpoint still responds successfully.
        self.assertEqual(response.status_code, 200)
        # REST API Test step: confirm that the JSON body is an empty list.
        self.assertEqual(payload, [])

    # REST API Test: verify that only authenticated employers can create jobs.
    def test_api_create_job_requires_employer_session(self):
        # REST API Test step: try to create a job without logging in first.
        response = self.client.post("/api/jobs", json={"title": "QA", "description": "Test all features"})
        # REST API Test step: confirm that the endpoint rejects the request as unauthorized.
        self.assertEqual(response.status_code, 401)
        # REST API Test step: confirm that the JSON error message is explicit.
        self.assertEqual(response.get_json()["error"], "Unauthorized")

    # REST API Test: verify that blank titles and descriptions are rejected after trimming.
    def test_api_create_job_rejects_blank_payload(self):
        # REST API Test step: create an employer with permission to call the endpoint.
        employer_id = self.create_user("blank-api-owner", "employer")
        # REST API Test step: mark the shared client as that employer.
        self.login_session(self.client, employer_id, "employer")

        # REST API Test step: submit whitespace-only fields to the create-job endpoint.
        response = self.client.post(
            "/api/jobs",
            json={"title": "   ", "description": "   "},
        )

        # REST API Test step: confirm that validation rejects the blank payload.
        self.assertEqual(response.status_code, 400)
        # REST API Test step: confirm that the JSON error explains the validation rule.
        self.assertEqual(response.get_json()["error"], "Title and description are required")

    # REST API Test: verify that valid employer requests create a job and return HTTP 201.
    def test_api_create_job_returns_201_for_employer(self):
        # REST API Test step: create an employer who is allowed to create jobs.
        employer_id = self.create_user("api-manager", "employer")
        # REST API Test step: mark the shared client as the logged-in employer.
        self.login_session(self.client, employer_id, "employer")

        # REST API Test step: submit a valid JSON payload to create a job.
        response = self.client.post(
            "/api/jobs",
            json={"title": "QA Lead", "description": "Lead testing efforts"},
        )

        # REST API Test step: confirm that the job was created successfully.
        self.assertEqual(response.status_code, 201)
        # REST API Test step: confirm that the response payload contains the created title.
        self.assertEqual(response.get_json()["title"], "QA Lead")
        # REST API Test step: confirm that exactly one job exists in the database.
        with app.app_context():
            # REST API Test step: count persisted jobs after the request.
            self.assertEqual(Job.query.count(), 1)

    # REST API Test: verify that whitespace is trimmed and ownership is assigned from the session.
    def test_api_create_job_trims_whitespace_and_assigns_owner(self):
        # REST API Test step: create an employer who will own the new job.
        employer_id = self.create_user("trim-owner", "employer")
        # REST API Test step: mark the shared client as that employer.
        self.login_session(self.client, employer_id, "employer")

        # REST API Test step: submit a payload with extra whitespace around the fields.
        response = self.client.post(
            "/api/jobs",
            json={"title": "  QA Architect  ", "description": "  Design test strategy  "},
        )
        # REST API Test step: parse the JSON payload returned by the endpoint.
        payload = response.get_json()

        # REST API Test step: confirm that the endpoint created the job successfully.
        self.assertEqual(response.status_code, 201)
        # REST API Test step: confirm that the API trimmed the title before storing it.
        self.assertEqual(payload["title"], "QA Architect")
        # REST API Test step: confirm that the API trimmed the description before storing it.
        self.assertEqual(payload["description"], "Design test strategy")
        # REST API Test step: confirm that the API assigned the current employer as the owner.
        self.assertEqual(payload["employer_id"], employer_id)

    # REST API Test: verify that the applications endpoint requires a job_id payload.
    def test_api_create_application_requires_job_id(self):
        # REST API Test step: create a worker who is allowed to apply through the API.
        worker_id = self.create_user("api-worker-missing-job", "worker")
        # REST API Test step: mark the shared client as that worker.
        self.login_session(self.client, worker_id, "worker")

        # REST API Test step: call the applications endpoint without the required job_id field.
        response = self.client.post("/api/applications", json={})

        # REST API Test step: confirm that validation rejects the request.
        self.assertEqual(response.status_code, 400)
        # REST API Test step: confirm that the JSON error explains the missing field.
        self.assertEqual(response.get_json()["error"], "job_id is required")

    # REST API Test: verify that the applications endpoint creates records and blocks duplicates/missing jobs.
    def test_api_create_application_validates_job_and_prevents_duplicates(self):
        # REST API Test step: create the employer who owns the job.
        employer_id = self.create_user("owner", "employer")
        # REST API Test step: create the worker who will submit the application.
        worker_id = self.create_user("api-worker", "worker")
        # REST API Test step: create the job that the worker will apply to.
        job_id = self.create_job("Performance Tester", "Load testing", employer_id)
        # REST API Test step: mark the shared client as the worker.
        self.login_session(self.client, worker_id, "worker")

        # REST API Test step: submit the first valid application request.
        created = self.client.post("/api/applications", json={"job_id": job_id})
        # REST API Test step: submit the same request again to trigger duplicate protection.
        duplicate = self.client.post("/api/applications", json={"job_id": job_id})
        # REST API Test step: submit a request for a job that does not exist.
        missing = self.client.post("/api/applications", json={"job_id": 9999})

        # REST API Test step: confirm that the first application is created successfully.
        self.assertEqual(created.status_code, 201)
        # REST API Test step: confirm that the duplicate request is rejected.
        self.assertEqual(duplicate.status_code, 409)
        # REST API Test step: confirm that the missing-job request is rejected.
        self.assertEqual(missing.status_code, 404)

    # REST API Test: verify that employers cannot use the worker-only application endpoint.
    def test_api_create_application_rejects_employer_session(self):
        # REST API Test step: create an employer account with the wrong role for this endpoint.
        employer_id = self.create_user("api-employer-blocked", "employer")
        # REST API Test step: mark the shared client as that employer.
        self.login_session(self.client, employer_id, "employer")

        # REST API Test step: try to submit an application while logged in as an employer.
        response = self.client.post("/api/applications", json={"job_id": 1})

        # REST API Test step: confirm that the endpoint rejects the wrong role.
        self.assertEqual(response.status_code, 401)
        # REST API Test step: confirm that the JSON error indicates unauthorized access.
        self.assertEqual(response.get_json()["error"], "Unauthorized")

    # REST API Test: verify that employers can read their own applications but not someone else's.
    def test_api_job_applications_enforces_ownership(self):
        # REST API Test step: create the job owner employer.
        owner_id = self.create_user("owner-2", "employer")
        # REST API Test step: create a second employer who does not own the job.
        outsider_id = self.create_user("outsider", "employer")
        # REST API Test step: create a worker who will appear in the applications list.
        worker_id = self.create_user("worker-3", "worker")
        # REST API Test step: create the protected job owned by the first employer.
        job_id = self.create_job("Security Tester", "Threat modeling", owner_id)
        # REST API Test step: insert an application for the protected job.
        with app.app_context():
            # REST API Test step: build the application that the owner should be allowed to see.
            application = Application(worker_id=worker_id, job_id=job_id)
            # REST API Test step: stage the application for insertion.
            db.session.add(application)
            # REST API Test step: commit the application so it exists for both requests.
            db.session.commit()

        # REST API Test step: open a dedicated client for the job owner.
        owner_client = app.test_client()
        # REST API Test step: mark the owner client as authenticated.
        self.login_session(owner_client, owner_id, "employer")
        # REST API Test step: request the applications list as the rightful owner.
        owner_response = owner_client.get(f"/api/jobs/{job_id}/applications")

        # REST API Test step: open a dedicated client for the outsider employer.
        outsider_client = app.test_client()
        # REST API Test step: mark the outsider client as authenticated.
        self.login_session(outsider_client, outsider_id, "employer")
        # REST API Test step: request the same applications list as a non-owner.
        outsider_response = outsider_client.get(f"/api/jobs/{job_id}/applications")

        # REST API Test step: confirm that the owner can see the applications.
        self.assertEqual(owner_response.status_code, 200)
        # REST API Test step: confirm that the owner receives the single stored application.
        self.assertEqual(len(owner_response.get_json()), 1)
        # REST API Test step: confirm that the outsider is forbidden from reading the data.
        self.assertEqual(outsider_response.status_code, 403)

    # REST API Test: verify that the applications-list endpoint returns 404 for unknown jobs.
    def test_api_job_applications_returns_404_for_missing_job(self):
        # REST API Test step: create an employer who is allowed to call the endpoint.
        employer_id = self.create_user("api-missing-job-owner", "employer")
        # REST API Test step: mark the shared client as that employer.
        self.login_session(self.client, employer_id, "employer")

        # REST API Test step: request applications for a job ID that does not exist.
        response = self.client.get("/api/jobs/9999/applications")

        # REST API Test step: confirm that the endpoint reports the missing job correctly.
        self.assertEqual(response.status_code, 404)
        # REST API Test step: confirm that the JSON error message is explicit.
        self.assertEqual(response.get_json()["error"], "Job not found")


# Standard unittest entry point: allow direct execution of this test module.
if __name__ == "__main__":
    # Standard unittest entry point purpose: run the full suite with verbose output.
    unittest.main(verbosity=2)
