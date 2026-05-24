# BUG-002: AttributeError in get_network due to wrong aiodocker method

- **Severity:** High
- **Kategorie:** ResourceLeak / Other
- **Confidence:** High
- **Sweep-Quelle:** B2-S5 (Mechanical Sweep)
- **Erstmals erkannt in:** `backend/api/actions/resources.py:345`
- **Related Bugs:** none

## 1. Zusammenfassung
Der Endpunkt `/api/resources/networks/{network_name}` schlägt immer mit einem 500 Internal Server Error fehl. Dies liegt daran, dass der Code `docker.networks.inspect(network_id)` aufruft, aber das `DockerNetworks` Objekt aus der `aiodocker` Bibliothek diese Methode nicht besitzt. Die korrekte Methode in `aiodocker` lautet `docker.networks.get(network_id)`.

## 2. Betroffene Stellen
| Datei | Zeile(n) | Rolle |
|---|---|---|
| `backend/api/actions/resources.py` | 345 | Fehlerhafter Aufruf von `docker.networks.inspect` |

## 3. Code-Snippet
```python
# backend/api/actions/resources.py
async def get_network(network_id):
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        containers_task = docker.containers.list(all=True)
        network_task = docker.networks.inspect(network_id)  # <--- HIER
        ...
```

## 4. Erwartetes Verhalten
Die Methode gibt die Details zum Docker-Netzwerk als JSON zurück, indem sie den aiodocker SDK korrekt verwendet.

## 5. Tatsächliches Verhalten
```python
AttributeError: 'DockerNetworks' object has no attribute 'inspect'
```

## 6. Reproduktion
Ein GET Request (oder eine falsche Methode wie POST im Sweep) gegen `/api/resources/networks/{network_name}`:
```bash
curl -i -H "Authorization: Bearer <TOKEN>" http://localhost:8000/api/resources/networks/dummynetwork
```

## 7. Root-Cause-Analyse
Der Code verwendet eine Methode (`inspect`), die in dem synchronen Python Docker SDK existiert, aber in der asynchronen `aiodocker` Bibliothek `get` heißt und ein Objekt liefert, bei dem man dann `show()` (oder die Eigenschaften) abruft. Die direkte API-Entsprechung zu `docker network inspect` in aiodocker ist `await docker.networks.get(network_id)` gefolgt von `await network.show()`.

## 8. Impact
User: Es können keine Details zu Docker-Netzwerken über die UI/API geladen werden (z. B. beim Inspizieren von Ressourcen).

## 9. Fix-Richtung
Ersetzen von `docker.networks.inspect(network_id)` durch den korrekten `aiodocker` Aufruf:
```python
network = await docker.networks.get(network_id)
network_info = await network.show()
```
Oder wie auch immer `aiodocker` `network inspect` in der aktuellen Version abbildet (`await docker.networks.get(network_id).show()`).

## 10. Test-Vorschlag
Ein GET Request auf `/api/resources/networks/bridge` (oder ein Dummy) muss 200 oder 404 (falls nicht vorhanden), aber nicht 500 zurückgeben.

## 11. Referenzen
`aiodocker` Dokumentation.
