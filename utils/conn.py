def source(url, session):
    resp = session.get(url)
    return resp.json()
