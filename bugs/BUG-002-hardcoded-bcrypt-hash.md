# BUG-002: Hardcoded Bcrypt Hash (Dummy Hash)

- **Severity:** Medium
- **Kategorie:** Auth
- **Confidence:** High (statisch erkannt durch Semgrep)
- **Erstmals erkannt in:** api/routers/users.py:128
- **Related Bugs:** none

## 1. Zusammenfassung (2–3 Sätze)
In `api/routers/users.py` wird ein hartkodierter bcrypt-Hash (`DUMMY_HASH`) verwendet. Dies geschieht in der Regel, um Timing-Angriffe auf Login-Formulare zu mildern (indem immer ein Hash verifiziert wird, auch wenn der Benutzer nicht existiert), aber das Hartkodieren des Hashs und ständige Berechnen gegen diesen konstanten Hash kann in manchen Umgebungen erkannt werden und bietet weniger Sicherheit als ein zufällig pro Request generierter Hash.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|-------|----------|-------|
| backend/api/routers/users.py | 128, 200 | Definition des `DUMMY_HASH` |

## 3. Code-Snippet (eingebettet)
```python
// backend/api/routers/users.py:128
        user = crud.get_user_by_name(db, username=form_data.username)
        if not user:
            # Prevent timing attack
            DUMMY_HASH = "$2b$12$EPB.k0Vz4T5lXl6uT9f9/eG0m7b7mG3aR4jPq4s0q3wY0r7U5/7qC"
            verify_password(form_data.password, DUMMY_HASH)
            logger.warning(f"Failed login attempt for nonexistent user: {form_data.username} from {client_ip}")
            record_login_attempt(db, client_ip, form_data.username, False)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
```

## 4. Erwartetes Verhalten
Um Timing-Angriffe abzuwehren, sollte `passlib` so konfiguriert oder verwendet werden, dass es einen zufälligen oder stattdessen generierten Dummy-Hash nutzt, anstatt eine konstante Zeichenfolge im Quellcode zu speichern. Ein konfigurierter Kontext (z. B. `pwd_context.dummy_verify()`) bietet diese Funktion standardmäßig ohne Hardcoding.

## 5. Tatsächliches Verhalten
Der Code verwendet eine hartkodierte Konstante (`DUMMY_HASH = "$2b$12$EPB.k0Vz4T5lXl6uT9f9/eG0m7b7mG3aR4jPq4s0q3wY0r7U5/7qC"`) zur Verifizierung von Passwörtern nicht existierender Benutzer.

## 6. Reproduktion
Schritt-für-Schritt, statisch nachgewiesen durch Semgrep (`generic.secrets.security.detected-bcrypt-hash.detected-bcrypt-hash`).
Die Ausführung erfolgt beim Login-Versuch mit einem ungültigen Benutzernamen.

## 7. Root-Cause-Analyse
Der Versuch, Timing-Attacks zu mitigieren, wurde naiv implementiert, indem ein statischer Hash hartkodiert wurde, anstatt die eingebauten Sicherheitsmechanismen der Hashing-Bibliothek (z. B. `passlib.context.CryptContext.dummy_verify()`) zu verwenden.

## 8. Impact
- **User-Impact:** Keiner direkt für bestehende Benutzer.
- **Daten-Impact:** Keiner.
- **Security-Impact:** Geringfügig geschwächter Schutz gegen fortgeschrittene Timing-Attacks; potenzielle Offenlegung von Implementierungsdetails.

## 9. Fix-Richtung (kein Code, nur Strategie)
Entferne den hartkodierten `DUMMY_HASH`. Nutze stattdessen die `dummy_verify()` Methode der in `passlib` konfigurierten `CryptContext` Instanz, um die konstante Zeit für ungültige Logins zu gewährleisten. Dies ist der empfohlene Weg zur Abwehr von Timing-Angriffen in FastAPI/passlib-Anwendungen.

## 10. Test-Vorschlag
Kein spezifischer Regressionstest nötig für das Hardcoding selbst, aber stelle sicher, dass der bestehende Test, der fehlerhafte Logins (ungültiger Username) abdeckt, weiterhin in etwa derselben Zeit antwortet (Timing-Test) und korrekte 401 Fehler zurückgibt.

## 11. Referenzen
- Verwandte Funktionen/Module im Repo: `backend/api/db/crud/users.py` (wo der pwd_context wahrscheinlich definiert ist)
- Externe Doku falls relevant: https://passlib.readthedocs.io/en/stable/lib/passlib.context.html#passlib.context.CryptContext.dummy_verify

---

## 📋 PROMPT FÜR CLAUDE (copy-paste-bereit)

> Hi Claude, bitte fixe den folgenden Bug. Alle nötigen Infos sind hier — du musst das Repo nicht vorher erkunden, frag nach falls etwas fehlt.
>
> **Bug:** Hardcoded Bcrypt Hash (Dummy Hash)
> **Datei(en):** backend/api/routers/users.py
> **Aktuelles Verhalten:** Ein hartkodierter Bcrypt-Hash wird zur Abwehr von Timing-Attacks genutzt.
> **Erwartetes Verhalten:** Nutzung von `pwd_context.dummy_verify()` statt eines hartkodierten Hashes.
> **Root Cause:** Die manuelle Mitigierung von Timing-Attacks nutzt eine statische Zeichenfolge anstatt der dafür vorgesehenen Bibliotheksfunktion.
> **Vorgeschlagene Fix-Richtung:** Ersetze `verify_password(form_data.password, DUMMY_HASH)` durch einen Aufruf von `dummy_verify()` über den Passlib-Kontext (der wahrscheinlich in `crud.users` oder ähnlich verfügbar ist).
> **Testfall der danach passen muss:** Der Login mit falschem Usernamen muss weiterhin 401 zurückgeben und nicht fehlschlagen.
>
> Aktueller Code:
> ```python
>             # Prevent timing attack
>             DUMMY_HASH = "$2b$12$EPB.k0Vz4T5lXl6uT9f9/eG0m7b7mG3aR4jPq4s0q3wY0r7U5/7qC"
>             verify_password(form_data.password, DUMMY_HASH)
> ```
>
> Bitte:
> 1. Implementiere den Fix mit minimaler Änderung.
> 2. Schreibe den Regressionstest aus §10 (falls sinnvoll).
> 3. Erkläre kurz, warum dein Fix den Root Cause behebt (nicht nur das Symptom).
> 4. Liste Seiteneffekte/Risiken auf, die ich beim Review beachten soll.
