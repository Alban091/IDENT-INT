import re
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup


class TrombiScraper:
    BASE_URL = "https://trombi.imtbs-tsp.eu"
    LOGIN_URL = "https://trombi.imtbs-tsp.eu/etudiants.php?login"
    ETUDIANTS_URL = "https://trombi.imtbs-tsp.eu/etudiants.php"
    PHOTO_URL = "https://trombi.imtbs-tsp.eu/photo.php"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        })
        self.authenticated = False

    def authenticate(self, username, password):
        try:
            response = self.session.get(self.LOGIN_URL, allow_redirects=True, timeout=15)
            soup = BeautifulSoup(response.text, 'html.parser')
            form = soup.find('form')
            if not form:
                return False
            action = form.get('action', '')
            if not action.startswith('http'):
                action = urljoin(response.url, action)
            data = {inp.get('name'): inp.get('value', '') for inp in form.find_all('input') if inp.get('name')}
            data['username'] = username
            data['password'] = password
            response = self.session.post(action, data=data, allow_redirects=True, timeout=15)
            if 'trombi.imtbs-tsp.eu' not in response.url:
                return False
            self.authenticated = True
            return True
        except Exception:
            return False

    def search(self, ecole='', annee=''):
        if not self.authenticated:
            return []
        students = []
        data = {
            'etu[user]': '',
            'etu[ecole]': ecole,
            'etu[annee]': annee,
        }
        try:
            response = self.session.post(self.ETUDIANTS_URL, data=data, timeout=30)
            soup = BeautifulSoup(response.text, 'html.parser')
            for fiche in soup.find_all('div', class_='ldapFiche'):
                student = self._parse_fiche(fiche, ecole)
                if student:
                    students.append(student)
        except Exception:
            pass
        return students

    def _parse_fiche(self, fiche, ecole_default='TSP'):
        try:
            classes = fiche.get('class', [])
            ecole = 'TSP' if 'TSP' in classes else 'IMT-BS' if 'IMT-BS' in classes else ecole_default
            photo_img = fiche.find('img')
            uid = None
            photo_url = None
            if photo_img and photo_img.get('src'):
                match = re.search(r'uid=([^&]+)', photo_img['src'])
                if match:
                    uid = match.group(1)
                    photo_url = f"{self.PHOTO_URL}?uid={uid}&h=320&w=240"
            if not uid:
                return None
            nom_div = fiche.find('div', class_='ldapNom')
            nom_complet = nom_div.text.strip() if nom_div else ""
            parts = nom_complet.split()
            prenom, nom_famille = "", ""
            for i, part in enumerate(parts):
                if part.isupper():
                    prenom = " ".join(parts[:i])
                    nom_famille = " ".join(parts[i:])
                    break
            if not nom_famille and parts:
                prenom = parts[0]
                nom_famille = " ".join(parts[1:]) if len(parts) > 1 else ""
            email = ""
            email_link = fiche.find('a', href=re.compile(r'^mailto:'))
            if email_link:
                email = email_link['href'].replace('mailto:', '')
            return {
                'uid': uid,
                'prenom': prenom,
                'nom_famille': nom_famille,
                'email': email,
                'ecole': ecole,
                'photo_url': photo_url,
            }
        except Exception:
            return None

    def download_photo(self, photo_url):
        try:
            response = self.session.get(
                photo_url,
                headers={'Referer': 'https://trombi.imtbs-tsp.eu/etudiants.php'},
                timeout=15
            )
            if response.status_code == 200 and len(response.content) > 100:
                return response.content
        except Exception:
            pass
        return None