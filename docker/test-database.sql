-- Django's test runner creates and drops its own isolated test database.
-- This development-only grant does not allow access to unrelated databases.
GRANT ALL PRIVILEGES ON `test_newsroom`.* TO 'newsroom'@'%';
