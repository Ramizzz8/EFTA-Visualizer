from flask import Flask, jsonify, render_template, request
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

BASE_URL = "https://www.justice.gov/epstein/doj-disclosures/data-set-1-files"

# Función para extraer todos los enlaces a PDFs
def scrape_pdf_links():
    r = requests.get(BASE_URL)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    # Todos los <a> que terminen en .pdf
    pdf_links = []
    for a in soup.select("a[href$='.pdf']"):
        href = a["href"]
        if href.startswith("/"):
            href = "https://www.justice.gov" + href
        pdf_links.append(href)

    return pdf_links

@app.route("/api/pdfs")
def get_pdfs():
    # Devuelve lista de URLs de PDF como JSON
    links = scrape_pdf_links()
    return jsonify(links)

@app.route("/")
def index():
    # Página principal HTML
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)