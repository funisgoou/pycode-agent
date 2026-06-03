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


def test_word_components_are_sensitive():
    assert is_sensitive("config/secrets.yaml")
    assert is_sensitive("auth/access_token.json")
    assert is_sensitive("aws/credentials")
    assert is_sensitive("my-secret-store/data")


def test_substrings_not_false_flagged():
    # These contain token/secret/credential as substrings of larger words
    # and must NOT be treated as sensitive.
    assert not is_sensitive("src/tokenizer.py")
    assert not is_sensitive("tests/test_secretary_view.py")
    assert not is_sensitive("lib/credentialing_helper.py")
