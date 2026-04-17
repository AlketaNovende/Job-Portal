# Testing Report

## 1. Objective

The objective of this project is to apply essential software testing methodologies to a Python web application for managing career opportunity applications. The test effort covers unit, integration, system, and REST API testing, with additional use of mocks and patches to isolate behavior and improve confidence in the application's robustness.

## 2. Application Overview

The application is a Flask-based job portal that supports:

- User registration and login
- Employer job posting
- Worker job search and application submission
- Resume upload for workers
- REST API endpoints for core job and application operations

The project uses Flask, Flask-SQLAlchemy, SQLite, and Python's built-in `unittest` framework.

## 3. Test Scope

The testing scope includes the main business and user flows of the application:

- Validation of helper logic such as allowed resume file types
- Registration and authentication-related behavior
- Employer and worker interaction through the web interface
- Job posting, job browsing, and application creation
- Resume upload behavior
- REST API authorization, validation, success cases, and error handling
- Negative-path testing for invalid input, duplicate submissions, and unauthorized access
- Session-protection checks for protected pages after logout or without authentication

The current scope focuses on functional correctness and route behavior. It does not include performance benchmarking, browser automation with Selenium, or security penetration testing.

## 4. Testing Strategy

### 4.1 Unit Testing

Unit tests focus on isolated functions and small pieces of logic. These tests verify:

- `allowed_file()` for supported and unsupported file extensions
- Job and application serialization helpers
- Password hashing integration during registration using a patched hash function
- Password verification integration during login using a patched checker

Unit tests are intended to confirm correctness of small components without requiring full user flows.

### 4.2 Integration Testing

Integration tests verify how multiple application components work together. These tests cover:

- Posting a job as an employer and applying to it as a worker
- Searching for jobs from the worker dashboard
- Resume upload flow, including secure filename handling and persistence of the stored resume path
- Duplicate-application prevention in the HTML flow
- Dashboard protection for anonymous users
- Employer-only job visibility and worker authorization restrictions
- Duplicate username rejection and invalid resume upload handling

These tests combine routes, session handling, templates, and database interactions.

### 4.3 System Testing

System testing validates the application from an end-user perspective using realistic browser-like flows with Flask's test client. The implemented system test covers:

- Employer registration and login
- Worker registration and login
- Employer job posting
- Worker dashboard access and application submission
- Employer review of submitted applications
- Logout and access revocation for protected pages

This test gives confidence that the major features operate correctly as a connected system.

### 4.4 REST API Testing

REST API testing validates the newly implemented JSON endpoints:

- `GET /api/jobs`
- `POST /api/jobs`
- `POST /api/applications`
- `GET /api/jobs/<job_id>/applications`

The API tests verify:

- Successful JSON responses
- Unauthorized access handling
- Input validation for missing or invalid payload data
- Duplicate-application prevention
- Ownership and access-control enforcement
- Whitespace trimming and session-based ownership assignment
- Missing-resource handling for unknown jobs

## 5. Tools and Frameworks

The following tools and frameworks were selected:

- `unittest`: built-in Python testing framework, appropriate for assignment requirements and simple project setup
- `unittest.mock`: used for mocks and patches to isolate external or side-effect-heavy behavior
- Flask test client: used to simulate requests without launching a live server
- SQLite test database: used to provide isolated test data for each run
- Flask-SQLAlchemy: used by the application and exercised directly in test setup/teardown

### Justification

- `unittest` is stable, widely understood, and requires no additional dependency for the assignment
- `unittest.mock` is suitable for patching hashing and file-save behavior
- Flask's test client allows efficient testing of web routes and API endpoints
- An isolated SQLite database per test run ensures repeatability and prevents pollution of production data

## 6. Test Environment and Design

The test suite is implemented in:

- `tests/test_app.py`

Test isolation is achieved by:

- Creating a temporary directory for every test case
- Using a separate SQLite database file for each test run
- Using a temporary upload directory for resume-related behavior
- Dropping and recreating database tables during setup and teardown

This design ensures tests remain repeatable, independent, and safe to rerun.

