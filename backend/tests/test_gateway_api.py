from fastapi.testclient import TestClient
from app.api.main import app

client = TestClient(app)
AUTH = {'Authorization': 'Bearer aro_local_dev'}

def test_v1_health_is_public():
    response = client.get('/v1/health')
    assert response.status_code == 200
    assert response.json()['service'] == 'airouter-gateway'

def test_models_is_public():
    response = client.get('/v1/models')
    assert response.status_code == 200
    assert response.json()['data'][0]['id'] == 'claude'

def test_chat_requires_api_key():
    response = client.post('/v1/chat/completions', json={'model':'claude','messages':[{'role':'user','content':'hi'}]})
    assert response.status_code == 401

def test_chat_rejects_unknown_model():
    response = client.post('/v1/chat/completions', headers=AUTH, json={'model':'not-real','messages':[{'role':'user','content':'hi'}]})
    assert response.status_code == 400

def test_legacy_health_remains_available():
    response = client.get('/health')
    assert response.status_code == 200
