from pycode_agent.security.paths import is_sensitive

def test_env_file_sensitive():
    assert is_sensitive(".env")
    assert is_sensitive("config/.env.local")

def test_key_and_cert_sensitive():
    assert is_sensitive("id_rsa.pem")
    assert is_sensitive("server.key")
    assert is_sensitive("secrets/api_token.txt")

def test_normal_source_not_sensitive():
    assert not is_sensitive("src/app/main.py")
    assert not is_sensitive("README.md")
