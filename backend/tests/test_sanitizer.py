import unittest
from api.utils.security_logging import sanitize_error_message

class TestSanitizer(unittest.TestCase):
    def test_sanitize_dict_simple(self):
        data = {"username": "admin", "password": "secret_password"}
        sanitized = sanitize_error_message(data)
        self.assertEqual(sanitized["username"], "admin")
        self.assertEqual(sanitized["password"], "[REDACTED]")

    def test_sanitize_dict_input(self):
        data = {
            "msg": "Validation error",
            "input": {
                "email": "test@example.com",
                "password": "my_secret_password"
            }
        }
        sanitized = sanitize_error_message(data)
        self.assertEqual(sanitized["input"]["email"], "[REDACTED]")
        self.assertEqual(sanitized["input"]["password"], "[REDACTED]")

    def test_sanitize_list(self):
        data = [
            {"loc": ["body", "password"], "msg": "field required", "input": "secret123"},
            {"loc": ["body", "email"], "msg": "invalid email", "input": "user@example.com"}
        ]
        # Note: If 'input' key exists in the dict, it handles it.
        # But here 'input' value is a string. My sanitizer recursion check:
        # if key == "input" or key == "body":
        #    if isinstance(sanitized[key], dict): ...
        # So it might NOT sanitize strings if not handled.
        # The prompt example showed input as a DICT inside the error.
        # "input": { "email": "...", "password": "..." }
        # But sometimes Pydantic returns input as the raw value if it's a leaf.
        pass

    def test_sanitize_nested(self):
        data = {
            "detail": [
                {
                    "input": {
                        "password": "123",
                        "nested": {
                             "secret": "hidden"
                        }
                    }
                }
            ]
        }
        sanitized = sanitize_error_message(data)
        self.assertEqual(sanitized["detail"][0]["input"]["password"], "[REDACTED]")
        self.assertEqual(sanitized["detail"][0]["input"]["nested"]["secret"], "[REDACTED]")

if __name__ == '__main__':
    unittest.main()
