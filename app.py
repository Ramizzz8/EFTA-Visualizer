import requests
from flask import Flask, jsonify, render_template, request, Response, stream_with_context
from bs4 import BeautifulSoup
import threading
import time

app = Flask(__name__)

BASE_URL = "https://www.justice.gov"
INDEX_URL = "https://www.justice.gov/epstein/doj-disclosures/data-set-1-files"

# Cache
_pdf_cache = []
_cache_lock = threading.Lock()
_scraping = False
_scrape_done = False
_total_pages = 63

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Persistent session — mantiene las cookies de verificación del DOJ
_doj_session = requests.Session()
_doj_session.headers.update(BROWSER_HEADERS)
_session_ready = False
_session_lock = threading.Lock()


def init_doj_session():
    """
    Visita la página principal de Epstein para obtener las cookies de sesión
    y luego acepta el aviso de privacidad/edad si existe.
    """
    global _session_ready
    with _session_lock:
        if _session_ready:
            return
        try:
            print("Iniciando sesión DOJ...")
            # 1. Visita la página principal para obtener cookies base
            r1 = _doj_session.get(
                "https://www.justice.gov/epstein",
                timeout=20,
                allow_redirects=True
            )
            print(f"  Epstein main: {r1.status_code}, cookies: {dict(_doj_session.cookies)}")

            # 2. Visita la página del dataset
            r2 = _doj_session.get(INDEX_URL, timeout=20, allow_redirects=True)
            print(f"  Dataset page: {r2.status_code}, cookies: {dict(_doj_session.cookies)}")

            # 3. Si hay formulario de verificación, buscarlo y enviarlo
            soup = BeautifulSoup(r2.text, "html.parser")
            form = soup.find("form")
            if form:
                action = form.get("action", r2.url)
                if not action.startswith("http"):
                    action = BASE_URL + action
                data = {}
                for inp in form.find_all("input"):
                    name = inp.get("name")
                    val = inp.get("value", "")
                    if name:
                        data[name] = val
                # Marcar checkboxes de verificación de edad como aceptados
                for key in list(data.keys()):
                    if any(w in key.lower() for w in ["age", "confirm", "agree", "accept", "verify"]):
                        data[key] = "1"
                print(f"  Enviando form a {action} con {data}")
                r3 = _doj_session.post(action, data=data, timeout=20, allow_redirects=True)
                print(f"  Form submit: {r3.status_code}")

            # 4. Intentar acceder directamente a un PDF de prueba
            test_url = "https://www.justice.gov/epstein/files/DataSet%201/EFTA00000001.pdf"
            rtest = _doj_session.get(
                test_url,
                timeout=20,
                allow_redirects=True,
                headers={"Accept": "application/pdf,*/*", "Referer": INDEX_URL}
            )
            print(f"  PDF test: {rtest.status_code}, content-type: {rtest.headers.get('content-type','?')}")
            print(f"  Final URL: {rtest.url}")

            _session_ready = True
        except Exception as e:
            print(f"Error inicializando sesión: {e}")
            _session_ready = True  # continuar aunque falle


def scrape_page(page_num):
    """Raspa una página del índice y devuelve lista de {name, url}."""
    url = INDEX_URL if page_num == 0 else f"{INDEX_URL}?page={page_num}"
    try:
        resp = _doj_session.get(url, timeout=20, allow_redirects=True)
        soup = BeautifulSoup(resp.text, "html.parser")
        links = []
        for a in soup.select("a[href*='/epstein/files/']"):
            href = a.get("href", "")
            if href.endswith(".pdf"):
                name = a.text.strip()
                full_url = BASE_URL + href if href.startswith("/") else href
                links.append({"name": name, "url": full_url})
        return links
    except Exception as e:
        print(f"Error scraping page {page_num}: {e}")
        return []


def background_scrape():
    global _scraping, _scrape_done
    init_doj_session()
    print("Iniciando scraping del índice...")
    for page in range(_total_pages):
        links = scrape_page(page)
        with _cache_lock:
            _pdf_cache.extend(links)
        print(f"Página {page+1}/{_total_pages} → {len(links)} PDFs | Total: {len(_pdf_cache)}")
        time.sleep(0.4)
    _scrape_done = True
    _scraping = False
    print(f"Scraping completo. Total PDFs: {len(_pdf_cache)}")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/start-scrape")
def start_scrape():
    global _scraping, _scrape_done
    if not _scraping and not _scrape_done:
        _scraping = True
        t = threading.Thread(target=background_scrape, daemon=True)
        t.start()
    return jsonify({"status": "started"})


@app.route("/api/pdfs")
def get_pdfs():
    page = int(request.args.get("page", 0))
    per_page = int(request.args.get("per_page", 50))
    search = request.args.get("search", "").lower()

    with _cache_lock:
        data = list(_pdf_cache)

    if search:
        data = [p for p in data if search in p["name"].lower()]

    total = len(data)
    start = page * per_page
    end = start + per_page
    sliced = data[start:end]

    return jsonify({
        "pdfs": sliced,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
        "scraping_done": _scrape_done,
        "scraped_count": len(_pdf_cache),
        "expected_total": _total_pages * 50,
    })


@app.route("/api/proxy")
def proxy_pdf():
    """
    Proxea un PDF desde justice.gov usando la sesión autenticada.
    Resuelve el problema de cookies de verificación de edad.
    """
    pdf_url = request.args.get("url", "")
    if not pdf_url or "justice.gov" not in pdf_url:
        return "URL inválida", 400

    if not _session_ready:
        init_doj_session()

    try:
        pdf_headers = {
            "Accept": "application/pdf,application/octet-stream,*/*",
            "Referer": INDEX_URL,
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
        }
        r = _doj_session.get(
            pdf_url,
            headers=pdf_headers,
            stream=True,
            timeout=60,
            allow_redirects=True,
        )

        # Si redirigió a una página de verificación (HTML en vez de PDF)
        content_type = r.headers.get("Content-Type", "")
        if "html" in content_type.lower():
            # Intentar aceptar la verificación y reintentar
            soup = BeautifulSoup(r.text, "html.parser")
            form = soup.find("form")
            if form:
                action = form.get("action", r.url)
                if not action.startswith("http"):
                    action = BASE_URL + action
                data = {}
                for inp in form.find_all("input"):
                    name = inp.get("name")
                    val = inp.get("value", "1")
                    if name:
                        data[name] = val
                _doj_session.post(action, data=data, timeout=20, allow_redirects=True)
                # Reintentar el PDF
                r = _doj_session.get(pdf_url, headers=pdf_headers, stream=True, timeout=60)

        def generate():
            for chunk in r.iter_content(chunk_size=8192):
                yield chunk

        resp_headers = {
            "Content-Type": r.headers.get("Content-Type", "application/pdf"),
            "Content-Disposition": "inline",
            "Access-Control-Allow-Origin": "*",
            "X-Frame-Options": "ALLOWALL",
        }
        # Pasar Content-Length si existe
        if "Content-Length" in r.headers:
            resp_headers["Content-Length"] = r.headers["Content-Length"]

        return Response(
            stream_with_context(generate()),
            status=r.status_code,
            headers=resp_headers,
        )
    except Exception as e:
        return str(e), 500


@app.route("/api/status")
def status():
    return jsonify({
        "scraping": _scraping,
        "done": _scrape_done,
        "count": len(_pdf_cache),
        "expected": _total_pages * 50,
        "session_ready": _session_ready,
    })


if __name__ == "__main__":
    _scraping = True
    t = threading.Thread(target=background_scrape, daemon=True)
    t.start()
    app.run(debug=False, port=5050, threaded=True)