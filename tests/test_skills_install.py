from silex.plugins.registry import get_registry

def test_kronos_skills_install_bundled():
    registry = get_registry()
    
    # Ensure it is uninstalled first so the test is idempotent
    registry.uninstall("security_audit")
    
    # Try to install a bundled skill (security_audit)
    ok, msg = registry.install("security_audit")
    assert ok, f"Expected security_audit to install successfully: {msg}"
    
    # Check that it is marked installed
    catalog = registry.load_catalog()
    entry = next((e for e in catalog if e.get("name") == "security_audit"), None)
    assert entry is not None
    assert entry.get("installed") is True
    
    # Re-install should fail gracefully
    ok, msg = registry.install("security_audit")
    assert not ok
    assert "already installed" in msg

def test_kronos_skills_search():
    registry = get_registry()
    results = registry.search("security")
    assert len(results) >= 1
    assert any(e["name"] == "security_audit" for e in results)
