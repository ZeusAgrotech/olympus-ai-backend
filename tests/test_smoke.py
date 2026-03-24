"""Smoke tests for import-time safety of the WSGI application."""


def test_wsgi_app_is_flask_application():
    import wsgi

    assert wsgi.app is not None
    assert wsgi.app.name is not None
