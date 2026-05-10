from fastapi.testclient import TestClient


def test_list_packs(studio_client: TestClient):
    r = studio_client.get("/admin/packs")
    assert r.status_code == 200
    assert "Skills" in r.text


def test_install_post_succeeds(studio_client: TestClient):
    r = studio_client.post("/admin/agents/ana/packs/demo/install")
    assert r.status_code in (200, 303)


def test_install_unknown_pack_returns_400(studio_client: TestClient):
    r = studio_client.post("/admin/agents/ana/packs/does-not-exist/install")
    assert r.status_code == 400


def test_uninstall_succeeds(studio_client: TestClient):
    studio_client.post("/admin/agents/ana/packs/demo/install")
    r = studio_client.post("/admin/agents/ana/packs/demo/uninstall")
    assert r.status_code in (200, 303)


def test_detail_view_shows_install_buttons(studio_client: TestClient):
    r = studio_client.get("/admin/agents/ana")
    assert r.status_code == 200
    assert "Add a pack" in r.text or "Skill Packs" in r.text
