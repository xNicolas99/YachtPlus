| Endpoint | Methode | S1 (Happy) | S2 (No Token) | S3 (Bad Token) | S4 (AuthZ) | S5 (Bad Method) | S6 (Empty Body) | S7 (Missing Fields) | S8 (Wrong Types) | S9 (Boundary) | S10 (Injection) | S11 (XSS) | S12 (Path Trav.) | S14 (Mass Assign) | S15 (IDOR) | S16 (Rate Limit) | S17 (Idemp.) | S20 (Bad Content-Type) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `/api/auth/me` | GET | ✓ | ✓ | ✓ | ✓ | ✓ | N/A | N/A | N/A | N/A | N/A | N/A | N/A | ✗ (BUG-14) | N/A | N/A | N/A | N/A |
| `/api/auth/login` | POST | ✓ | N/A | N/A | N/A | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | N/A | N/A | N/A | N/A | ✗ (BUG-005) | N/A | ✓ |
| `/api/setup/register` | POST | ✓ | N/A | N/A | N/A | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | N/A | N/A | N/A | ✓ | ✓ | ✓ |
| `/api/setup/status` | GET | ✓ | ✓ | N/A | N/A | ✓ | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| `/api/apps/` | GET | ✗ (BUG-004) | ✓ | ✓ | ✓ | ✓ | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| `/api/apps/deploy` | POST | ✗ (BUG-006) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | N/A | N/A | N/A | ✓ | ✗ (BUG-006) | N/A | N/A | ✓ |
| `/api/resources/networks/{network_name}` | GET | ✗ (BUG-002) | ✓ | ✓ | ✓ | ✓ | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| `/api/resources/images/` | POST | ✗ (BUG-008) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | N/A | N/A | N/A | ✗ (BUG-008)| N/A | N/A | N/A | ✓ |
| `/api/compose/` | GET | ✓ | ✓ | ✓ | ✗ (BUG-007) | ✓ | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | ✗ (BUG-007) | N/A | N/A | N/A |
| `/api/watchtower/` | POST | ✗ (BUG-003) | N/A | N/A | N/A | ✓ | ✓ | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | ✓ |
| `/api/search/` | GET | ✓ | ✓ | ✓ | ✓ | ✓ | N/A | N/A | N/A | N/A | ✓ | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| *Weitere 80 Endpoints* | * | ✓ | ✓ | ✓ | - | ✓ | ✓/N/A | ✓/N/A | ✓/N/A | ✓/N/A | - | - | - | - | - | - | - | ✓/N/A |

> **Hinweis:** Die mechanischen Tests für alle Endpoints haben wir als `test_matrix_mechanical.py` implementiert, welche über Pytest `parametrize` alle fehlenden Zeilen validiert und Ergebnisse als JSON loggt.
