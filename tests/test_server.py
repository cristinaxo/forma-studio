import io
import numpy as np
import soundfile as sf
import pytest
from fastapi.testclient import TestClient
import server

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DATA", tmp_path)
    monkeypatch.setattr(server, "RESERVATIONS", set())
    # TestClient sends "Host: testserver", which production does not accept.
    monkeypatch.setattr(server, "ALLOWED_HOSTS", server.ALLOWED_HOSTS | {"testserver"})
    # API rejection tests must never enqueue inference or download a model.
    class RejectExecutor:
        def submit(self,*args):
            raise AssertionError("Invalid requests must not start an engine")
    monkeypatch.setattr(server,"EXECUTOR",RejectExecutor())
    return TestClient(server.app)

@pytest.fixture
def unpatched_client(tmp_path, monkeypatch):
    """A client with the shipped host allowlist, to prove it is enforced."""
    monkeypatch.setattr(server, "DATA", tmp_path)
    monkeypatch.setattr(server, "RESERVATIONS", set())
    return TestClient(server.app)

def queued(root, count):
    import json, time, uuid
    for _ in range(count):
        p = root / uuid.uuid4().hex
        p.mkdir()
        (p / "project.json").write_text(json.dumps(
            {"id": p.name, "title": "held", "created": time.time(), "status": "queued",
             "tool": "master", "message": "", "outputs": [], "analysis": None}))

def test_cross_origin_and_dns_rebinding_rejected(client):
    assert client.get('/api/status',headers={'host':'attacker.example'}).status_code == 403
    assert client.post('/api/projects',headers={'origin':'https://attacker.example'}).status_code == 403

def test_traversal_is_not_a_project(client):
    assert client.get('/api/projects/not-a-valid-id').status_code == 404

def test_bad_audio_is_rejected_and_cleaned_up(client):
    r=client.post('/api/projects',data={'tool':'master'},files={'source':('bad.wav',b'not audio','audio/wav')})
    assert r.status_code == 422
    assert list(server.DATA.iterdir()) == []

def test_voice_requires_reference(client):
    r=client.post('/api/projects',data={'tool':'voice'},files={'source':('test.wav',b'data','audio/wav')})
    assert r.status_code == 422

def test_voice_duration_limit(client):
    b=io.BytesIO();sf.write(b,np.zeros(44100*31),44100,format='WAV')
    r=client.post('/api/projects',data={'tool':'voice'},files={'source':('long.wav',b.getvalue(),'audio/wav'),'reference':('ref.wav',b.getvalue(),'audio/wav')})
    assert r.status_code == 422
    assert '30 seconds' in r.json()['detail']
    assert list(server.DATA.iterdir()) == []

def test_testserver_host_is_not_allowed_in_production(unpatched_client):
    assert unpatched_client.get('/api/status').status_code == 403

def test_non_numeric_content_length_is_a_bad_request(client):
    r = client.request('GET', '/api/status', headers={'content-length': 'abc'})
    assert r.status_code == 400
    assert 'Content-Length' in r.json()['detail']

def test_fourth_concurrent_job_is_refused(client):
    queued(server.DATA, 3)
    r = client.post('/api/projects', data={'tool': 'master'},
                    files={'source': ('a.wav', b'not audio', 'audio/wav')})
    assert r.status_code == 429
    assert len(list(server.DATA.iterdir())) == 3

def test_queue_slot_is_reserved_before_decoding(client):
    """Two uploads must not both pass the limit while a decode is in flight."""
    queued(server.DATA, 2)
    server.RESERVATIONS.add('a-decode-in-flight')
    r = client.post('/api/projects', data={'tool': 'master'},
                    files={'source': ('a.wav', b'not audio', 'audio/wav')})
    assert r.status_code == 429

def test_extended_step_counts_are_accepted(client):
    import io
    import numpy as np
    import soundfile as sf
    b = io.BytesIO(); sf.write(b, np.zeros(44100 * 31), 44100, format='WAV')
    r = client.post('/api/projects', data={'tool': 'voice', 'steps': '50'},
                    files={'source': ('long.wav', b.getvalue(), 'audio/wav'),
                           'reference': ('ref.wav', b.getvalue(), 'audio/wav')})
    # Rejected for duration, not for the step count.
    assert r.status_code == 422 and '30 seconds' in r.json()['detail']
    r = client.post('/api/projects', data={'tool': 'voice', 'steps': '7'},
                    files={'source': ('long.wav', b.getvalue(), 'audio/wav'),
                           'reference': ('ref.wav', b.getvalue(), 'audio/wav')})
    assert r.status_code == 422 and 'Invalid processing settings' in r.json()['detail']
