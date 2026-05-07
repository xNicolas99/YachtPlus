with open("backend/tests/test_setup.py", "r") as f:
    content = f.read()

# Fix the mock to also return count for User check in bypass_setup
old_mock = """    # Using a fake DB with real query/add/commit mock
    db = MagicMock()
    query_mock = MagicMock()
    # first call returns None, meaning setup not started
    query_mock.first.return_value = None
    db.query.return_value = query_mock"""

new_mock = """    # Using a fake DB with real query/add/commit mock
    db = MagicMock()
    def mock_query(model):
        q = MagicMock()
        if model.__name__ == "User":
            q.count.return_value = 0
        else:
            q.first.return_value = None
        return q
    db.query.side_effect = mock_query"""

content = content.replace(old_mock, new_mock)

with open("backend/tests/test_setup.py", "w") as f:
    f.write(content)
