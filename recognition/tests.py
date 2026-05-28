import os
import tempfile

import numpy as np
from PIL import Image
from bs4 import BeautifulSoup
from django.test import TestCase

from .models import Student
from .trombi import TrombiScraper
from .face_recognition_utils import find_matching_students


class StudentModelTest(TestCase):

    def test_get_full_name(self):
        student = Student(first_name='Marie', last_name='CURIE')
        self.assertEqual(student.get_full_name(), 'Marie CURIE')

    def test_face_encoding_roundtrip(self):
        student = Student.objects.create(first_name='Jean', last_name='TEST', email='jean@test.eu')
        encoding = np.random.rand(128)
        student.set_face_encoding(encoding)
        student.save()
        retrieved = student.get_face_encoding()
        np.testing.assert_array_almost_equal(encoding, retrieved)


class TrombiScraperParseTest(TestCase):

    def test_parse_fiche(self):
        html = '''
        <div class="ldapFiche TSP">
            <img src="photo.php?uid=jdupont&h=320&w=240">
            <div class="ldapNom">Jean DUPONT</div>
            <a href="mailto:jean.dupont@telecom-sudparis.eu">email</a>
        </div>
        '''
        fiche = BeautifulSoup(html, 'html.parser').find('div', class_='ldapFiche')
        result = TrombiScraper()._parse_fiche(fiche)
        self.assertEqual(result['uid'], 'jdupont')
        self.assertEqual(result['prenom'], 'Jean')
        self.assertEqual(result['nom_famille'], 'DUPONT')
        self.assertEqual(result['email'], 'jean.dupont@telecom-sudparis.eu')
        self.assertEqual(result['ecole'], 'TSP')


class MatchingTest(TestCase):

    def test_no_face_returns_error(self):
        img = Image.new('RGB', (100, 100), color='blue')
        path = os.path.join(tempfile.gettempdir(), 'test_noface.jpg')
        img.save(path)
        try:
            result = find_matching_students(path)
            self.assertIsNotNone(result['error'])
            self.assertEqual(result['matches'], [])
        finally:
            os.remove(path)


from django.test import TestCase

# Create your tests here.
