import pycode_agent

def test_version_exposed():
    assert isinstance(pycode_agent.__version__, str)
    assert pycode_agent.__version__
