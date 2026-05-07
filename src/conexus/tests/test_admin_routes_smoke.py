from fastapi.testclient import TestClient

from conexus.web.admin.app import make_admin_app


def test_admin_root_renders(tmp_path):
    app = make_admin_app(agents_dir=tmp_path, data_dir=tmp_path)
    client = TestClient(app)
    resp = client.get("/admin/")
    assert resp.status_code == 200
    assert "Conexus Studio" in resp.text
