import io
import numpy as np
import soundfile as sf
import pytest
from fastapi.testclient import TestClient
import server

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DATA", tmp_path)
    # API rejection tests must never enqueue inference or download a model.
    class RejectExecutor:
        def submit(self,*args):
            raise AssertionError("Invalid requests must not start an engine")
    monkeypatch.setattr(server,"EXECUTOR",RejectExecutor())
    return TestClient(server.app)

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
