import face_recognition
import numpy as np


def crop_face(image_path, margin=0.3):
    image = face_recognition.load_image_file(image_path)
    locations = face_recognition.face_locations(image)
    if not locations:
        return None
    top, right, bottom, left = max(locations, key=lambda b: (b[2]-b[0])*(b[1]-b[3]))
    h, w = image.shape[:2]
    dy, dx = int((bottom - top) * margin), int((right - left) * margin)
    top = max(0, top - dy)
    bottom = min(h, bottom + dy)
    left = max(0, left - dx)
    right = min(w, right + dx)
    return np.ascontiguousarray(image[top:bottom, left:right])


def encode_student_faces(student):
    if not student.photo:
        return False
    cropped = crop_face(student.photo.path)
    if cropped is None:
        print(f"⚠️  Pas de visage détecté pour {student.get_full_name()}")
        return False
    encodings = face_recognition.face_encodings(cropped)
    if not encodings:
        return False
    student.set_face_encoding(encodings[0])
    student.save()
    return True


def find_matching_students(uploaded_photo_path, top_k=10):
    from .models import Student

    cropped = crop_face(uploaded_photo_path)
    if cropped is None:
        return {'error': 'Aucun visage détecté sur la photo', 'matches': []}

    encodings = face_recognition.face_encodings(cropped)
    if not encodings:
        return {'error': "Impossible d'encoder le visage", 'matches': []}
    query = encodings[0]

    students = list(Student.objects.exclude(face_encoding__isnull=True).exclude(face_encoding=''))
    if not students:
        return {'error': 'Aucun étudiant avec encodage facial dans la base', 'matches': []}

    matrix = np.array([s.get_face_encoding() for s in students])
    distances = np.linalg.norm(matrix - query, axis=1)

    order = np.argsort(distances)[:top_k]
    matches = [{
        'student': students[i],
        'distance': float(distances[i]),
        'similarity': float((1 - distances[i]) * 100),
    } for i in order]

    return {'error': None, 'matches': matches}