## 7. Use of Mocks and Patches

Mocks and patches were used specifically to satisfy the assignment requirement for controlled, isolated testing.
The test file is also fully annotated with comments so each test block clearly states its type and intent.

### 7.1 Password Hashing Patch

The registration test patches `generate_password_hash` so the test can:

- Verify that password hashing is invoked
- Confirm the exact stored value without depending on the real hash output

### 7.2 Password Verification Patch

The login test patches `check_password_hash` so the test can:

- Verify that password verification is invoked with the stored hash and submitted password
- Confirm that successful authentication writes the expected session data

### 7.3 Resume Upload Patches

The resume upload integration test patches:

- `secure_filename`
- `FileStorage.save`

This approach allows the test to:

- Verify that filenames are sanitized
- Confirm file-save behavior is called
- Avoid unnecessary filesystem writes while still validating application logic

## 8. Implemented Test Cases

The suite currently contains 26 tests divided across the required categories.

### Unit Tests

- Validate accepted and rejected file extensions
- Validate job serialization output
- Validate application serialization output
- Validate password hashing behavior during registration
- Validate password verification behavior during login with a patch

### Integration Tests

- Employer posts a job and worker applies successfully
- Worker uploads a resume with patched file handling
- Worker search query filters dashboard results correctly
- Anonymous dashboard access redirects to login
- Employer dashboard shows only the employer's own jobs
- Duplicate applications are prevented in the HTML flow
- Workers cannot use the employer-only job-posting route
- Unsupported resume uploads are rejected
- Duplicate usernames are rejected during registration

### System Tests

- Full end-to-end flow for employer and worker interactions
- Logout removes access to protected pages

### REST API Tests

- List jobs through the API
- Return an empty list when no jobs exist
- Reject unauthorized job creation
- Reject blank job payloads
- Create a job through the API as an employer
- Trim whitespace and assign employer ownership when creating jobs
- Reject application creation requests that omit `job_id`
- Create an application and reject duplicates or missing jobs
- Reject application creation attempts from employer sessions
- Enforce ownership when listing applications for a specific job
- Return 404 when listing applications for a missing job

## 9. Test Execution

The test suite is executed with:

```bash
python -m unittest discover -s tests -v
```

### Result

```text
Ran 26 tests in 15.815s

OK
```

This confirms that all implemented tests passed successfully at the time of execution.

## 10. Challenges and Solutions

### Challenge 1: Missing REST API

The original application did not provide REST API endpoints, even though the assignment explicitly required REST API testing.

Solution:

- Added JSON API endpoints for key job and application operations
- Added validation and authorization behavior to support meaningful API tests

### Challenge 2: Isolating Resume Upload Logic

Direct file uploads can introduce fragile filesystem dependencies during testing.

Solution:

- Used patches for filename sanitization and file saving
- Stored uploads in a temporary test directory

### Challenge 3: Test Isolation

Using the default application database would risk cross-test interference.

Solution:

- Configured a temporary SQLite database for each test case
- Recreated the schema for each run

## 11. Evaluation of Outcomes

The implemented suite demonstrates:

- Coverage across unit, integration, system, and REST API testing
- Proper use of mocks and patches
- Clear organization through reusable test setup
- Validation of both successful and failing scenarios

The test suite gives strong evidence that the application's core flows behave correctly under normal and invalid conditions.

## 12. Limitations and Future Improvements

The following areas could be expanded in future work:

- Add negative tests for HTML form validation edge cases
- Add tests for duplicate username handling in more detail
- Add browser-based UI testing with Selenium or Playwright
- Add coverage measurement with `coverage.py`
- Add CI execution through GitHub Actions
- Add security-oriented tests for session handling and file upload abuse cases

## 13. Conclusion

This project successfully applies the required software testing methodologies to a Flask-based career opportunities portal. The resulting suite verifies isolated logic, interactions between components, complete system workflows, and REST API behavior. The use of mocks and patches improved test reliability and allowed controlled evaluation of sensitive operations such as password hashing and file upload handling.
