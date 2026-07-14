with open("backend/tests/test_security.py", "r") as f:
    content = f.read()

import re

# In test_check_ip_restriction_public_ip, mock_alert is missing the patch decorator
content = re.sub(r'def test_check_ip_restriction_public_ip\(mock_alert\):', r'@patch("api.utils.security.send_security_alert")\ndef test_check_ip_restriction_public_ip(mock_alert):', content)

with open("backend/tests/test_security.py", "w") as f:
    f.write(content)
