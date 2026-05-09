## 2024-05-08 - [Handle Deleted User in Auth Checks]
Bug/Gap: Routes crashed with 500 errors when accessed with a valid JWT token for a user that was subsequently deleted from the database.
Root Cause: `get_user_by_name()` returns `None` for deleted users, and the subsequent `if not user.is_superuser:` check threw an `AttributeError`.
Prevention: Always check if the user object returned from the database is `None` before attempting to access its properties, even if the JWT token is valid.

## 2024-05-08 - [Handle DB Integrity Errors Gracefully]
Bug/Gap: Updating a user's name to an already existing name crashed the server with an unhandled 500 error.
Root Cause: Changing a field with a `UNIQUE` constraint raises a raw SQLAlchemy `IntegrityError` during `db.commit()` if the constraint is violated, which was not caught.
Prevention: Wrap `db.commit()` in a `try/except` block, and perform a `db.rollback()` and raise a clear 400 API error if it fails to prevent crashing the server.

## 2024-05-08 - [Handle Empty YAML Parse Returns]
Bug/Gap: Fetching an empty `docker-compose.yml` file caused a 500 error.
Root Cause: `yaml.load()` returns `None` for empty files instead of an empty dictionary. The subsequent code called `.get()` directly on the result, causing an `AttributeError: 'NoneType' object has no attribute 'get'`.
Prevention: Ensure that the result of `yaml.load()` is truthy before accessing it like a dictionary.
